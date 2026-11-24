from __future__ import annotations

import time
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache

from routing_app.geometry import (
    apply_truck_speed_cap,
    compute_perpendicular_via_points,
    decode_polyline,
    route_overlap_ratio,
)
from routing_app.providers.exceptions import RoutingUnavailableError


def _extract_leg_annotations(
    raw_route: dict[str, Any],
) -> tuple[list[float] | None, list[float] | None]:
    legs = raw_route.get("legs")
    if not isinstance(legs, list) or not legs:
        return None, None

    distances: list[float] = []
    durations: list[float] = []
    for leg in legs:
        if not isinstance(leg, dict):
            return None, None
        ann = leg.get("annotation")
        if not isinstance(ann, dict):
            return None, None
        d_list = ann.get("distance")
        t_list = ann.get("duration")
        if not isinstance(d_list, list) or not isinstance(t_list, list):
            return None, None
        try:
            distances.extend(float(x) for x in d_list)
            durations.extend(float(x) for x in t_list)
        except (TypeError, ValueError):
            return None, None

    return distances, durations


def _parse_osrm_route(
    raw_route: dict[str, Any],
    source: str,
    max_speed_mph: float,
) -> dict[str, Any]:
    geom = raw_route.get("geometry")
    if not isinstance(geom, str) or not geom:
        raise ValueError("OSRM route missing polyline6 geometry")

    coords = decode_polyline(geom, precision=6)
    if len(coords) < 2:
        raise ValueError("OSRM route has fewer than 2 coordinates")

    raw_dist_m = float(raw_route.get("distance") or 0.0)
    raw_dur_s = float(raw_route.get("duration") or 0.0)
    if raw_dist_m <= 0.0 or raw_dur_s <= 0.0:
        raise ValueError("OSRM route has non-positive distance or duration")

    seg_dist_m, seg_dur_s = _extract_leg_annotations(raw_route)
    cum_miles, cum_seconds = apply_truck_speed_cap(
        coords=coords,
        seg_distances_m=seg_dist_m,
        seg_durations_s=seg_dur_s,
        raw_total_distance_m=raw_dist_m,
        raw_total_duration_s=raw_dur_s,
        max_speed_mph=max_speed_mph,
    )

    return {
        "polyline": geom,
        "coords": coords,
        "cum_miles": cum_miles,
        "cum_seconds": cum_seconds,
        "distance_mi": round(cum_miles[-1], 2),
        "duration_s": round(cum_seconds[-1], 1),
        "raw_osrm_duration_s": round(raw_dur_s, 1),
        "source": source,
    }


def _query_osrm_waypoints(
    waypoints: list[tuple[float, float]],
    alternatives: bool,
    http: requests.Session,
    sleep_fn: Any,
    raise_on_error: bool = True,
) -> list[dict[str, Any]]:
    coord_str = ";".join(f"{lon:.5f},{lat:.5f}" for lat, lon in waypoints)
    url = f"{settings.OSRM_BASE_URL.rstrip('/')}/route/v1/driving/{coord_str}"
    params = {
        "overview": "full",
        "geometries": "polyline6",
        "annotations": "distance,duration",
        "alternatives": "3" if alternatives else "false",
        "steps": "false",
    }
    headers = {"User-Agent": settings.HTTP_USER_AGENT}

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = http.get(url, params=params, headers=headers, timeout=8.0)
            if resp.status_code == 429 or resp.status_code >= 500:
                last_exc = RoutingUnavailableError(
                    f"Routing provider returned HTTP {resp.status_code}"
                )
                if attempt < 2:
                    sleep_fn(0.3 * (2**attempt))
                    continue
                break
            if resp.status_code == 400:
                data = resp.json() if resp.content else {}
                code = data.get("code", "NoRoute")
                if not raise_on_error:
                    return []
                raise RoutingUnavailableError(
                    f"No drivable route found between origin and destination ({code}).",
                    status_code=400,
                )
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict) or payload.get("code") != "Ok":
                if not raise_on_error:
                    return []
                raise RoutingUnavailableError(
                    "No drivable route found between origin and destination."
                )
            routes = payload.get("routes")
            if not isinstance(routes, list) or not routes:
                if not raise_on_error:
                    return []
                raise RoutingUnavailableError("Routing provider returned no routes.")
            return routes
        except RoutingUnavailableError as exc:
            last_exc = exc
            if exc.status_code == 400:
                raise
            if attempt < 2:
                sleep_fn(0.3 * (2**attempt))
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            if attempt < 2:
                sleep_fn(0.3 * (2**attempt))

    if not raise_on_error:
        return []
    raise RoutingUnavailableError(
        f"Routing unavailable after 3 attempts: {last_exc}"
    )


def _direction_descriptor(
    origin: tuple[float, float],
    destination: tuple[float, float],
    route_coords: list[tuple[float, float]],
    primary_coords: list[tuple[float, float]],
) -> str:
    if not route_coords or not primary_coords:
        return "Alternate Corridor"
    mid_r = route_coords[len(route_coords) // 2]
    mid_p = primary_coords[len(primary_coords) // 2]
    dlat = mid_r[0] - mid_p[0]
    dlon = mid_r[1] - mid_p[1]

    # Determine if primary trip is mostly East-West or North-South
    trip_dlat = abs(destination[0] - origin[0])
    trip_dlon = abs(destination[1] - origin[1])
    if trip_dlon >= trip_dlat:
        return "Northern Corridor" if dlat >= 0 else "Southern Corridor"
    return "Eastern Corridor" if dlon >= 0 else "Western Corridor"


def _is_distinct_route(
    cand: dict[str, Any], existing_routes: list[dict[str, Any]]
) -> bool:
    return all(
        route_overlap_ratio(
            cand["coords"],
            cand["cum_miles"],
            cand["cum_seconds"],
            existing["coords"],
            existing["cum_miles"],
            existing["cum_seconds"],
        )
        < 0.70
        for existing in existing_routes
    )


def fetch_three_routes(
    origin: tuple[float, float],
    destination: tuple[float, float],
    max_speed_mph: float | None = None,
    session: requests.Session | None = None,
    sleep_fn: Any = time.sleep,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch up to 3 distinct drivable routes between origin and destination.

    1. Queries native OSRM alternatives first.
    2. If < 3 distinct routes (<70% overlap) come back, queries perpendicular
       via-points centered on the corridor midpoint so we get 3 distinct routes.
    Returns (routes_list, notices_list).
    """
    speed_cap = (
        float(max_speed_mph)
        if max_speed_mph is not None
        else float(settings.TRUCK_MAX_SPEED_MPH)
    )
    ckey = (
        f"routes:v2:{origin[0]:.4f},{origin[1]:.4f}:"
        f"{destination[0]:.4f},{destination[1]:.4f}:{speed_cap:.1f}"
    )
    cached = cache.get(ckey)
    if cached is not None:
        return cached

    http = session or requests.Session()
    raw_primary = _query_osrm_waypoints(
        [origin, destination],
        alternatives=True,
        http=http,
        sleep_fn=sleep_fn,
        raise_on_error=True,
    )

    accepted: list[dict[str, Any]] = []
    for raw_r in raw_primary:
        try:
            parsed = _parse_osrm_route(raw_r, source="osrm", max_speed_mph=speed_cap)
        except ValueError:
            continue
        if _is_distinct_route(parsed, accepted):
            accepted.append(parsed)
        if len(accepted) >= 3:
            break

    if not accepted:
        raise RoutingUnavailableError(
            "Routing provider returned malformed route geometry."
        )

    fastest_dur = min(r["duration_s"] for r in accepted)

    # Via-point fallback if native OSRM returned fewer than 3 distinct routes
    if len(accepted) < 3:
        via_points = compute_perpendicular_via_points(
            origin=origin,
            destination=destination,
            route_coords=None,
            offsets=(0.0, 0.14, -0.14, 0.25, -0.25),
        )
        slow_fallbacks: list[dict[str, Any]] = []
        for via in via_points:
            if len(accepted) >= 3:
                break
            via_raw_list = _query_osrm_waypoints(
                [origin, via, destination],
                alternatives=False,
                http=http,
                sleep_fn=sleep_fn,
                raise_on_error=False,
            )
            for via_raw in via_raw_list:
                try:
                    cand = _parse_osrm_route(
                        via_raw, source="via-point", max_speed_mph=speed_cap
                    )
                except ValueError:
                    continue
                if cand["duration_s"] > fastest_dur * 1.95:
                    continue
                if not _is_distinct_route(cand, accepted):
                    continue
                if cand["duration_s"] <= fastest_dur * 1.55:
                    accepted.append(cand)
                else:
                    slow_fallbacks.append(cand)
                break

        if len(accepted) < 3 and slow_fallbacks:
            slow_fallbacks.sort(key=lambda r: r["duration_s"])
            for cand in slow_fallbacks:
                if len(accepted) >= 3:
                    break
                if _is_distinct_route(cand, accepted):
                    accepted.append(cand)

    letters = ("A", "B", "C")
    primary_coords = accepted[0]["coords"]
    used_labels: set[str] = set()

    for idx, route in enumerate(accepted[:3]):
        letter = letters[idx]
        route["id"] = f"route_{letter.lower()}"
        if idx == 0:
            desc = "Primary Direct"
        else:
            desc = _direction_descriptor(
                origin, destination, route["coords"], primary_coords
            )
            if desc in used_labels:
                desc = f"{desc} II"
        used_labels.add(desc)
        route["name"] = f"Route {letter} ({desc})"

    notices: list[str] = []
    if len(accepted) < 3:
        notices.append(
            f"Only {len(accepted)} distinct drivable route(s) available for this corridor."
        )

    result = (accepted[:3], notices)
    cache.set(ckey, result, timeout=3600)
    return result
