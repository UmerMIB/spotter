import React, { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type {
  Checkpoint,
  HeatmapMetric,
  SamplingInterval,
  TripBundle,
} from "../types";
import {
  buildHeatmapFramesForMetric,
  formatUtcTimeShort,
  interpolateTruckPositionsAtHour,
} from "../utils/heatmap";
import {
  DARK_RASTER_STYLE,
  buildTripMapGeoJSON,
  buildTruckGeoJSON,
} from "../utils/mapLayers";
import { CheckpointModal } from "./CheckpointModal";
import { ForecastSlider } from "./ForecastSlider";
import { HeatmapControls } from "./HeatmapControls";

interface Props {
  trip: TripBundle | null;
  intervalMi: SamplingInterval;
  selectedRouteId: string | null;
  onSelectRoute: (routeId: string) => void;
  inspectedCheckpoint: Checkpoint | null;
  onInspectCheckpoint: (cp: Checkpoint | null) => void;
}

/**
 * Interactive MapLibre GL map rendering the 3 route corridors, risk-colored checkpoints,
 * pre-rendered 0-48h weather heatmap frames, and animated truck position markers.
 */
export const MapView: React.FC<Props> = ({
  trip,
  intervalMi,
  selectedRouteId,
  onSelectRoute,
  inspectedCheckpoint,
  onInspectCheckpoint,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [mapReady, setMapReady] = useState(false);

  const [metric, setMetric] = useState<HeatmapMetric>("risk");
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);

  // Refs for 60fps direct slider updates without React tree re-renders
  const hourRef = useRef<number>(0);
  const sliderInputRef = useRef<HTMLInputElement>(null);
  const hourBadgeRef = useRef<HTMLSpanElement>(null);
  const timeLabelRef = useRef<HTMLSpanElement>(null);
  const truckHudRef = useRef<HTMLDivElement>(null);
  const rafRef = useRef<number | null>(null);

  const framesCacheRef = useRef<Partial<Record<HeatmapMetric, string[]>>>({});
  const tripRef = useRef<TripBundle | null>(trip);
  tripRef.current = trip;
  const selectedRouteRef = useRef<string | null>(selectedRouteId);
  selectedRouteRef.current = selectedRouteId;
  const metricRef = useRef<HeatmapMetric>(metric);
  metricRef.current = metric;

  useEffect(() => {
    framesCacheRef.current = {};
    hourRef.current = 0;
    if (sliderInputRef.current) sliderInputRef.current.value = "0";
    setIsPlaying(false);
  }, [trip]);

  const getFramesForMetric = (bundle: TripBundle, m: HeatmapMetric): string[] => {
    if (!framesCacheRef.current[m]) {
      framesCacheRef.current[m] = buildHeatmapFramesForMetric(bundle.heat_grid, m);
    }
    return framesCacheRef.current[m]!;
  };

  const applyHourFrame = (hour: number) => {
    hourRef.current = hour;
    const bundle = tripRef.current;
    const map = mapRef.current;

    if (sliderInputRef.current && sliderInputRef.current.value !== String(hour)) {
      sliderInputRef.current.value = String(hour);
    }
    if (hourBadgeRef.current) {
      hourBadgeRef.current.textContent = `+${hour}h`;
    }
    if (bundle && timeLabelRef.current) {
      const iso = bundle.heat_grid.hour_utc[hour] || bundle.heat_grid.start_utc;
      timeLabelRef.current.textContent = formatUtcTimeShort(iso);
    }
    if (bundle && truckHudRef.current) {
      const positions = interpolateTruckPositionsAtHour(bundle.routes, hour);
      const sel =
        positions.find((p) => p.routeId === selectedRouteRef.current) ||
        positions[0];
      if (sel) {
        truckHudRef.current.textContent = sel.arrived
          ? `Truck arrived at destination (${sel.totalMiles.toFixed(0)} mi)`
          : `Truck at Mile ${sel.mile} of ${sel.totalMiles.toFixed(0)} mi (${
              sel.pctComplete
            }%)`;
      }
    }

    if (!map || !bundle) return;

    const frameUrl = getFramesForMetric(bundle, metricRef.current)[hour];
    const heatSrc = map.getSource("corridor-heatmap") as
      | maplibregl.ImageSource
      | undefined;
    if (heatSrc && frameUrl) {
      const [minLon, minLat, maxLon, maxLat] = bundle.heat_grid.bbox;
      heatSrc.updateImage({
        url: frameUrl,
        coordinates: [
          [minLon, maxLat],
          [maxLon, maxLat],
          [maxLon, minLat],
          [minLon, minLat],
        ],
      });
    }

    const truckSrc = map.getSource("truck-positions") as
      | maplibregl.GeoJSONSource
      | undefined;
    if (truckSrc) {
      truckSrc.setData(buildTruckGeoJSON(bundle, hour, selectedRouteRef.current));
    }
  };

  const scheduleHourUpdate = (nextHour: number) => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      applyHourFrame(nextHour);
    });
  };

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container: mapContainerRef.current,
        style: DARK_RASTER_STYLE,
        center: [-104.99, 39.74],
        zoom: 4.3,
        attributionControl: false,
      });
    } catch {
      return;
    }

    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl(), "top-left");

    map.on("load", () => {
      setMapReady(true);

      map.on("click", "checkpoints-layer", (e) => {
        const cpId = e.features?.[0]?.properties?.cp_uid;
        const bundle = tripRef.current;
        if (!cpId || !bundle) return;
        for (const ikey of ["10", "25", "50"] as const) {
          for (const rId of Object.keys(bundle.intervals[ikey].checkpoints)) {
            const found = bundle.intervals[ikey].checkpoints[rId].find(
              (c) => `${c.interval_mi}-${c.route_id}-${c.index}` === cpId
            );
            if (found) {
              onInspectCheckpoint(found);
              return;
            }
          }
        }
      });

      map.on("click", "routes-inactive-layer", (e) => {
        const rId = e.features?.[0]?.properties?.route_id;
        if (rId) onSelectRoute(String(rId));
      });

      for (const layerId of ["checkpoints-layer", "routes-inactive-layer"]) {
        map.on("mouseenter", layerId, () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", layerId, () => {
          map.getCanvas().style.cursor = "";
        });
      }
    });

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      map.remove();
      mapRef.current = null;
    };
  }, []);

  const { routesGeoJSON, checkpointsGeoJSON, endpointsGeoJSON } = useMemo(
    () => buildTripMapGeoJSON(trip, intervalMi, selectedRouteId),
    [trip, intervalMi, selectedRouteId]
  );

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !trip) return;

    const [minLon, minLat, maxLon, maxLat] = trip.heat_grid.bbox;
    const frames = getFramesForMetric(trip, metric);
    const currentHour = Math.min(hourRef.current, frames.length - 1);
    const frameUrl = frames[currentHour];
    const imageCoords: [
      [number, number],
      [number, number],
      [number, number],
      [number, number]
    ] = [
      [minLon, maxLat],
      [maxLon, maxLat],
      [maxLon, minLat],
      [minLon, minLat],
    ];

    const existingHeat = map.getSource("corridor-heatmap") as
      | maplibregl.ImageSource
      | undefined;
    if (!existingHeat) {
      map.addSource("corridor-heatmap", {
        type: "image",
        url: frameUrl,
        coordinates: imageCoords,
      });
      map.addLayer({
        id: "corridor-heatmap-layer",
        type: "raster",
        source: "corridor-heatmap",
        paint: {
          "raster-opacity": showHeatmap ? 0.65 : 0,
          "raster-resampling": "linear",
          "raster-fade-duration": 0,
        },
      });
    } else {
      existingHeat.updateImage({ url: frameUrl, coordinates: imageCoords });
      if (map.getLayer("corridor-heatmap-layer")) {
        map.setPaintProperty(
          "corridor-heatmap-layer",
          "raster-opacity",
          showHeatmap ? 0.65 : 0
        );
      }
    }

    const existingRoutes = map.getSource("routes-source") as
      | maplibregl.GeoJSONSource
      | undefined;
    if (!existingRoutes) {
      map.addSource("routes-source", { type: "geojson", data: routesGeoJSON });
      map.addLayer({
        id: "routes-inactive-layer",
        type: "line",
        source: "routes-source",
        filter: ["==", ["get", "is_selected"], 0],
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": "#94a3b8",
          "line-width": 4,
          "line-opacity": 0.65,
          "line-dasharray": [2, 1.5],
        },
      });
      map.addLayer({
        id: "routes-active-casing",
        type: "line",
        source: "routes-source",
        filter: ["==", ["get", "is_selected"], 1],
        layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": "#0f172a", "line-width": 10, "line-opacity": 0.9 },
      });
      map.addLayer({
        id: "routes-active-layer",
        type: "line",
        source: "routes-source",
        filter: ["==", ["get", "is_selected"], 1],
        layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": "#38bdf8", "line-width": 5.5, "line-opacity": 1 },
      });
    } else {
      existingRoutes.setData(routesGeoJSON);
    }

    const existingCps = map.getSource("checkpoints-source") as
      | maplibregl.GeoJSONSource
      | undefined;
    if (!existingCps) {
      map.addSource("checkpoints-source", {
        type: "geojson",
        data: checkpointsGeoJSON,
      });
      map.addLayer({
        id: "checkpoints-layer",
        type: "circle",
        source: "checkpoints-source",
        paint: {
          "circle-radius": ["case", ["==", ["get", "is_selected"], 1], 6.5, 4.2],
          "circle-color": ["get", "color"],
          "circle-stroke-width": [
            "case",
            ["==", ["get", "is_selected"], 1],
            2,
            1,
          ],
          "circle-stroke-color": "#0f172a",
          "circle-opacity": [
            "case",
            ["==", ["get", "is_selected"], 1],
            1.0,
            0.75,
          ],
        },
      });
    } else {
      existingCps.setData(checkpointsGeoJSON);
    }

    const existingEps = map.getSource("endpoints-source") as
      | maplibregl.GeoJSONSource
      | undefined;
    if (!existingEps) {
      map.addSource("endpoints-source", {
        type: "geojson",
        data: endpointsGeoJSON,
      });
      map.addLayer({
        id: "endpoints-layer",
        type: "circle",
        source: "endpoints-source",
        paint: {
          "circle-radius": 9,
          "circle-color": ["get", "color"],
          "circle-stroke-width": 2.5,
          "circle-stroke-color": "#ffffff",
        },
      });
    } else {
      existingEps.setData(endpointsGeoJSON);
    }

    const truckData = buildTruckGeoJSON(trip, currentHour, selectedRouteId);
    const existingTrucks = map.getSource("truck-positions") as
      | maplibregl.GeoJSONSource
      | undefined;
    if (!existingTrucks) {
      map.addSource("truck-positions", { type: "geojson", data: truckData });
      map.addLayer({
        id: "truck-positions-halo",
        type: "circle",
        source: "truck-positions",
        paint: {
          "circle-radius": ["case", ["==", ["get", "is_selected"], 1], 13, 8],
          "circle-color": [
            "case",
            ["==", ["get", "is_selected"], 1],
            "#38bdf8",
            "#94a3b8",
          ],
          "circle-opacity": 0.28,
        },
      });
      map.addLayer({
        id: "truck-positions-layer",
        type: "circle",
        source: "truck-positions",
        paint: {
          "circle-radius": ["case", ["==", ["get", "is_selected"], 1], 7.5, 5],
          "circle-color": [
            "case",
            ["==", ["get", "is_selected"], 1],
            "#0284c7",
            "#475569",
          ],
          "circle-stroke-width": 2.5,
          "circle-stroke-color": "#ffffff",
        },
      });
    } else {
      existingTrucks.setData(truckData);
    }

    applyHourFrame(currentHour);
  }, [
    trip,
    mapReady,
    routesGeoJSON,
    checkpointsGeoJSON,
    endpointsGeoJSON,
    metric,
    showHeatmap,
    selectedRouteId,
  ]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !trip) return;
    const [minLon, minLat, maxLon, maxLat] = trip.heat_grid.bbox;
    map.fitBounds(
      [
        [minLon, minLat],
        [maxLon, maxLat],
      ],
      { padding: 48, duration: 700 }
    );
  }, [trip, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !inspectedCheckpoint) return;
    map.easeTo({
      center: [inspectedCheckpoint.lon, inspectedCheckpoint.lat],
      duration: 450,
    });
  }, [inspectedCheckpoint, mapReady]);

  useEffect(() => {
    if (!isPlaying || !trip) return;
    const maxHour = trip.heat_grid.hours - 1;
    const intervalId = window.setInterval(() => {
      const next = hourRef.current >= maxHour ? 0 : hourRef.current + 1;
      scheduleHourUpdate(next);
    }, 180);
    return () => window.clearInterval(intervalId);
  }, [isPlaying, trip]);

  return (
    <div className="map-stage">
      <div
        ref={mapContainerRef}
        className="maplibre-container"
        data-testid="map-container"
      />

      <HeatmapControls
        metric={metric}
        showHeatmap={showHeatmap}
        onChangeMetric={setMetric}
        onToggleHeatmap={() => setShowHeatmap((v) => !v)}
      />

      <CheckpointModal
        checkpoint={inspectedCheckpoint}
        onClose={() => onInspectCheckpoint(null)}
      />

      {trip && (
        <ForecastSlider
          hours={trip.heat_grid.hours}
          startUtc={trip.heat_grid.start_utc}
          isPlaying={isPlaying}
          onTogglePlay={() => setIsPlaying((p) => !p)}
          onScrubHour={(hour) => {
            setIsPlaying(false);
            scheduleHourUpdate(hour);
          }}
          sliderInputRef={sliderInputRef}
          hourBadgeRef={hourBadgeRef}
          timeLabelRef={timeLabelRef}
          truckHudRef={truckHudRef}
        />
      )}
    </div>
  );
};
