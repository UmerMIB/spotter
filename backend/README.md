# Backend — Weather-Aware Truck Routing API

Django 5 + Django REST Framework API powering route generation, truck speed-capped ETA calculation, batched weather forecasting, risk/load-rule evaluation, and 0–48h corridor heatgrid assembly.

---

## 1. Architecture & Modules

```
backend/
├── config/
│   ├── settings.py        # Env-driven config, CORS, WhiteNoise, LocMemCache (1h TTL)
│   ├── urls.py            # /api/health, /api/geocode, /api/trips, and SPA fallback /
│   └── wsgi.py            # Gunicorn / WSGI entrypoint
├── routing_app/
│   ├── risk.py            # Pure-Python thresholds, load rules, segment miles, ranking
│   ├── geometry.py        # Haversine, polyline6 codec, 65 mph speed cap, 10/25/50 mi resampling, corridor grid
│   ├── pipeline.py        # Input validation + unified trip bundle builder
│   ├── views.py           # DRF endpoints with structured JSON 400/503/500 error responses
│   ├── providers/
│   │   ├── exceptions.py  # ProviderError, GeocodingNotFoundError, RoutingUnavailableError, WeatherProviderError
│   │   ├── geocoding.py   # Photon (Komoot) with US/Canada bias + Nominatim fallback
│   │   ├── routing.py     # OSRM alternatives + perpendicular via-point fallback (0.0, ±14%, ±25%)
│   │   └── weather.py     # Open-Meteo parallel batching (75 cells/call), 0.1° cache, linear ETA interpolation
│   └── tests/             # 85 unit, adapter, and pipeline/API tests
├── requirements.txt
├── pytest.ini
└── manage.py
```

---

## 2. API Endpoints

### `GET /api/health`
Returns service status (`{"status": "ok", "service": "weather-aware-truck-routing"}`).

### `GET /api/geocode?q=<query>`
Proxies Photon with Nominatim fallback, biased to US/Canada, cached for 1 hour.
- **Query params**: `q` (string; queries shorter than 2 characters return `{"results": []}`).
- **Response `200`**: `{"results": [{"label": "Denver, CO, US", "lat": 39.7392, "lon": -104.9903, "country_code": "US", "is_north_america": true}]}`.

### `POST /api/trips`
Computes 3 distinct routes, checkpoints & ranked summaries for **all three intervals (`10`, `25`, `50` mi)**, and the `0–48h` corridor weather grid in one response.
- **Request JSON**:
  ```json
  {
    "origin": "Denver, CO",
    "destination": "Salt Lake City, UT",
    "departure_time": "2026-11-25T14:00:00Z",
    "load_lb": 42000
  }
  ```
  *(Note: `origin` and `destination` also accept `{label, lat, lon}` objects from `/api/geocode`. `departure_time` must be within `[now - 1h, now + 7d]` and `load_lb` within `[0, 80000]`.)*
- **Response `200`**:
  - `request`: validated origin/destination, `departure_utc`, `load_lb`, `truck_max_speed_mph`.
  - `routes[]`: up to 3 routes with `geojson_coords`, `progress_profile`, `distance_mi`, `duration_s`, `eta_utc`, `source` (`"osrm"` or `"via-point"`).
  - `intervals["10" | "25" | "50"]`: `summaries[]` (ranked) and `checkpoints[route_id][]`.
  - `heat_grid`: `{bbox, rows, cols, mask, hours: 49, hour_utc[], cells[{lat, lon, wind[], rain[], snow[], score[]}]}`.
  - `notices[]`: route-count or weather-rate-limit advisories.
- **Error Responses**: `400` (validation / unknown place with `field`), `503` (OSRM unreachable), `500` (unexpected server error with structured JSON `{error, provider}`).

---

## 3. Domain & Provider Logic

- **Truck Speed Cap (`geometry.py`)**: Caps every OSRM segment at `min(osrm_segment_speed, TRUCK_MAX_SPEED_MPH)` (default `65.0 mph`) before computing cumulative checkpoint ETAs.
- **3-Route Guarantee (`providers/routing.py`)**: Requests OSRM `alternatives=3`; if fewer than 3 distinct routes (`< 70%` interior overlap) return, queries perpendicular via-waypoints from the corridor midpoint (`0.0`, `±14%`, `±25%` offsets) and promotes slower distinct candidates up to `1.95x` fastest duration when needed.
- **Weather Sampling (`providers/weather.py`)**: Uses steady `wind_speed_10m` (displays `wind_gusts_10m`), `rain + showers` for liquid rain, and `snowfall` for snow (avoiding `precipitation`, which double-counts snow). Snaps points to `0.1°` cells, deduplicates, caches for 1 hour, and linearly interpolates hourly values at each checkpoint's exact ETA.
- **Pure Risk Engine (`risk.py`)**: Zero-I/O classification, strict load-weight overrides (`>30,000 lb` at `45–54 mph` → `No Travel`; `>40,000 lb` at `35–44 mph` → `Severe`), `Unknown` handling (never treated as `Low`; `< 90%` coverage disqualifies recommendation), and deterministic ranking (`Coverage ≥ 90%` → `No Travel mi` → `Severe mi` → `High mi` → `Avg Risk` → `Travel Time`).

---

## 4. Environment Variables

All defaults work out of the box with free zero-key APIs (see [../.env.example](../.env.example)):
- `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`
- `TRUCK_MAX_SPEED_MPH` (default `65.0`)
- `WEATHER_COVERAGE_THRESHOLD_PCT` (default `90.0`)

---

## 5. Setup, Tests & Lint

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Run all 85 unit, adapter, and pipeline/API tests
.venv/bin/pytest -v

# Lint with Ruff
.venv/bin/ruff check .

# Start development server
.venv/bin/python manage.py runserver 8000
```
