import type maplibregl from "maplibre-gl";
import type { SamplingInterval, TripBundle } from "../types";
import { RISK_COLORS, interpolateTruckPositionsAtHour } from "./heatmap";

/**
 * Free CARTO dark-matter raster basemap style specification for MapLibre GL.
 */
export const DARK_RASTER_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    "carto-dark": {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
        "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
        "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
      ],
      tileSize: 256,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    },
  },
  layers: [
    {
      id: "carto-dark-layer",
      type: "raster",
      source: "carto-dark",
      minzoom: 0,
      maxzoom: 20,
    },
  ],
};

/**
 * Build GeoJSON collections for route lines, checkpoints, and origin/destination endpoints.
 */
export function buildTripMapGeoJSON(
  trip: TripBundle | null,
  intervalMi: SamplingInterval,
  selectedRouteId: string | null
): {
  routesGeoJSON: GeoJSON.FeatureCollection;
  checkpointsGeoJSON: GeoJSON.FeatureCollection;
  endpointsGeoJSON: GeoJSON.FeatureCollection;
} {
  if (!trip) {
    const empty: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: [],
    };
    return {
      routesGeoJSON: empty,
      checkpointsGeoJSON: empty,
      endpointsGeoJSON: empty,
    };
  }

  const ikey = String(intervalMi) as "10" | "25" | "50";
  const intervalData = trip.intervals[ikey];
  const summaryByRoute = Object.fromEntries(
    intervalData.summaries.map((s) => [s.route_id, s])
  );

  const routeFeatures: GeoJSON.Feature[] = trip.routes.map((r) => {
    const sum = summaryByRoute[r.id];
    const worstColor = sum?.has_no_travel
      ? RISK_COLORS["No Travel"]
      : (sum?.miles_by_level.Severe || 0) > 0
      ? RISK_COLORS.Severe
      : (sum?.miles_by_level.High || 0) > 0
      ? RISK_COLORS.High
      : sum?.recommended
      ? "#10b981"
      : "#38bdf8";

    return {
      type: "Feature",
      geometry: {
        type: "LineString",
        coordinates: r.geojson_coords,
      },
      properties: {
        route_id: r.id,
        route_name: r.name,
        is_selected: r.id === selectedRouteId ? 1 : 0,
        recommended: sum?.recommended ? 1 : 0,
        color: worstColor,
      },
    };
  });

  const cpFeatures: GeoJSON.Feature[] = [];
  for (const r of trip.routes) {
    const cps = intervalData.checkpoints[r.id] || [];
    const isSel = r.id === selectedRouteId;
    for (const cp of cps) {
      cpFeatures.push({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [cp.lon, cp.lat],
        },
        properties: {
          cp_uid: `${cp.interval_mi}-${cp.route_id}-${cp.index}`,
          route_id: cp.route_id,
          mile: cp.mile,
          level: cp.level,
          color: RISK_COLORS[cp.level] || RISK_COLORS.Unknown,
          is_selected: isSel ? 1 : 0,
          load_triggered: cp.load_rule_triggered ? 1 : 0,
        },
      });
    }
  }

  const epFeatures: GeoJSON.Feature[] = [
    {
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [trip.request.origin.lon, trip.request.origin.lat],
      },
      properties: {
        kind: "ORIGIN",
        label: trip.request.origin.label,
        color: "#22c55e",
      },
    },
    {
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [
          trip.request.destination.lon,
          trip.request.destination.lat,
        ],
      },
      properties: {
        kind: "DESTINATION",
        label: trip.request.destination.label,
        color: "#f43f5e",
      },
    },
  ];

  return {
    routesGeoJSON: { type: "FeatureCollection", features: routeFeatures },
    checkpointsGeoJSON: { type: "FeatureCollection", features: cpFeatures },
    endpointsGeoJSON: { type: "FeatureCollection", features: epFeatures },
  };
}

/**
 * Build a GeoJSON FeatureCollection of interpolated truck positions at forecast hour +T.
 */
export function buildTruckGeoJSON(
  trip: TripBundle,
  hourOffset: number,
  selectedRouteId: string | null
): GeoJSON.FeatureCollection {
  const positions = interpolateTruckPositionsAtHour(trip.routes, hourOffset);
  return {
    type: "FeatureCollection",
    features: positions.map((p) => ({
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [p.lon, p.lat],
      },
      properties: {
        route_id: p.routeId,
        route_name: p.routeName,
        mile: p.mile,
        pct: p.pctComplete,
        arrived: p.arrived,
        is_selected: p.routeId === selectedRouteId ? 1 : 0,
        label: `${p.routeName.split(" ")[1] || p.routeId}: ${p.mile} mi (${
          p.pctComplete
        }%)`,
      },
    })),
  };
}
