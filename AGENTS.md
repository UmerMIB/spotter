# AGENTS.md: Weather-Aware Truck Routing

Instructions for any AI agent working in this repo. Read this file before you change anything.

## 1. What we are building

A **React + Django** web app that helps a truck driver pick the safest route, based on weather, load weight and travel time.
This is a take-home assessment for Spotter (Full Stack Developer). The source brief is `docs/brief.pdf` (copy it there if it's missing).

**User inputs:** origin, destination, departure date/time, load weight (lb).

**The app must:**
1. Generate **3 route options** using a routing API.
2. Sample weather every **10 / 25 / 50 miles**, using the truck's **estimated arrival time at each checkpoint** (not the departure time).
3. Calculate weather risk using the risk and load rules below.
4. Recommend the best route, balancing weather risk and travel time.
5. Show all routes, checkpoints, risk levels, ETAs and route summaries on a map.
6. Show a **weather heatmap along the trip corridor** with a **0–48 hour forecast slider**.

**Deliverables:** GitHub repo, hosted app.

**Evaluation weights:** keep these in mind when deciding where to spend effort.
| Weight | Area |
|---|---|
| 40% | Routes, weather, risk & recommendation logic |
| 40% | UI, map & heatmap smoothness and performance |
| 15% | Code quality |
| 5% | Documentation & walkthrough |

> **Prioritize correctness and clarity over extra features.** Don't add scope that the brief doesn't ask for.

## 2. Domain rules (source of truth)

### 2.1 Risk thresholds per checkpoint
| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | < 25 | 25–34 | 35–44 | 45–54 | ≥ 55 |
| Rain (in/hr) | < 0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow (in/hr) | < 0.5 | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

**Boundary convention.** The brief's ranges overlap at their edges, so this is our decision and it must be documented in the README:
- Wind: `[0,25) Low`, `[25,35) Moderate`, `[35,45) High`, `[45,55) Severe`, `≥55 No Travel`.
- Rain: `[0,0.10) Low`, `[0.10,0.25) Moderate`, `[0.25,0.50) High`, `[0.50,1.00] Severe`, `>1.00 No Travel`.
- Snow: `[0,0.5) Low`, `[0.5,1.0) Moderate`, `[1.0,2.0) High`, `[2.0,3.0] Severe`, `>3.0 No Travel`.

### 2.2 Load rules (applied to wind)
- Wind ≥ 55 mph → **No Travel**, whatever the load.
- Wind 45–54 mph **and** load > 30,000 lb → **No Travel**.
- Wind 35–44 mph **and** load > 40,000 lb → **Severe**.
- Load comparisons are strict (`>`). A load of exactly 30,000 lb doesn't trigger the rule.

### 2.3 Checkpoint risk
- Overall checkpoint risk = **the highest level** across wind (after load rules), rain and snow.
- Numeric score: `Low=1, Moderate=2, High=3, Severe=4, No Travel=5`.
- Every checkpoint keeps its contributing factors (e.g. "Wind 47 mph + 42,000 lb load"), so the UI can explain each level.

### 2.4 Route segment miles
- Each checkpoint represents the route miles around it, so "Severe miles" = the sum of segment lengths whose checkpoint risk is Severe. Use the same rule for every level.

### 2.5 Recommendation ranking (agreed with user)
The brief lists 4 criteria. We add **No Travel** in front of them, because a route that crosses No Travel conditions must never be recommended ahead of a route that doesn't.
- A checkpoint with missing weather data is marked **Unknown** (never Low).
- `avg_score` is computed over known miles only, and `coverage_pct` is reported for each route.
- Any route with `< 90%` known weather coverage is ineligible for recommendation unless all routes are `< 90%` (in which case no recommendation is made and a warning is shown).
- Among eligible routes, rank by:
  1. Fewest **No Travel** miles (any route with them gets a visible warning)
  2. Fewest **Severe** miles
  3. Fewest **High** miles
  4. Lowest **average risk score** (distance-weighted over known miles)
  5. Shortest **travel time**

Explain this decision in the README and in the UI ("why this route").

## 3. Agreed decisions

| Topic | Decision |
|---|---|
| Stack | Django (+ DRF) backend, React (Vite + TypeScript) frontend |
| Cost | **Free providers only, no paid API keys** |
| Weather | Open-Meteo (`wind_speed_unit=mph`, `precipitation_unit=inch`). Classify wind on steady `wind_speed_10m` (and display `wind_gusts_10m` in checkpoint details). Use `rain + showers` for rain and `snowfall` for snow. Don't use `precipitation`, because it already includes snow. |
| Routing | OSRM (`alternatives=3`, `annotations=distance,duration`, `geometries=polyline6`). Ask for native alternatives first. If fewer than 3 distinct routes (<70% overlap) come back, add perpendicular via-point offsets (`±15%`, `±30%` of route length) at the midpoint so we get 3 distinct drivable routes. |
| Truck ETA | Apply a configurable truck speed cap (`min(osrm_segment_speed, 65 mph)`) on each road segment when computing cumulative durations and checkpoint ETAs. Raw drive time (no HOS break insertion). |
| Geocoding | Photon (Komoot) with Nominatim fallback via `/api/geocode`, biased toward US/Canada. Send a proper User-Agent and respect rate limits + caching. |
| Map | MapLibre GL with free CARTO/OSM vector tiles; routes, checkpoints, truck markers, and 0–48h pre-rendered heatmap image frames drawn on WebGL layers. |
| Sampling interval | Backend returns all three (`10`, `25`, `50` mi) in one trip bundle; frontend toggle (**default 25 mi**) switches instantaneously without network calls. |
| Heatmap | Prefetch hourly 0–48h forecasts (from departure time) for an adaptive corridor grid (~250 cells within ~40 mi of routes), pre-rendering 49×4 hourly images so dragging the slider is 60 fps with zero React re-renders. Metric switcher: Risk / Wind / Rain / Snow. Show animated truck position markers at hour `+T`. |
| Hosting | Single Render service (or Docker container) where Django serves the API and built React static assets via WhiteNoise, plus CORS support for local Vite dev or split Vercel/Render deployment. |

## 4. How to work in this repo

Use the skills in `.agents/skills/` in this order:
1. `challenge-the-brief`: before any new task.
2. `plan-before-build`: give options, wait for the user to choose, write the plan in slices. **Don't write code until the plan is approved.**
3. Build one slice at a time.
4. `review-like-a-sceptic`: after code is written. Show real test output and never claim success without evidence.
5. `production-check`: when a feature is finished.

### Rules
- **Risk logic is pure and tested.** Classification, load rules, segment miles and ranking go in plain Python functions with no I/O, covered by unit tests. Test every boundary value in §2.1–2.2.
- **Providers sit behind adapters** (`routing`, `geocoding`, `weather`), so they can be swapped or mocked. No provider calls in views or React components.
- **Timeouts, retries and caching on every external call.** Cache weather by rounded lat/lon + hour. Batch Open-Meteo requests (it accepts multiple coordinates in one call).
- **Fail clearly.** If a provider is down, rate-limited or returns empty or malformed data, return a clear error and show it in the UI. Never show missing weather as "Low" risk.
- **Units:** store miles, mph and in/hr internally; keep times in UTC and convert only for display.
- **No secrets in code.** Put config in `.env` (commit `.env.example`).
- **Frontend performance is graded (40%).** Memoize map layers and don't re-render the map on slider changes. The slider should only swap prebuilt heatmap frames.
- Keep things small and readable. No speculative features.

## 5. Layout & commands

```
backend/
  config/           Django settings, urls, wsgi
  routing_app/
    risk.py         Pure-Python risk classification, load rules, segment miles, ranking
    geometry.py     Haversine, polyline6, resampling at 10/25/50 mi, truck speed cap, corridor grid
    providers/      Adapters for geocoding (Photon/Nominatim), routing (OSRM + via-points), weather (Open-Meteo batch)
    pipeline.py     Trip assembly pipeline combining routes, checkpoints, risk summaries, and 0-48h heatgrid
    views.py        /api/health, /api/geocode, /api/trips
    tests/          Unit and adapter/endpoint tests
frontend/
  src/
    api/            Typed client for /api/geocode and /api/trips
    components/     TripForm, RouteCards, MapView (MapLibre + 60fps heatmap), ForecastSlider, CheckpointModal
    utils/          Heatmap frame rasterizer, truck position interpolator, formatting
docs/               brief.pdf
```

**Commands:**
- Backend tests: `cd backend && .venv/bin/pytest -v`
- Backend dev server: `cd backend && .venv/bin/python manage.py runserver 8000`
- Frontend tests: `cd frontend && npm test`
- Frontend build: `cd frontend && npm run build`
- Frontend dev server: `cd frontend && npm run dev`
