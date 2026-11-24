from __future__ import annotations

import gzip
import json
from typing import Any
from unittest.mock import patch

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from routing_app.geometry import encode_polyline
from routing_app.pipeline import build_trip_bundle
from routing_app.tests.test_providers import FakeResponse, FakeSession


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def _make_mock_trip_session(base_ts: int) -> FakeSession:
    origin = (39.7392, -104.9903)
    dest = (40.7608, -111.8910)

    r1_coords = [origin, (41.14, -107.5), dest]  # Northern route (windy)
    r2_coords = [origin, (39.80, -108.2), dest]  # Central route (calm)
    r3_coords = [origin, (38.50, -108.5), dest]  # Southern route (moderate)

    osrm_payload = {
        "code": "Ok",
        "routes": [
            {
                "geometry": encode_polyline(r1_coords, 6),
                "distance": 830000.0,
                "duration": 29000.0,
                "legs": [],
            },
            {
                "geometry": encode_polyline(r2_coords, 6),
                "distance": 850000.0,
                "duration": 30500.0,
                "legs": [],
            },
            {
                "geometry": encode_polyline(r3_coords, 6),
                "distance": 910000.0,
                "duration": 32500.0,
                "legs": [],
            },
        ],
    }

    times = [base_ts + h * 3600 for h in range(72)]

    class DynamicOpenMeteoSession(FakeSession):
        def get(self, url: str, params: Any = None, headers: Any = None, timeout: float = 5.0) -> FakeResponse:
            self.calls.append({"url": url, "params": params})
            if "route/v1/driving" in url:
                return FakeResponse(200, osrm_payload)
            if "forecast" in url:
                lats = [float(x) for x in str(params["latitude"]).split(",")]
                items = []
                for lat in lats:
                    # Make northern latitude (>40.8) experience 48 mph wind (triggers No Travel when load > 30,000 lb)
                    w = 48.0 if lat > 40.8 else 15.0
                    items.append(
                        {
                            "hourly": {
                                "time": times,
                                "wind_speed_10m": [w] * len(times),
                                "wind_gusts_10m": [w + 10.0] * len(times),
                                "rain": [0.02] * len(times),
                                "showers": [0.0] * len(times),
                                "snowfall": [0.0] * len(times),
                            }
                        }
                    )
                return FakeResponse(200, items[0] if len(items) == 1 else items)
            raise AssertionError(f"Unexpected URL {url}")

    return DynamicOpenMeteoSession([])


class TestTripPipelineAndAPI:
    def test_denver_to_slc_full_bundle_and_payload_budget(self):
        now_ts = 1795305600.0  # 2026-11-22T00:00:00Z
        dep_iso = "2026-11-22T02:00:00Z"
        session = _make_mock_trip_session(int(now_ts) - 3600)

        bundle = build_trip_bundle(
            {
                "origin": {"label": "Denver, CO, US", "lat": 39.7392, "lon": -104.9903},
                "destination": {"label": "Salt Lake City, UT, US", "lat": 40.7608, "lon": -111.8910},
                "departure_time": dep_iso,
                "load_lb": 42000,
            },
            session=session,
            now_ts=now_ts,
            sleep_fn=lambda _: None,
        )

        assert len(bundle["routes"]) == 3
        assert set(bundle["intervals"].keys()) == {"10", "25", "50"}

        # Check 25-mile interval recommendation: Route A (Northern, lat 41.14) has 48 mph wind + 42,000 lb -> No Travel!
        # Therefore Route B (Central, calm) must be recommended ahead of Route A despite Route A being faster.
        summaries_25 = bundle["intervals"]["25"]["summaries"]
        assert summaries_25[0]["recommended"] is True
        assert summaries_25[0]["route_id"] != "route_a"
        route_a_summary = next(s for s in summaries_25 if s["route_id"] == "route_a")
        assert route_a_summary["has_no_travel"] is True
        assert route_a_summary["miles_by_level"]["No Travel"] > 0

        # Check heat_grid has 49 hours and active cells
        hg = bundle["heat_grid"]
        assert hg["hours"] == 49
        assert len(hg["hour_utc"]) == 49
        assert len(hg["cells"]) > 10
        assert len(hg["cells"][0]["score"]) == 49

        # Check gzipped payload size budget (< 400 KB)
        raw_bytes = json.dumps(bundle).encode("utf-8")
        gz_bytes = gzip.compress(raw_bytes)
        assert len(gz_bytes) < 400 * 1024

    def test_load_weight_changes_risk_without_altering_travel_time(self):
        now_ts = 1795305600.0
        dep_iso = "2026-11-22T02:00:00Z"

        light_bundle = build_trip_bundle(
            {
                "origin": {"label": "Denver, CO, US", "lat": 39.7392, "lon": -104.9903},
                "destination": {"label": "Salt Lake City, UT, US", "lat": 40.7608, "lon": -111.8910},
                "departure_time": dep_iso,
                "load_lb": 20000,
            },
            session=_make_mock_trip_session(int(now_ts) - 3600),
            now_ts=now_ts,
            sleep_fn=lambda _: None,
        )
        heavy_bundle = build_trip_bundle(
            {
                "origin": {"label": "Denver, CO, US", "lat": 39.7392, "lon": -104.9903},
                "destination": {"label": "Salt Lake City, UT, US", "lat": 40.7608, "lon": -111.8910},
                "departure_time": dep_iso,
                "load_lb": 42000,
            },
            session=_make_mock_trip_session(int(now_ts) - 3600),
            now_ts=now_ts,
            sleep_fn=lambda _: None,
        )

        # Travel time, distance, and ETAs must be identical regardless of load weight
        for r_light, r_heavy in zip(light_bundle["routes"], heavy_bundle["routes"]):
            assert r_light["distance_mi"] == r_heavy["distance_mi"]
            assert r_light["duration_s"] == r_heavy["duration_s"]
            assert r_light["eta_utc"] == r_heavy["eta_utc"]

        for rid in ("route_a", "route_b", "route_c"):
            cps_light = light_bundle["intervals"]["25"]["checkpoints"][rid]
            cps_heavy = heavy_bundle["intervals"]["25"]["checkpoints"][rid]
            assert [c["eta_ts"] for c in cps_light] == [c["eta_ts"] for c in cps_heavy]

        # Under 20,000 lb, 48 mph wind on route_a is Severe (no No Travel),
        # whereas under 42,000 lb (>30,000 lb) it escalates to No Travel.
        ra_light = next(
            s for s in light_bundle["intervals"]["25"]["summaries"] if s["route_id"] == "route_a"
        )
        ra_heavy = next(
            s for s in heavy_bundle["intervals"]["25"]["summaries"] if s["route_id"] == "route_a"
        )
        assert ra_light["has_no_travel"] is False
        assert ra_light["miles_by_level"]["Severe"] > 0
        assert ra_heavy["has_no_travel"] is True
        assert ra_heavy["miles_by_level"]["No Travel"] > 0

    def test_api_endpoints_and_validation_errors(self):
        client = APIClient()

        # 1. Health endpoint
        h_resp = client.get("/api/health")
        assert h_resp.status_code == 200
        assert h_resp.json()["status"] == "ok"

        # 2. Past departure time rejected with 400 + field='departure_time'
        resp_past = client.post(
            "/api/trips",
            data={
                "origin": "39.7392, -104.9903",
                "destination": "40.7608, -111.8910",
                "departure_time": "2020-01-01T00:00:00Z",
                "load_lb": 35000,
            },
            format="json",
        )
        assert resp_past.status_code == 400
        assert resp_past.json()["field"] == "departure_time"

        # 3. Invalid load weight rejected with 400 + field='load_lb'
        now_ts = 1795305600.0
        with patch("routing_app.pipeline.time.time", return_value=now_ts):
            resp_load = client.post(
                "/api/trips",
                data={
                    "origin": "39.7392, -104.9903",
                    "destination": "40.7608, -111.8910",
                    "departure_time": "2026-11-22T02:00:00Z",
                    "load_lb": 95000,
                },
                format="json",
            )
            assert resp_load.status_code == 400
            assert resp_load.json()["field"] == "load_lb"

        # 4. Geocode short query returns empty list
        geo_short = client.get("/api/geocode", {"q": "a"})
        assert geo_short.status_code == 200
        assert geo_short.json()["results"] == []
