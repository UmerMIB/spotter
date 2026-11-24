from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import requests
from django.conf import settings

from routing_app.geometry import (
    build_corridor_heatgrid,
    haversine_miles,
    resample_route_checkpoints,
    snap_to_weather_cell,
)
from routing_app.providers.geocoding import resolve_location
from routing_app.providers.routing import fetch_three_routes
from routing_app.providers.weather import (
    fetch_weather_for_cells,
    interpolate_weather_at_timestamp,
)
from routing_app.risk import (
    compute_segment_lengths,
    evaluate_checkpoint_risk,
    rank_route_summaries,
    summarize_route,
)

SAMPLING_INTERVALS = (10, 25, 50)
HEATMAP_HOURS = 49


class TripValidationError(Exception):
    """Raised when user trip inputs (departure time, load weight, or corridor) fail validation."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


def parse_and_validate_departure(
    departure_raw: Any,
    now_ts: float | None = None,
) -> tuple[float, str]:
    """Validate departure_time ISO string is within [now - 1h, now + 7d]."""
    if not isinstance(departure_raw, str) or not departure_raw.strip():
        raise TripValidationError(
            "Departure date and time is required.", field="departure_time"
        )

    raw = departure_raw.strip()
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        else:
            dt = dt.astimezone(UTC)
    except ValueError as exc:
        raise TripValidationError(
            "Invalid departure date/time format. Use ISO-8601 format.",
            field="departure_time",
        ) from exc

    dep_ts = dt.timestamp()
    ref_now = now_ts if now_ts is not None else time.time()

    if dep_ts < ref_now - 3600:
        raise TripValidationError(
            "Departure time cannot be in the past.", field="departure_time"
        )
    if dep_ts > ref_now + 7 * 86400 + 3600:
        raise TripValidationError(
            "Departure time must be within the next 7 days for reliable hourly weather forecasts.",
            field="departure_time",
        )

    iso_utc = dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return dep_ts, iso_utc


def validate_load_weight(load_raw: Any) -> float:
    """Validate truck load weight in pounds (0 to 80,000 lb)."""
    if load_raw is None or isinstance(load_raw, bool) or str(load_raw).strip() == "":
        raise TripValidationError("Load weight (lb) is required.", field="load_lb")
    try:
        load_lb = float(load_raw)
    except (TypeError, ValueError) as exc:
        raise TripValidationError(
            "Load weight must be a valid number in pounds.", field="load_lb"
        ) from exc

    if load_lb < 0.0 or load_lb > 80000.0:
        raise TripValidationError(
            "Load weight must be between 0 and 80,000 lb.", field="load_lb"
        )
    return round(load_lb, 1)


def _downsample_route_profile(
    coords: list[tuple[float, float]],
    cum_miles: list[float],
    cum_seconds: list[float],
    max_points: int = 350,
) -> tuple[list[list[float]], list[list[float]]]:
    """Return compact [[lon, lat], ...] GeoJSON coordinates and [[mile, elapsed_s, lat, lon], ...] table."""
    n = len(coords)
    if n <= max_points:
        indices = list(range(n))
    else:
        step = (n - 1) / float(max_points - 1)
        indices = sorted({min(n - 1, round(i * step)) for i in range(max_points)})
        if indices[-1] != n - 1:
            indices.append(n - 1)

    geojson_coords = [
        [round(coords[i][1], 5), round(coords[i][0], 5)] for i in indices
    ]
    progress_profile = [
        [
            round(cum_miles[i], 2),
            round(cum_seconds[i], 1),
            round(coords[i][0], 5),
            round(coords[i][1], 5),
        ]
        for i in indices
    ]
    return geojson_coords, progress_profile


def build_trip_bundle(
    payload: dict[str, Any],
    session: requests.Session | None = None,
    now_ts: float | None = None,
    sleep_fn: Any = time.sleep,
) -> dict[str, Any]:
    """Execute the full weather-aware truck routing pipeline for a trip request."""
    origin_raw = payload.get("origin")
    destination_raw = payload.get("destination")
    departure_ts, departure_utc = parse_and_validate_departure(
        payload.get("departure_time"), now_ts=now_ts
    )
    load_lb = validate_load_weight(payload.get("load_lb"))

    origin = resolve_location(
        origin_raw, field_name="origin", session=session, sleep_fn=sleep_fn
    )
    destination = resolve_location(
        destination_raw, field_name="destination", session=session, sleep_fn=sleep_fn
    )

    direct_mi = haversine_miles(
        origin["lat"], origin["lon"], destination["lat"], destination["lon"]
    )
    if direct_mi < 1.0:
        raise TripValidationError(
            "Origin and destination must be at least 1 mile apart.",
            field="destination",
        )

    raw_routes, route_notices = fetch_three_routes(
        (origin["lat"], origin["lon"]),
        (destination["lat"], destination["lon"]),
        max_speed_mph=float(settings.TRUCK_MAX_SPEED_MPH),
        session=session,
        sleep_fn=sleep_fn,
    )

    # 1. Resample checkpoints for all 3 intervals (10, 25, 50 mi) across all routes
    checkpoints_by_interval: dict[str, dict[str, list[dict[str, Any]]]] = {
        str(interval): {} for interval in SAMPLING_INTERVALS
    }
    weather_points: list[tuple[float, float]] = []

    for route in raw_routes:
        rid = route["id"]
        for interval in SAMPLING_INTERVALS:
            cps = resample_route_checkpoints(
                coords=route["coords"],
                cum_miles=route["cum_miles"],
                cum_seconds=route["cum_seconds"],
                interval_mi=interval,
                departure_ts=departure_ts,
            )
            checkpoints_by_interval[str(interval)][rid] = cps
            for cp in cps:
                weather_points.append((cp["lat"], cp["lon"]))

    # 2. Build corridor heatmap grid
    heatgrid_meta = build_corridor_heatgrid(
        [r["coords"] for r in raw_routes],
        max_active_cells=200,
        corridor_radius_mi=45.0,
    )
    for cell in heatgrid_meta["active_cells"]:
        weather_points.append((cell["lat"], cell["lon"]))

    # 3. Fetch weather for all unique 0.1° cells (checkpoints + corridor heatmap)
    cell_weather_map, weather_warnings = fetch_weather_for_cells(
        weather_points,
        resolution_deg=0.1,
        session=session,
        sleep_fn=sleep_fn,
    )

    # 4. Evaluate risk at every checkpoint and summarize/rank routes per interval
    summaries_by_interval: dict[str, list[dict[str, Any]]] = {}
    coverage_threshold = float(settings.WEATHER_COVERAGE_THRESHOLD_PCT)

    for interval in SAMPLING_INTERVALS:
        ikey = str(interval)
        interval_summaries: list[dict[str, Any]] = []

        for route in raw_routes:
            rid = route["id"]
            cps = checkpoints_by_interval[ikey][rid]
            cp_miles = [float(cp["mile"]) for cp in cps]
            seg_lengths = compute_segment_lengths(cp_miles, route["distance_mi"])

            for cp, seg_mi in zip(cps, seg_lengths):
                w_cell = snap_to_weather_cell(cp["lat"], cp["lon"], resolution_deg=0.1)
                series = cell_weather_map.get(w_cell)
                wx = interpolate_weather_at_timestamp(series, cp["eta_ts"])

                risk_res = evaluate_checkpoint_risk(
                    wind_mph=wx["wind_mph"],
                    rain_in_hr=wx["rain_in_hr"],
                    snow_in_hr=wx["snow_in_hr"],
                    load_lb=load_lb,
                )

                cp["route_id"] = rid
                cp["route_name"] = route["name"]
                cp["segment_miles"] = round(seg_mi, 2)
                cp["wind_mph"] = (
                    round(wx["wind_mph"], 1) if wx["wind_mph"] is not None else None
                )
                cp["gust_mph"] = (
                    round(wx["gust_mph"], 1) if wx["gust_mph"] is not None else None
                )
                cp["rain_in_hr"] = (
                    round(wx["rain_in_hr"], 3) if wx["rain_in_hr"] is not None else None
                )
                cp["snow_in_hr"] = (
                    round(wx["snow_in_hr"], 3) if wx["snow_in_hr"] is not None else None
                )
                cp["wind_level"] = risk_res.wind_level
                cp["rain_level"] = risk_res.rain_level
                cp["snow_level"] = risk_res.snow_level
                cp["level"] = risk_res.level
                cp["score"] = risk_res.score
                cp["load_rule_triggered"] = risk_res.load_rule_triggered
                cp["factors"] = risk_res.factors

            summary = summarize_route(
                route_id=rid,
                route_name=route["name"],
                interval_mi=interval,
                total_distance_mi=route["distance_mi"],
                duration_s=route["duration_s"],
                checkpoints=cps,
            )
            interval_summaries.append(summary)

        summaries_by_interval[ikey] = rank_route_summaries(
            interval_summaries,
            coverage_threshold_pct=coverage_threshold,
        )

    # 5. Precompute 0-48h hourly heatmap values for all active corridor cells
    hour_timestamps = [departure_ts + h * 3600.0 for h in range(HEATMAP_HOURS)]
    hour_iso_labels = [
        datetime.fromtimestamp(ts, tz=UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
        for ts in hour_timestamps
    ]

    heat_cells_out: list[dict[str, Any]] = []
    for cell in heatgrid_meta["active_cells"]:
        w_cell = snap_to_weather_cell(cell["lat"], cell["lon"], resolution_deg=0.1)
        series = cell_weather_map.get(w_cell)

        wind_arr: list[float | None] = []
        rain_arr: list[float | None] = []
        snow_arr: list[float | None] = []
        score_arr: list[int] = []

        for ts in hour_timestamps:
            wx = interpolate_weather_at_timestamp(series, ts)
            w_val = wx["wind_mph"]
            r_val = wx["rain_in_hr"]
            s_val = wx["snow_in_hr"]

            risk_res = evaluate_checkpoint_risk(
                wind_mph=w_val,
                rain_in_hr=r_val,
                snow_in_hr=s_val,
                load_lb=load_lb,
            )
            wind_arr.append(round(w_val, 1) if w_val is not None else None)
            rain_arr.append(round(r_val, 3) if r_val is not None else None)
            snow_arr.append(round(s_val, 3) if s_val is not None else None)
            score_arr.append(risk_res.score if risk_res.score is not None else 0)

        heat_cells_out.append(
            {
                "idx": cell["idx"],
                "row": cell["row"],
                "col": cell["col"],
                "lat": cell["lat"],
                "lon": cell["lon"],
                "wind": wind_arr,
                "rain": rain_arr,
                "snow": snow_arr,
                "score": score_arr,
            }
        )

    # 6. Serialize route geometries and truck progress profiles
    routes_out: list[dict[str, Any]] = []
    for route in raw_routes:
        geojson_coords, progress_profile = _downsample_route_profile(
            route["coords"],
            route["cum_miles"],
            route["cum_seconds"],
        )
        eta_ts = departure_ts + route["duration_s"]
        eta_utc = (
            datetime.fromtimestamp(eta_ts, tz=UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        routes_out.append(
            {
                "id": route["id"],
                "name": route["name"],
                "source": route["source"],
                "polyline": route["polyline"],
                "geojson_coords": geojson_coords,
                "progress_profile": progress_profile,
                "distance_mi": route["distance_mi"],
                "duration_s": route["duration_s"],
                "eta_utc": eta_utc,
            }
        )

    all_notices = route_notices + weather_warnings

    return {
        "request": {
            "origin": origin,
            "destination": destination,
            "departure_utc": departure_utc,
            "departure_ts": round(departure_ts, 1),
            "load_lb": load_lb,
            "truck_max_speed_mph": float(settings.TRUCK_MAX_SPEED_MPH),
            "default_interval_mi": 25,
        },
        "routes": routes_out,
        "intervals": {
            ikey: {
                "summaries": summaries_by_interval[ikey],
                "checkpoints": checkpoints_by_interval[ikey],
            }
            for ikey in ("10", "25", "50")
        },
        "heat_grid": {
            "bbox": heatgrid_meta["bbox"],
            "rows": heatgrid_meta["rows"],
            "cols": heatgrid_meta["cols"],
            "mask": heatgrid_meta["mask"],
            "start_utc": departure_utc,
            "start_ts": round(departure_ts, 1),
            "hours": HEATMAP_HOURS,
            "hour_utc": hour_iso_labels,
            "cells": heat_cells_out,
        },
        "notices": all_notices,
    }
