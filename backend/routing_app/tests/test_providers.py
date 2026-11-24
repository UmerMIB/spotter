from __future__ import annotations

from typing import Any

import pytest
from django.core.cache import cache

from routing_app.geometry import (
    apply_truck_speed_cap,
    build_corridor_heatgrid,
    decode_polyline,
    encode_polyline,
    haversine_miles,
    resample_route_checkpoints,
)
from routing_app.providers.exceptions import (
    GeocodingNotFoundError,
    ProviderError,
    RoutingUnavailableError,
)
from routing_app.providers.geocoding import resolve_location, search_places
from routing_app.providers.routing import fetch_three_routes
from routing_app.providers.weather import (
    fetch_weather_for_cells,
    interpolate_weather_at_timestamp,
)


class FakeResponse:
    def __init__(self, status_code: int, json_data: Any = None) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.content = b"{}" if json_data is not None else b""

    def json(self) -> Any:
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, params: Any = None, headers: Any = None, timeout: float = 5.0) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if not self.responses:
            raise AssertionError(f"Unexpected extra call to {url}")
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def clear_django_cache():
    cache.clear()
    yield
    cache.clear()


class TestGeometry:
    def test_polyline6_roundtrip(self):
        pts = [(39.739236, -104.990251), (40.233845, -111.658531), (40.760779, -111.891047)]
        encoded = encode_polyline(pts, precision=6)
        decoded = decode_polyline(encoded, precision=6)
        assert len(decoded) == len(pts)
        for (lat1, lon1), (lat2, lon2) in zip(pts, decoded):
            assert abs(lat1 - lat2) < 1e-5
            assert abs(lon1 - lon2) < 1e-5

    def test_truck_speed_cap_enforces_65_mph_limit(self):
        # 65 miles segment reported by OSRM at 3000s (78 mph car speed) -> capped to 3600s (65 mph)
        coords = [(39.0, -105.0), (39.0, -106.21)]
        dist_m = [65.0 / 0.000621371192]
        dur_s = [3000.0]
        cum_mi, cum_s = apply_truck_speed_cap(
            coords, seg_distances_m=dist_m, seg_durations_s=dur_s, max_speed_mph=65.0
        )
        assert abs(cum_mi[-1] - 65.0) < 0.01
        assert abs(cum_s[-1] - 3600.0) < 0.5

    def test_resample_route_checkpoints_and_corridor_grid(self):
        coords = [(39.74, -104.99), (40.5, -108.0), (40.76, -111.89)]
        d1 = haversine_miles(coords[0][0], coords[0][1], coords[1][0], coords[1][1])
        d2 = haversine_miles(coords[1][0], coords[1][1], coords[2][0], coords[2][1])
        cum_mi = [0.0, d1, d1 + d2]
        cum_s = [0.0, (d1 / 60.0) * 3600.0, ((d1 + d2) / 60.0) * 3600.0]

        cps_25 = resample_route_checkpoints(coords, cum_mi, cum_s, interval_mi=25, departure_ts=1700000000.0)
        assert cps_25[0]["mile"] == 0.0
        assert cps_25[1]["mile"] == 25.0
        assert abs(cps_25[-1]["mile"] - (d1 + d2)) < 0.05
        assert cps_25[-1]["eta_ts"] > cps_25[0]["eta_ts"]

        grid = build_corridor_heatgrid([coords], max_active_cells=180)
        assert len(grid["active_cells"]) <= 180
        assert len(grid["active_cells"]) > 10
        assert len(grid["mask"]) == grid["rows"] * grid["cols"]


class TestGeocodingAdapter:
    def test_photon_success_and_caching(self):
        photon_payload = {
            "features": [
                {
                    "geometry": {"coordinates": [-104.9903, 39.7392]},
                    "properties": {"name": "Denver", "state": "Colorado", "countrycode": "US"},
                }
            ]
        }
        session = FakeSession([FakeResponse(200, photon_payload)])
        res1 = resolve_location("Denver, CO", field_name="origin", session=session, sleep_fn=lambda _: None)
        assert res1["lat"] == 39.7392
        assert res1["lon"] == -104.9903
        assert "Denver" in res1["label"]
        assert len(session.calls) == 1

        # Second call hits cache without extra HTTP call
        res2 = resolve_location("denver, co", field_name="origin", session=session, sleep_fn=lambda _: None)
        assert res2 == res1
        assert len(session.calls) == 1

    def test_falls_back_to_nominatim_when_photon_rate_limited(self):
        nominatim_payload = [
            {"lat": "40.7608", "lon": "-111.8910", "display_name": "Salt Lake City, Utah, US"}
        ]
        session = FakeSession(
            [
                FakeResponse(429, {}),  # Photon attempt 1
                FakeResponse(429, {}),  # Photon attempt 2
                FakeResponse(200, nominatim_payload),  # Nominatim fallback
            ]
        )
        results = search_places("Salt Lake City", session=session, sleep_fn=lambda _: None)
        assert len(results) == 1
        assert results[0]["lat"] == 40.7608
        assert len(session.calls) == 3

    def test_empty_result_raises_geocoding_not_found(self):
        session = FakeSession([FakeResponse(200, {"features": []})])
        with pytest.raises(GeocodingNotFoundError) as exc_info:
            resolve_location("NonexistentPlaceXYZ123", field_name="destination", session=session)
        assert exc_info.value.field == "destination"

    def test_both_providers_failing_raises_503(self):
        session = FakeSession(
            [
                FakeResponse(503, {}),
                FakeResponse(503, {}),
                FakeResponse(503, {}),
            ]
        )
        with pytest.raises(ProviderError) as exc_info:
            search_places("Chicago, IL", session=session, sleep_fn=lambda _: None)
        assert exc_info.value.status_code == 503


class TestRoutingAdapter:
    def _make_osrm_route(self, coords: list[tuple[float, float]], distance_m: float = 500000.0, duration_s: float = 25000.0) -> dict[str, Any]:
        return {
            "geometry": encode_polyline(coords, precision=6),
            "distance": distance_m,
            "duration": duration_s,
            "legs": [],
        }

    def test_via_point_fallback_produces_three_distinct_routes(self):
        origin = (39.7392, -104.9903)
        dest = (40.7608, -111.8910)
        direct_coords = [origin, (40.2, -108.5), dest]
        north_coords = [origin, (41.6, -108.5), dest]
        south_coords = [origin, (38.5, -108.5), dest]

        session = FakeSession(
            [
                # Primary request returns only 1 route
                FakeResponse(200, {"code": "Ok", "routes": [self._make_osrm_route(direct_coords)]}),
                # First perpendicular via-point returns Northern corridor
                FakeResponse(200, {"code": "Ok", "routes": [self._make_osrm_route(north_coords, 540000.0, 27000.0)]}),
                # Second perpendicular via-point returns Southern corridor
                FakeResponse(200, {"code": "Ok", "routes": [self._make_osrm_route(south_coords, 560000.0, 28000.0)]}),
            ]
        )

        routes, notices = fetch_three_routes(origin, dest, session=session, sleep_fn=lambda _: None)
        assert len(routes) == 3
        assert notices == []
        assert routes[0]["source"] == "osrm"
        assert routes[1]["source"] == "via-point"
        assert routes[2]["source"] == "via-point"
        assert [r["id"] for r in routes] == ["route_a", "route_b", "route_c"]

    def test_via_point_promotes_slower_distinct_fallback_up_to_1_95x(self):
        origin = (39.7392, -104.9903)
        dest = (40.7608, -111.8910)
        direct_coords = [origin, (41.4, -108.5), dest]
        mid_coords = [origin, (40.25, -108.5), dest]
        south_coords = [origin, (38.9, -108.5), dest]

        session = FakeSession(
            [
                # Primary route: 30,000s
                FakeResponse(200, {"code": "Ok", "routes": [self._make_osrm_route(direct_coords, 500000.0, 30000.0)]}),
                # Via 1 (0.0): 1.2x (accepted immediately)
                FakeResponse(200, {"code": "Ok", "routes": [self._make_osrm_route(mid_coords, 520000.0, 36000.0)]}),
                # Via 2 (+0.14): duplicates direct
                FakeResponse(200, {"code": "Ok", "routes": [self._make_osrm_route(direct_coords, 505000.0, 31000.0)]}),
                # Via 3 (-0.14): 1.70x -> held in slow_fallbacks, promoted after loop
                FakeResponse(200, {"code": "Ok", "routes": [self._make_osrm_route(south_coords, 600000.0, 51000.0)]}),
                # Via 4 (+0.25) & Via 5 (-0.25): empty/duplicate
                FakeResponse(200, {"code": "Ok", "routes": [self._make_osrm_route(direct_coords, 510000.0, 32000.0)]}),
                FakeResponse(200, {"code": "Ok", "routes": [self._make_osrm_route(mid_coords, 525000.0, 37000.0)]}),
            ]
        )

        routes, notices = fetch_three_routes(origin, dest, session=session, sleep_fn=lambda _: None)
        assert len(routes) == 3
        assert notices == []
        assert [r["id"] for r in routes] == ["route_a", "route_b", "route_c"]

    def test_osrm_down_retries_and_raises_503(self):
        session = FakeSession(
            [
                FakeResponse(503, {}),
                FakeResponse(503, {}),
                FakeResponse(503, {}),
            ]
        )
        with pytest.raises(RoutingUnavailableError):
            fetch_three_routes(
                (39.74, -104.99),
                (40.76, -111.89),
                session=session,
                sleep_fn=lambda _: None,
            )
        assert len(session.calls) == 3


class TestWeatherAdapter:
    def test_batch_deduplication_caching_and_interpolation(self):
        hourly_payload = {
            "hourly": {
                "time": [1700000000, 1700003600, 1700007200],
                "wind_speed_10m": [20.0, 40.0, 50.0],
                "wind_gusts_10m": [28.0, 52.0, 62.0],
                "rain": [0.0, 0.20, 0.40],
                "showers": [0.0, 0.10, 0.10],
                "snowfall": [0.0, 1.0, 2.0],
            }
        }
        session = FakeSession([FakeResponse(200, hourly_payload)])
        # Two nearby points that snap to the exact same 0.1 deg cell (39.7, -105.0)
        pts = [(39.71, -104.99), (39.74, -105.02)]
        cell_map, warnings = fetch_weather_for_cells(pts, session=session, sleep_fn=lambda _: None)
        assert warnings == []
        assert len(session.calls) == 1
        series = cell_map[(39.7, -105.0)]
        assert series is not None
        # Rain combines rain + showers
        assert series["rain_in_hr"] == [0.0, 0.30, 0.50]

        # Re-fetching hits cache with 0 new HTTP requests
        cell_map_2, _ = fetch_weather_for_cells(pts, session=session, sleep_fn=lambda _: None)
        assert len(session.calls) == 1
        assert cell_map_2 == cell_map

        # Interpolate halfway between hour 0 (1700000000) and hour 1 (1700003600)
        interp = interpolate_weather_at_timestamp(series, 1700001800.0)
        assert interp["wind_mph"] == 30.0
        assert interp["gust_mph"] == 40.0
        assert interp["rain_in_hr"] == 0.15
        assert interp["snow_in_hr"] == 0.5

        # Out-of-range timestamp returns None (never Low)
        out_of_range = interpolate_weather_at_timestamp(series, 1800000000.0)
        assert out_of_range["wind_mph"] is None
        assert out_of_range["rain_in_hr"] is None
        assert out_of_range["snow_in_hr"] is None

    def test_rate_limit_or_malformed_marks_cells_none_with_warning(self):
        session = FakeSession(
            [
                FakeResponse(429, {}),
                FakeResponse(429, {}),
            ]
        )
        cell_map, warnings = fetch_weather_for_cells(
            [(39.7, -105.0)], session=session, sleep_fn=lambda _: None
        )
        assert cell_map[(39.7, -105.0)] is None
        assert len(warnings) == 1
        assert "429" in warnings[0]
