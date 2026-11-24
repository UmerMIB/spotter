import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import type { TripBundle } from "./types";
import {
  buildHeatmapFramesForMetric,
  cellColorForMetric,
  interpolateTruckPositionsAtHour,
} from "./utils/heatmap";

// Mock maplibre-gl so jsdom tests run cleanly without WebGL context
vi.mock("maplibre-gl", () => {
  class MockMap {
    on() {}
    remove() {}
    addControl() {}
    getSource() {
      return undefined;
    }
    getLayer() {
      return undefined;
    }
    fitBounds() {}
    easeTo() {}
  }
  class MockNavigationControl {}
  return {
    default: {
      Map: MockMap,
      NavigationControl: MockNavigationControl,
    },
  };
});

const MOCK_BUNDLE: TripBundle = {
  request: {
    origin: { label: "Denver, CO, US", lat: 39.7392, lon: -104.9903 },
    destination: { label: "Salt Lake City, UT, US", lat: 40.7608, lon: -111.891 },
    departure_utc: "2026-11-22T06:00:00Z",
    departure_ts: 1795327200,
    load_lb: 42000,
    truck_max_speed_mph: 65,
    default_interval_mi: 25,
  },
  routes: [
    {
      id: "route_a",
      name: "Route A (Primary Direct)",
      source: "osrm",
      polyline: "mockpolyA",
      geojson_coords: [
        [-104.99, 39.74],
        [-108.5, 41.1],
        [-111.89, 40.76],
      ],
      progress_profile: [
        [0, 0, 39.74, -104.99],
        [250, 14400, 41.1, -108.5],
        [500, 28800, 40.76, -111.89],
      ],
      distance_mi: 500,
      duration_s: 28800,
      eta_utc: "2026-11-22T14:00:00Z",
    },
    {
      id: "route_b",
      name: "Route B (Southern Corridor)",
      source: "via-point",
      polyline: "mockpolyB",
      geojson_coords: [
        [-104.99, 39.74],
        [-108.5, 39.1],
        [-111.89, 40.76],
      ],
      progress_profile: [
        [0, 0, 39.74, -104.99],
        [260, 15000, 39.1, -108.5],
        [520, 30000, 40.76, -111.89],
      ],
      distance_mi: 520,
      duration_s: 30000,
      eta_utc: "2026-11-22T14:20:00Z",
    },
  ],
  intervals: {
    "10": {
      summaries: [
        {
          route_id: "route_b",
          route_name: "Route B (Southern Corridor)",
          interval_mi: 10,
          distance_mi: 520,
          duration_s: 30000,
          miles_by_level: {
            Low: 520,
            Moderate: 0,
            High: 0,
            Severe: 0,
            "No Travel": 0,
            Unknown: 0,
          },
          avg_score: 1.0,
          coverage_pct: 100,
          has_no_travel: false,
          warnings: [],
          rank: 1,
          recommended: true,
          deciding_criterion: "no_travel_miles",
          reasons: ["Fewest No Travel miles (0.0 mi vs 120.0 mi on Route A)"],
        },
      ],
      checkpoints: {
        route_b: [
          {
            index: 0,
            route_id: "route_b",
            route_name: "Route B (Southern Corridor)",
            interval_mi: 10,
            mile: 0,
            segment_miles: 10,
            lat: 39.74,
            lon: -104.99,
            elapsed_s: 0,
            eta_ts: 1795327200,
            eta_utc: "2026-11-22T06:00:00Z",
            wind_mph: 14,
            gust_mph: 20,
            rain_in_hr: 0,
            snow_in_hr: 0,
            wind_level: "Low",
            rain_level: "Low",
            snow_level: "Low",
            level: "Low",
            score: 1,
            load_rule_triggered: false,
            factors: ["Calm conditions"],
          },
        ],
      },
    },
    "25": {
      summaries: [
        {
          route_id: "route_b",
          route_name: "Route B (Southern Corridor)",
          interval_mi: 25,
          distance_mi: 520,
          duration_s: 30000,
          miles_by_level: {
            Low: 520,
            Moderate: 0,
            High: 0,
            Severe: 0,
            "No Travel": 0,
            Unknown: 0,
          },
          avg_score: 1.0,
          coverage_pct: 100,
          has_no_travel: false,
          warnings: [],
          rank: 1,
          recommended: true,
          deciding_criterion: "no_travel_miles",
          reasons: ["Fewest No Travel miles (0.0 mi vs 120.0 mi on Route A)"],
        },
        {
          route_id: "route_a",
          route_name: "Route A (Primary Direct)",
          interval_mi: 25,
          distance_mi: 500,
          duration_s: 28800,
          miles_by_level: {
            Low: 380,
            Moderate: 0,
            High: 0,
            Severe: 0,
            "No Travel": 120,
            Unknown: 0,
          },
          avg_score: 1.96,
          coverage_pct: 100,
          has_no_travel: true,
          warnings: [
            "NO TRAVEL HAZARD: Route crosses 120.0 mi of No Travel conditions.",
          ],
          rank: 2,
          recommended: false,
          deciding_criterion: "no_travel_miles",
          reasons: ["Ranked #2: Fewest No Travel miles"],
        },
      ],
      checkpoints: {
        route_b: [
          {
            index: 0,
            route_id: "route_b",
            route_name: "Route B (Southern Corridor)",
            interval_mi: 25,
            mile: 0,
            segment_miles: 25,
            lat: 39.74,
            lon: -104.99,
            elapsed_s: 0,
            eta_ts: 1795327200,
            eta_utc: "2026-11-22T06:00:00Z",
            wind_mph: 14,
            gust_mph: 20,
            rain_in_hr: 0,
            snow_in_hr: 0,
            wind_level: "Low",
            rain_level: "Low",
            snow_level: "Low",
            level: "Low",
            score: 1,
            load_rule_triggered: false,
            factors: ["Calm conditions"],
          },
        ],
        route_a: [
          {
            index: 0,
            route_id: "route_a",
            route_name: "Route A (Primary Direct)",
            interval_mi: 25,
            mile: 150,
            segment_miles: 120,
            lat: 41.1,
            lon: -108.5,
            elapsed_s: 9000,
            eta_ts: 1795336200,
            eta_utc: "2026-11-22T08:30:00Z",
            wind_mph: 48,
            gust_mph: 60,
            rain_in_hr: 0,
            snow_in_hr: 0,
            wind_level: "No Travel",
            rain_level: "Low",
            snow_level: "Low",
            level: "No Travel",
            score: 5,
            load_rule_triggered: true,
            factors: [
              "Wind 48.0 mph (45–54 mph) + 42,000 lb load (>30,000 lb) → No Travel",
            ],
          },
        ],
      },
    },
    "50": {
      summaries: [
        {
          route_id: "route_b",
          route_name: "Route B (Southern Corridor)",
          interval_mi: 50,
          distance_mi: 520,
          duration_s: 30000,
          miles_by_level: {
            Low: 520,
            Moderate: 0,
            High: 0,
            Severe: 0,
            "No Travel": 0,
            Unknown: 0,
          },
          avg_score: 1.0,
          coverage_pct: 100,
          has_no_travel: false,
          warnings: [],
          rank: 1,
          recommended: true,
          deciding_criterion: "no_travel_miles",
          reasons: ["Fewest No Travel miles (0.0 mi vs 120.0 mi on Route A)"],
        },
      ],
      checkpoints: {
        route_b: [],
      },
    },
  },
  heat_grid: {
    bbox: [-112.5, 38.5, -104.2, 41.8],
    rows: 6,
    cols: 8,
    mask: new Array(48).fill(1),
    start_utc: "2026-11-22T06:00:00Z",
    start_ts: 1795327200,
    hours: 49,
    hour_utc: Array.from(
      { length: 49 },
      (_, h) => new Date((1795327200 + h * 3600) * 1000).toISOString()
    ),
    cells: [
      {
        idx: 0,
        row: 0,
        col: 0,
        lat: 41.5,
        lon: -112.0,
        wind: new Array(49).fill(18),
        rain: new Array(49).fill(0),
        snow: new Array(49).fill(0),
        score: new Array(49).fill(1),
      },
    ],
  },
  notices: [],
};

describe("Heatmap & Truck Interpolation Utils", () => {
  it("interpolates truck positions along progress profile for hour T", () => {
    const posAt0 = interpolateTruckPositionsAtHour(MOCK_BUNDLE.routes, 0);
    expect(posAt0[0].mile).toBe(0);
    expect(posAt0[0].pctComplete).toBe(0);

    // At hour +4 (14400s), Route A is at midpoint (250 mi, 50%)
    const posAt4 = interpolateTruckPositionsAtHour(MOCK_BUNDLE.routes, 4);
    expect(posAt4[0].mile).toBe(250);
    expect(posAt4[0].pctComplete).toBe(50);

    // At hour +10 (36000s > 28800s), Route A has arrived (500 mi, 100%)
    const posAt10 = interpolateTruckPositionsAtHour(MOCK_BUNDLE.routes, 10);
    expect(posAt10[0].arrived).toBe(true);
    expect(posAt10[0].pctComplete).toBe(100);
  });

  it("maps risk and weather metrics to RGBA and builds 49 hourly frames", () => {
    const noTravelRgba = cellColorForMetric("risk", 5, 48, 0, 0);
    expect(noTravelRgba[0]).toBe(168); // Purple No Travel

    const frames = buildHeatmapFramesForMetric(MOCK_BUNDLE.heat_grid, "risk");
    expect(frames).toHaveLength(49);
  });
});

describe("App Component Integration", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders recommended route, switches intervals without network calls, and opens checkpoint inspector", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => MOCK_BUNDLE,
    } as Response);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("route-card-route_b")).toBeInTheDocument();
    });

    expect(screen.getByText(/RECOMMENDED/i)).toBeInTheDocument();
    expect(
      screen.getByText(
        /Fewest No Travel miles \(0.0 mi vs 120.0 mi on Route A\)/i
      )
    ).toBeInTheDocument();

    // Switching from 25 mi to 10 mi interval should not trigger any extra network fetch
    const callsBeforeToggle = fetchMock.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "10 mi" }));
    expect(fetchMock.mock.calls.length).toBe(callsBeforeToggle);

    // Switch back to 25 mi, click Route A card, and inspect its No Travel checkpoint
    fireEvent.click(screen.getByRole("button", { name: "25 mi" }));
    fireEvent.click(screen.getByTestId("route-card-route_a"));
    fireEvent.click(screen.getByText("150 mi"));

    await waitFor(() => {
      expect(screen.getByTestId("checkpoint-inspector")).toBeInTheDocument();
    });
    expect(
      screen.getByText(
        /Wind 48.0 mph \(45–54 mph\) \+ 42,000 lb load \(>30,000 lb\) → No Travel/i
      )
    ).toBeInTheDocument();
  });

  it("displays clear error banner when routing or weather provider returns 503", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({
        error: "Routing unavailable after 3 attempts",
        provider: "routing",
      }),
    } as Response);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        /Routing unavailable after 3 attempts/i
      );
    });
  });

  it("catches rendering errors in ErrorBoundary and recovers on reset", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    let shouldThrow = true;
    const Bomb = () => {
      if (shouldThrow) throw new Error("Simulated WebGL failure");
      return <div>Map recovered</div>;
    };

    render(
      <ErrorBoundary fallbackTitle="Map Rendering Error">
        <Bomb />
      </ErrorBoundary>
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Map Rendering Error");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Simulated WebGL failure"
    );

    shouldThrow = false;
    fireEvent.click(screen.getByRole("button", { name: /Try Again/i }));
    expect(screen.getByText("Map recovered")).toBeInTheDocument();
    spy.mockRestore();
  });
});
