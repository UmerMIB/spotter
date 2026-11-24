from __future__ import annotations

import bisect
import math
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache

from routing_app.geometry import snap_to_weather_cell

BATCH_SIZE = 75


def _clean_float(val: Any) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f) or f < 0.0:
        return None
    return f


def _parse_single_hourly(item: Any) -> dict[str, list[ Any]] | None:
    if not isinstance(item, dict) or item.get("error"):
        return None
    hourly = item.get("hourly")
    if not isinstance(hourly, dict):
        return None

    raw_times = hourly.get("time")
    raw_winds = hourly.get("wind_speed_10m")
    raw_gusts = hourly.get("wind_gusts_10m")
    raw_rains = hourly.get("rain")
    raw_showers = hourly.get("showers")
    raw_snows = hourly.get("snowfall")

    if not isinstance(raw_times, list) or not raw_times:
        return None
    n = len(raw_times)
    if (
        not isinstance(raw_winds, list)
        or len(raw_winds) != n
        or not isinstance(raw_rains, list)
        or len(raw_rains) != n
        or not isinstance(raw_snows, list)
        or len(raw_snows) != n
    ):
        return None

    has_showers = isinstance(raw_showers, list) and len(raw_showers) == n
    has_gusts = isinstance(raw_gusts, list) and len(raw_gusts) == n

    times: list[int] = []
    wind_mph: list[float | None] = []
    gust_mph: list[float | None] = []
    rain_in_hr: list[float | None] = []
    snow_in_hr: list[float | None] = []

    for i in range(n):
        try:
            t_val = int(raw_times[i])
        except (TypeError, ValueError):
            return None
        times.append(t_val)
        wind_mph.append(_clean_float(raw_winds[i]))
        gust_mph.append(_clean_float(raw_gusts[i]) if has_gusts else None)

        r_val = _clean_float(raw_rains[i])
        sh_val = _clean_float(raw_showers[i]) if has_showers else 0.0
        if r_val is None or (has_showers and sh_val is None):
            rain_in_hr.append(None)
        else:
            rain_in_hr.append(round(r_val + (sh_val or 0.0), 4))

        snow_in_hr.append(_clean_float(raw_snows[i]))

    return {
        "time": times,
        "wind_mph": wind_mph,
        "gust_mph": gust_mph,
        "rain_in_hr": rain_in_hr,
        "snow_in_hr": snow_in_hr,
    }


def _fetch_batch(
    batch_cells: list[tuple[float, float]],
    http: requests.Session | None,
    sleep_fn: Any,
) -> tuple[dict[tuple[float, float], dict[str, Any] | None], str | None]:
    """Fetch a single batch of up to BATCH_SIZE cells from Open-Meteo."""
    client = http or requests.Session()
    lats = ",".join(f"{c[0]:.2f}" for c in batch_cells)
    lons = ",".join(f"{c[1]:.2f}" for c in batch_cells)
    params = {
        "latitude": lats,
        "longitude": lons,
        "hourly": "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timeformat": "unixtime",
        "forecast_days": 10,
        "past_days": 1,
    }
    headers = {"User-Agent": settings.HTTP_USER_AGENT}

    last_warning: str | None = None
    for attempt in range(2):
        try:
            resp = client.get(
                settings.OPEN_METEO_BASE_URL,
                params=params,
                headers=headers,
                timeout=8.0,
            )
            if resp.status_code == 429:
                last_warning = "Weather provider rate-limited (HTTP 429); affected locations marked Unknown."
                if attempt == 0:
                    sleep_fn(0.4)
                    continue
                return {c: None for c in batch_cells}, last_warning
            if resp.status_code >= 500:
                last_warning = f"Weather provider unavailable (HTTP {resp.status_code}); affected locations marked Unknown."
                if attempt == 0:
                    sleep_fn(0.4)
                    continue
                return {c: None for c in batch_cells}, last_warning

            resp.raise_for_status()
            payload = resp.json()

            items: list[Any]
            if len(batch_cells) == 1:
                items = [payload] if isinstance(payload, dict) else (payload if isinstance(payload, list) else [])
            else:
                items = payload if isinstance(payload, list) else []

            if len(items) != len(batch_cells):
                return (
                    {c: None for c in batch_cells},
                    "Weather provider returned malformed batch response.",
                )

            out: dict[tuple[float, float], dict[str, Any] | None] = {}
            had_malformed = False
            for cell, raw_item in zip(batch_cells, items):
                parsed = _parse_single_hourly(raw_item)
                if parsed is None:
                    had_malformed = True
                out[cell] = parsed

            warn = (
                "Some weather forecast cells returned incomplete data."
                if had_malformed
                else None
            )
            return out, warn
        except (requests.RequestException, ValueError) as exc:
            last_warning = f"Weather forecast request failed: {exc}"
            if attempt == 0:
                sleep_fn(0.4)

    return {c: None for c in batch_cells}, last_warning


def fetch_weather_for_cells(
    points: list[tuple[float, float]],
    resolution_deg: float = 0.1,
    session: requests.Session | None = None,
    sleep_fn: Any = time.sleep,
) -> tuple[dict[tuple[float, float], dict[str, Any] | None], list[str]]:
    """Fetch and cache hourly weather series for a set of (lat, lon) points.

    Snaps points to resolution_deg cells, checks cache (keyed by cell + current hour bucket),
    and fetches missing cells in batches of BATCH_SIZE.
    Returns (cell_to_series_dict, warnings_list).
    """
    hour_bucket = int(time.time() // 3600)
    unique_cells: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()

    for lat, lon in points:
        cell = snap_to_weather_cell(lat, lon, resolution_deg=resolution_deg)
        if cell not in seen:
            seen.add(cell)
            unique_cells.append(cell)

    cell_map: dict[tuple[float, float], dict[str, Any] | None] = {}
    uncached: list[tuple[float, float]] = []

    for cell in unique_cells:
        ckey = f"wx:{cell[0]:.2f}:{cell[1]:.2f}:{hour_bucket}"
        cached_val = cache.get(ckey)
        if cached_val is not None:
            cell_map[cell] = cached_val
        else:
            uncached.append(cell)

    warnings: list[str] = []
    if not uncached:
        return cell_map, warnings

    batches = [
        uncached[i : i + BATCH_SIZE] for i in range(0, len(uncached), BATCH_SIZE)
    ]

    if session is not None or len(batches) == 1:
        batch_results = [_fetch_batch(b, session, sleep_fn) for b in batches]
    else:
        with ThreadPoolExecutor(max_workers=min(3, len(batches))) as pool:
            futures = [
                pool.submit(_fetch_batch, b, None, sleep_fn) for b in batches
            ]
            batch_results = [f.result() for f in futures]

    for batch_dict, warn in batch_results:
        if warn and warn not in warnings:
            warnings.append(warn)
        for cell, series in batch_dict.items():
            cell_map[cell] = series
            if series is not None:
                ckey = f"wx:{cell[0]:.2f}:{cell[1]:.2f}:{hour_bucket}"
                cache.set(ckey, series, timeout=3600)

    return cell_map, warnings


def interpolate_weather_at_timestamp(
    series: dict[str, Any] | None,
    target_ts: float,
) -> dict[str, float | None]:
    """Linearly interpolate wind_mph, gust_mph, rain_in_hr, snow_in_hr at target_ts."""
    empty: dict[str, float | None] = {
        "wind_mph": None,
        "gust_mph": None,
        "rain_in_hr": None,
        "snow_in_hr": None,
    }
    if not series:
        return empty

    times: list[int] = series.get("time") or []
    if not times:
        return empty

    if target_ts < times[0] or target_ts > times[-1]:
        return empty

    idx = bisect.bisect_right(times, target_ts) - 1
    idx = min(max(0, idx), len(times) - 1)

    if times[idx] == target_ts or idx == len(times) - 1:
        return {
            "wind_mph": series["wind_mph"][idx],
            "gust_mph": series["gust_mph"][idx],
            "rain_in_hr": series["rain_in_hr"][idx],
            "snow_in_hr": series["snow_in_hr"][idx],
        }

    t0 = times[idx]
    t1 = times[idx + 1]
    span = t1 - t0
    if span <= 0 or span > 10800:
        return empty

    frac = (target_ts - t0) / span

    def _lerp(key: str) -> float | None:
        arr = series.get(key)
        if not arr:
            return None
        v0 = arr[idx]
        v1 = arr[idx + 1]
        if v0 is None or v1 is None:
            return None
        return round(float(v0) + frac * (float(v1) - float(v0)), 4)

    return {
        "wind_mph": _lerp("wind_mph"),
        "gust_mph": _lerp("gust_mph"),
        "rain_in_hr": _lerp("rain_in_hr"),
        "snow_in_hr": _lerp("snow_in_hr"),
    }
