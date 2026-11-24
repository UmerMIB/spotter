from __future__ import annotations

import bisect
import math
from datetime import UTC, datetime
from typing import Any

EARTH_RADIUS_MI = 3958.7613
METERS_TO_MILES = 0.000621371192


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two (lat, lon) points in statute miles."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi * 0.5) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda * 0.5) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return EARTH_RADIUS_MI * c


def decode_polyline(encoded: str, precision: int = 6) -> list[tuple[float, float]]:
    """Decode an encoded polyline string (default polyline6) into [(lat, lon), ...]."""
    factor = 10.0**precision
    coords: list[tuple[float, float]] = []
    index = 0
    lat = 0
    lon = 0
    length = len(encoded)

    while index < length:
        shift = 0
        result = 0
        while True:
            if index >= length:
                raise ValueError("Malformed polyline string")
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat

        shift = 0
        result = 0
        while True:
            if index >= length:
                raise ValueError("Malformed polyline string")
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlon = ~(result >> 1) if (result & 1) else (result >> 1)
        lon += dlon

        coords.append((lat / factor, lon / factor))

    return coords


def encode_polyline(coords: list[tuple[float, float]], precision: int = 6) -> str:
    """Encode [(lat, lon), ...] into a polyline string (default polyline6)."""
    factor = 10.0**precision
    output: list[str] = []
    prev_lat = 0
    prev_lon = 0

    def _encode_value(val: int) -> None:
        v = ~(val << 1) if val < 0 else (val << 1)
        while v >= 0x20:
            output.append(chr((0x20 | (v & 0x1F)) + 63))
            v >>= 5
        output.append(chr(v + 63))

    for lat, lon in coords:
        ilat = round(lat * factor)
        ilon = round(lon * factor)
        _encode_value(ilat - prev_lat)
        _encode_value(ilon - prev_lon)
        prev_lat = ilat
        prev_lon = ilon

    return "".join(output)


def apply_truck_speed_cap(
    coords: list[tuple[float, float]],
    seg_distances_m: list[float] | None = None,
    seg_durations_s: list[float] | None = None,
    raw_total_distance_m: float | None = None,
    raw_total_duration_s: float | None = None,
    max_speed_mph: float = 65.0,
) -> tuple[list[float], list[float]]:
    """Compute cumulative (miles, seconds) at each vertex with a truck speed cap.

    Each road segment is traversed at min(OSRM speed, max_speed_mph).
    """
    n = len(coords)
    if n == 0:
        return [], []
    if n == 1:
        return [0.0], [0.0]

    num_edges = n - 1
    has_seg_dist = seg_distances_m is not None and len(seg_distances_m) == num_edges
    has_seg_dur = seg_durations_s is not None and len(seg_durations_s) == num_edges

    edge_miles: list[float] = []
    for i in range(num_edges):
        if has_seg_dist:
            d_mi = max(0.0, float(seg_distances_m[i]) * METERS_TO_MILES)  # type: ignore[index]
        else:
            d_mi = haversine_miles(
                coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1]
            )
        edge_miles.append(d_mi)

    sum_geo_miles = sum(edge_miles)
    if not has_seg_dist and raw_total_distance_m and sum_geo_miles > 0:
        target_mi = float(raw_total_distance_m) * METERS_TO_MILES
        scale = target_mi / sum_geo_miles
        edge_miles = [d * scale for d in edge_miles]
        sum_geo_miles = target_mi

    fallback_total_dur = float(raw_total_duration_s or 0.0)

    cum_miles = [0.0]
    cum_seconds = [0.0]

    for i in range(num_edges):
        d_mi = edge_miles[i]
        if has_seg_dur:
            raw_s = max(0.0, float(seg_durations_s[i]))  # type: ignore[index]
        elif sum_geo_miles > 0 and fallback_total_dur > 0:
            raw_s = fallback_total_dur * (d_mi / sum_geo_miles)
        else:
            raw_s = (d_mi / 55.0) * 3600.0

        if max_speed_mph > 0.0:
            min_truck_s = (d_mi / max_speed_mph) * 3600.0
            eff_s = max(raw_s, min_truck_s)
        else:
            eff_s = raw_s

        cum_miles.append(cum_miles[-1] + d_mi)
        cum_seconds.append(cum_seconds[-1] + eff_s)

    return cum_miles, cum_seconds


def interpolate_along_route(
    coords: list[tuple[float, float]],
    cum_miles: list[float],
    cum_seconds: list[float],
    target_mile: float,
) -> tuple[float, float, float]:
    """Interpolate (lat, lon, elapsed_seconds) at target_mile along a route."""
    if not coords:
        raise ValueError("Route has no coordinates")
    if len(coords) == 1 or target_mile <= 0.0:
        return coords[0][0], coords[0][1], 0.0

    total_mi = cum_miles[-1]
    if target_mile >= total_mi:
        return coords[-1][0], coords[-1][1], cum_seconds[-1]

    idx = bisect.bisect_right(cum_miles, target_mile) - 1
    idx = min(max(0, idx), len(coords) - 2)

    m0 = cum_miles[idx]
    m1 = cum_miles[idx + 1]
    span = m1 - m0
    frac = (target_mile - m0) / span if span > 1e-9 else 0.0
    frac = min(max(0.0, frac), 1.0)

    lat = coords[idx][0] + frac * (coords[idx + 1][0] - coords[idx][0])
    lon = coords[idx][1] + frac * (coords[idx + 1][1] - coords[idx][1])
    elapsed_s = cum_seconds[idx] + frac * (cum_seconds[idx + 1] - cum_seconds[idx])
    return lat, lon, elapsed_s


def resample_route_checkpoints(
    coords: list[tuple[float, float]],
    cum_miles: list[float],
    cum_seconds: list[float],
    interval_mi: int,
    departure_ts: float,
) -> list[dict[str, Any]]:
    """Sample checkpoints along the route every interval_mi miles plus destination."""
    if not coords or not cum_miles:
        return []

    total_miles = cum_miles[-1]
    step = float(interval_mi)
    sample_miles: list[float] = [0.0]

    curr = step
    while curr < total_miles:
        sample_miles.append(curr)
        curr += step

    if total_miles > 0.0:
        if len(sample_miles) > 1 and (total_miles - sample_miles[-1]) < min(
            2.0, step * 0.15
        ):
            sample_miles[-1] = total_miles
        elif sample_miles[-1] < total_miles:
            sample_miles.append(total_miles)

    checkpoints: list[dict[str, Any]] = []
    for idx, mile in enumerate(sample_miles):
        lat, lon, elapsed_s = interpolate_along_route(
            coords, cum_miles, cum_seconds, mile
        )
        eta_ts = departure_ts + elapsed_s
        eta_iso = (
            datetime.fromtimestamp(eta_ts, tz=UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        checkpoints.append(
            {
                "index": idx,
                "interval_mi": interval_mi,
                "mile": round(mile, 2),
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "elapsed_s": round(elapsed_s, 1),
                "eta_ts": round(eta_ts, 1),
                "eta_utc": eta_iso,
            }
        )

    return checkpoints


def compute_perpendicular_via_points(
    origin: tuple[float, float],
    destination: tuple[float, float],
    route_coords: list[tuple[float, float]] | None = None,
    offsets: tuple[float, ...] = (0.18, -0.18, 0.32, -0.32),
) -> list[tuple[float, float]]:
    """Compute candidate via-points offset perpendicularly from the route midpoint."""
    lat1, lon1 = origin
    lat2, lon2 = destination

    if route_coords and len(route_coords) >= 3:
        mid_idx = len(route_coords) // 2
        mid_lat, mid_lon = route_coords[mid_idx]
    else:
        mid_lat = 0.5 * (lat1 + lat2)
        mid_lon = 0.5 * (lon1 + lon2)

    cos_lat = max(0.2, math.cos(math.radians(mid_lat)))
    dlat = lat2 - lat1
    dlon_scaled = (lon2 - lon1) * cos_lat
    norm = math.hypot(dlat, dlon_scaled)
    if norm < 1e-6:
        return []

    # Unit perpendicular vector in equal-distance local plane
    perp_lat = -dlon_scaled / norm
    perp_lon_scaled = dlat / norm

    via_points: list[tuple[float, float]] = []
    for frac in offsets:
        dist_deg = frac * norm
        v_lat = mid_lat + perp_lat * dist_deg
        v_lon = mid_lon + (perp_lon_scaled * dist_deg) / cos_lat
        v_lat = min(max(-85.0, v_lat), 85.0)
        v_lon = min(max(-180.0, v_lon), 180.0)
        via_points.append((round(v_lat, 5), round(v_lon, 5)))

    return via_points


def route_overlap_ratio(
    coords_a: list[tuple[float, float]],
    cum_miles_a: list[float],
    cum_seconds_a: list[float],
    coords_b: list[tuple[float, float]],
    cum_miles_b: list[float],
    cum_seconds_b: list[float],
    sample_count: int = 30,
    threshold_miles: float = 4.0,
) -> float:
    """Estimate fraction of interior of Route A that lies within threshold_miles of Route B."""
    if not coords_a or not coords_b:
        return 0.0
    total_a = cum_miles_a[-1]
    total_b = cum_miles_b[-1]
    if total_a <= 1.0 or total_b <= 1.0:
        return 1.0

    # Sample interior 10%..90% of both routes
    pts_a = [
        interpolate_along_route(
            coords_a,
            cum_miles_a,
            cum_seconds_a,
            total_a * (0.10 + 0.80 * i / max(1, sample_count - 1)),
        )[:2]
        for i in range(sample_count)
    ]
    dense_b = [
        interpolate_along_route(
            coords_b,
            cum_miles_b,
            cum_seconds_b,
            total_b * (i / max(1, (sample_count * 2) - 1)),
        )[:2]
        for i in range(sample_count * 2)
    ]

    close_count = 0
    for lat_a, lon_a in pts_a:
        min_d = min(
            haversine_miles(lat_a, lon_a, lat_b, lon_b) for lat_b, lon_b in dense_b
        )
        if min_d <= threshold_miles:
            close_count += 1

    return close_count / len(pts_a)


def snap_to_weather_cell(
    lat: float, lon: float, resolution_deg: float = 0.1
) -> tuple[float, float]:
    """Snap (lat, lon) to the nearest weather cache grid cell (default 0.1 deg ≈ 7 mi)."""
    inv = 1.0 / resolution_deg
    return (round(round(lat * inv) / inv, 2), round(round(lon * inv) / inv, 2))


def build_corridor_heatgrid(
    routes_coords: list[list[tuple[float, float]]],
    max_active_cells: int = 220,
    corridor_radius_mi: float = 45.0,
) -> dict[str, Any]:
    """Build an adaptive lat/lon grid covering the route corridor with <= max_active_cells active points."""
    all_pts = [pt for r in routes_coords for pt in r]
    if not all_pts:
        raise ValueError("Cannot build corridor grid with no route coordinates")

    min_lat = min(p[0] for p in all_pts)
    max_lat = max(p[0] for p in all_pts)
    min_lon = min(p[1] for p in all_pts)
    max_lon = max(p[1] for p in all_pts)

    mid_lat = 0.5 * (min_lat + max_lat)
    cos_lat = max(0.2, math.cos(math.radians(mid_lat)))

    pad_lat = 0.45  # ~31 miles
    pad_lon = 0.45 / cos_lat

    min_lat -= pad_lat
    max_lat += pad_lat
    min_lon -= pad_lon
    max_lon += pad_lon

    # Downsample route polylines to ~120 reference points total for fast distance checks
    ref_pts: list[tuple[float, float]] = []
    for r in routes_coords:
        step = max(1, len(r) // 45)
        ref_pts.extend(r[::step])
        if r[-1] != ref_pts[-1]:
            ref_pts.append(r[-1])

    span_lat = max(0.3, max_lat - min_lat)
    span_lon = max(0.3, max_lon - min_lon)

    # Start with a candidate grid spacing and coarsen until active cells <= max_active_cells
    aspect = (span_lon * cos_lat) / span_lat
    target_total = max_active_cells * 1.6
    rows = max(6, min(28, round(math.sqrt(target_total / max(0.25, aspect)))))
    cols = max(6, min(36, round(rows * max(0.35, min(3.0, aspect)))))

    while True:
        dlat = span_lat / rows
        dlon = span_lon / cols
        cell_diag_mi = 0.5 * math.hypot(dlat * 69.0, dlon * 69.0 * cos_lat)
        eff_radius = max(corridor_radius_mi, cell_diag_mi * 1.35)

        mask: list[int] = []
        active_cells: list[dict[str, Any]] = []

        # Row 0 is top (north: max_lat) to bottom (south: min_lat) to match image coordinates!
        for r_idx in range(rows):
            cell_lat = max_lat - (r_idx + 0.5) * dlat
            for c_idx in range(cols):
                cell_lon = min_lon + (c_idx + 0.5) * dlon
                is_near = any(
                    haversine_miles(cell_lat, cell_lon, rp[0], rp[1]) <= eff_radius
                    for rp in ref_pts
                )
                flat_idx = r_idx * cols + c_idx
                if is_near:
                    mask.append(1)
                    active_cells.append(
                        {
                            "idx": flat_idx,
                            "row": r_idx,
                            "col": c_idx,
                            "lat": round(cell_lat, 4),
                            "lon": round(cell_lon, 4),
                        }
                    )
                else:
                    mask.append(0)

        if len(active_cells) <= max_active_cells or (rows <= 6 and cols <= 6):
            break
        rows = max(6, round(rows * 0.85))
        cols = max(6, round(cols * 0.85))

    return {
        "bbox": [
            round(min_lon, 5),
            round(min_lat, 5),
            round(max_lon, 5),
            round(max_lat, 5),
        ],
        "rows": rows,
        "cols": cols,
        "mask": mask,
        "active_cells": active_cells,
    }
