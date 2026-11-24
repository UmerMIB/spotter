from __future__ import annotations

import hashlib
import re
import time
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache

from routing_app.providers.exceptions import GeocodingNotFoundError, ProviderError

COORD_RE = re.compile(
    r"^\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*$"
)

NORTH_AMERICA_COUNTRIES = {"US", "CA", "United States", "United States of America", "Canada"}


def _cache_key(prefix: str, query: str) -> str:
    norm = " ".join(query.strip().lower().split())
    digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:24]
    return f"geo:{prefix}:{digest}"


def _format_photon_label(props: dict[str, Any]) -> str:
    parts: list[str] = []
    name = props.get("name")
    city = props.get("city") or props.get("town") or props.get("county")
    state = props.get("state")
    country = props.get("countrycode") or props.get("country")

    if name:
        parts.append(str(name))
    if city and city != name:
        parts.append(str(city))
    if state and state not in parts:
        parts.append(str(state))
    if country and country not in parts:
        parts.append(str(country))
    return ", ".join(parts) if parts else "Unknown Location"


def _parse_photon_features(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        raise TypeError("Malformed Photon response: expected JSON object")
    features = data.get("features")
    if not isinstance(features, list):
        raise TypeError("Malformed Photon response: missing features list")

    results: list[dict[str, Any]] = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates")
        if (
            not isinstance(coords, list)
            or len(coords) < 2
            or not isinstance(coords[0], (int, float))
            or not isinstance(coords[1], (int, float))
        ):
            continue
        lon, lat = float(coords[0]), float(coords[1])
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            continue
        props = feat.get("properties") or {}
        country_code = str(props.get("countrycode") or "").upper()
        country = str(props.get("country") or "")
        is_na = country_code in NORTH_AMERICA_COUNTRIES or country in NORTH_AMERICA_COUNTRIES
        results.append(
            {
                "label": _format_photon_label(props),
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "country_code": country_code or country,
                "is_north_america": is_na,
            }
        )

    # Bias US/Canada results to the front while preserving relative relevance order
    results.sort(key=lambda r: (0 if r["is_north_america"] else 1))
    return results


def _parse_nominatim_items(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise TypeError("Malformed Nominatim response: expected JSON list")
    results: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            lat = float(item["lat"])
            lon = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            continue
        label = str(item.get("display_name") or f"{lat:.4f}, {lon:.4f}")
        results.append(
            {
                "label": label,
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "country_code": "US",
                "is_north_america": True,
            }
        )
    return results


def search_places(
    query: str,
    limit: int = 5,
    session: requests.Session | None = None,
    sleep_fn: Any = time.sleep,
) -> list[dict[str, Any]]:
    """Search for places matching query using Photon with Nominatim fallback."""
    cleaned = (query or "").strip()
    if not cleaned:
        return []

    coord_match = COORD_RE.match(cleaned)
    if coord_match:
        lat = float(coord_match.group(1))
        lon = float(coord_match.group(2))
        if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
            return [
                {
                    "label": f"{lat:.4f}, {lon:.4f}",
                    "lat": round(lat, 5),
                    "lon": round(lon, 5),
                    "country_code": "",
                    "is_north_america": True,
                }
            ]

    ckey = _cache_key(f"search:{limit}", cleaned)
    cached = cache.get(ckey)
    if cached is not None:
        return cached

    http = session or requests.Session()
    headers = {"User-Agent": settings.HTTP_USER_AGENT}
    last_error: Exception | None = None

    # 1. Try Photon (with 2 attempts on transient failure)
    for attempt in range(2):
        try:
            resp = http.get(
                settings.PHOTON_BASE_URL,
                params={
                    "q": cleaned,
                    "limit": max(limit * 2, 8),
                    "lang": "en",
                    "lat": 39.8283,
                    "lon": -98.5795,
                },
                headers=headers,
                timeout=5.0,
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = ProviderError(
                    f"Photon returned HTTP {resp.status_code}",
                    provider="geocoding",
                    status_code=503,
                )
                if attempt == 0:
                    sleep_fn(0.25)
                    continue
                break
            resp.raise_for_status()
            parsed = _parse_photon_features(resp.json())[:limit]
            cache.set(ckey, parsed, timeout=3600)
            return parsed
        except (requests.RequestException, ValueError, TypeError) as exc:
            last_error = exc
            if attempt == 0:
                sleep_fn(0.25)

    # 2. Fallback to Nominatim
    try:
        resp = http.get(
            settings.NOMINATIM_BASE_URL,
            params={
                "q": cleaned,
                "format": "jsonv2",
                "countrycodes": "us,ca",
                "limit": limit,
            },
            headers=headers,
            timeout=5.0,
        )
        if resp.status_code == 429 or resp.status_code >= 500:
            raise ProviderError(
                f"Geocoding service unavailable (HTTP {resp.status_code})",
                provider="geocoding",
                status_code=503,
            )
        resp.raise_for_status()
        parsed = _parse_nominatim_items(resp.json())[:limit]
        cache.set(ckey, parsed, timeout=3600)
        return parsed
    except ProviderError:
        raise
    except (requests.RequestException, ValueError, TypeError) as exc:
        raise ProviderError(
            f"Geocoding service unavailable: {last_error or exc}",
            provider="geocoding",
            status_code=503,
        ) from exc


def resolve_location(
    location_input: str | dict[str, Any],
    field_name: str = "location",
    session: requests.Session | None = None,
    sleep_fn: Any = time.sleep,
) -> dict[str, Any]:
    """Resolve an origin/destination string or {label, lat, lon} dict to validated coordinates."""
    if isinstance(location_input, dict):
        lat = location_input.get("lat")
        lon = location_input.get("lon")
        label = str(location_input.get("label") or "").strip()
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            f_lat, f_lon = float(lat), float(lon)
            if -90.0 <= f_lat <= 90.0 and -180.0 <= f_lon <= 180.0:
                return {
                    "label": label or f"{f_lat:.4f}, {f_lon:.4f}",
                    "lat": round(f_lat, 5),
                    "lon": round(f_lon, 5),
                }
        if label:
            location_input = label
        else:
            raise GeocodingNotFoundError(
                f"Invalid coordinates or empty address for {field_name}.",
                field=field_name,
            )

    if not isinstance(location_input, str) or not location_input.strip():
        raise GeocodingNotFoundError(
            f"Please enter a valid {field_name} city or address.",
            field=field_name,
        )

    matches = search_places(
        location_input, limit=3, session=session, sleep_fn=sleep_fn
    )
    if not matches:
        raise GeocodingNotFoundError(
            f"Could not find location '{location_input.strip()}'. Try a city and state (e.g. 'Denver, CO').",
            field=field_name,
        )

    top = matches[0]
    return {
        "label": top["label"],
        "lat": top["lat"],
        "lon": top["lon"],
    }
