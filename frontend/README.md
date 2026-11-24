# Frontend — Weather-Aware Truck Routing UI

React 18 + TypeScript + Vite + MapLibre GL client for comparing 3 weather-aware truck routes, switching `10 / 25 / 50 mi` sampling intervals instantaneously, inspecting checkpoint weather/load explanations, and scrubbing a 60 FPS `0–48h` corridor weather heatmap.

---

## 1. Structure & Components

```
frontend/
├── index.html
├── vite.config.ts                 # Dev proxy (/api -> http://127.0.0.1:8000) & Vitest config
├── package.json
└── src/
    ├── main.tsx                   # React root mount
    ├── App.tsx                    # App shell, state coordination, error/No-Travel banners, rules modal
    ├── types.ts                   # Shared TypeScript interfaces for TripBundle, RouteSummary, Checkpoint, HeatGrid
    ├── styles.css                 # Dark-theme layout, route cards, overlays, slider styling
    ├── api/
    │   └── client.ts                # Typed fetch wrappers (`searchGeocode`, `planTrip`) + `ApiRequestError`
    ├── hooks/
    │   └── useTripPlanner.ts        # Custom hook owning trip state, API error handling, and selections
    ├── components/
    │   ├── Header.tsx               # Top app bar, speed-cap badge, rules modal trigger
    │   ├── StatusBanners.tsx        # Error alerts, all-route No-Travel advisory, loading skeleton
    │   ├── RulesModal.tsx           # Risk thresholds & load-weight rules reference modal
    │   ├── TripForm.tsx             # Sample freight presets, departure & load validation, 10/25/50 mi toggle
    │   ├── LocationAutocomplete.tsx # Debounced (300 ms) place search backed by /api/geocode
    │   ├── RouteCards.tsx           # Ranked route cards, risk mileage bar, recommendation reasons
    │   ├── CheckpointLogTable.tsx   # Clickable sampled checkpoint weather schedule table
    │   ├── MapView.tsx              # Thin MapLibre GL orchestrator & 60 FPS frame/layer sync
    │   ├── HeatmapControls.tsx      # Metric tabs (Risk/Wind/Rain/Snow), toggle, risk legend
    │   ├── CheckpointModal.tsx      # Floating checkpoint inspector popup card
    │   └── ForecastSlider.tsx       # Bottom 0-48h slider, Play/Pause, live truck position HUD
    ├── utils/
    │   ├── heatmap.ts               # 49-frame canvas PNG rasterizer, color scales, truck interpolator
    │   └── mapLayers.ts             # GeoJSON builders & CARTO raster style config
    └── App.test.tsx                 # Vitest unit + component integration tests
```

---

## 2. Performance & Map Rendering Design

- **Zero-Network Interval Toggle (`10 / 25 / 50 mi`)**: `POST /api/trips` returns checkpoints and ranked summaries for all three sampling intervals in one bundle. Clicking `10 mi`, `25 mi`, or `50 mi` switches in-memory state immediately with zero network requests.
- **WebGL Layers (No DOM Markers)**: Routes (`line`), checkpoints (`circle`), endpoints (`circle`), and live truck positions (`circle`) render inside MapLibre WebGL layers via GeoJSON sources so 500+ checkpoints stay responsive.
- **60 FPS Heatmap Slider (`utils/heatmap.ts` + `MapView.tsx`)**:
  - For each metric (`Combined Risk`, `Wind`, `Rain`, `Snow`), `buildHeatmapFramesForMetric` pre-renders all **49 hourly frames (`0–48h`)** once into small smoothed PNG data URLs with a feathered corridor boundary.
  - Dragging the `0–48h` slider or clicking **Play** updates DOM refs (`+Xh`, UTC timestamp, truck milepost HUD) and calls `ImageSource.updateImage()` + `GeoJSONSource.setData()` inside `requestAnimationFrame` — **without triggering React tree re-renders**.

---

## 3. Environment Variables

- `VITE_API_BASE_URL` (optional): Leave unset in local dev (Vite proxies `/api/*` to `http://127.0.0.1:8000`) and in single-service Render deployment where Django serves `frontend/dist/`. Set this only if deploying the frontend separately (e.g. Vercel → Render API).

---

## 4. Setup, Tests & Build

```bash
cd frontend
npm install

# Run Vitest unit & component tests
npm test

# Typecheck and build production bundle into frontend/dist/
npm run build

# Start Vite dev server on http://localhost:5173
npm run dev
```
