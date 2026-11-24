import type {
  HeatGrid,
  HeatmapMetric,
  RiskLevel,
  RouteGeometry,
} from "../types";

export const RISK_COLORS: Record<RiskLevel, string> = {
  Low: "#10b981",
  Moderate: "#eab308",
  High: "#f97316",
  Severe: "#ef4444",
  "No Travel": "#a855f7",
  Unknown: "#64748b",
};

export const RISK_BG_COLORS: Record<RiskLevel, string> = {
  Low: "rgba(16, 185, 129, 0.16)",
  Moderate: "rgba(234, 179, 8, 0.18)",
  High: "rgba(249, 115, 22, 0.20)",
  Severe: "rgba(239, 68, 68, 0.22)",
  "No Travel": "rgba(168, 85, 247, 0.26)",
  Unknown: "rgba(100, 116, 139, 0.18)",
};

type RGBA = [number, number, number, number];

const SCORE_RGBA: Record<number, RGBA> = {
  0: [100, 116, 139, 110], // Unknown
  1: [16, 185, 129, 145], // Low
  2: [234, 179, 8, 175], // Moderate
  3: [249, 115, 22, 200], // High
  4: [239, 68, 68, 220], // Severe
  5: [168, 85, 247, 240], // No Travel
};

function lerpRgba(a: RGBA, b: RGBA, t: number): RGBA {
  const c = Math.max(0, Math.min(1, t));
  return [
    Math.round(a[0] + (b[0] - a[0]) * c),
    Math.round(a[1] + (b[1] - a[1]) * c),
    Math.round(a[2] + (b[2] - a[2]) * c),
    Math.round(a[3] + (b[3] - a[3]) * c),
  ];
}

/**
 * Map a heatmap cell's weather metric or combined risk score (0-5) to an RGBA color tuple.
 */
export function cellColorForMetric(
  metric: HeatmapMetric,
  score: number,
  wind: number | null,
  rain: number | null,
  snow: number | null
): RGBA {
  if (metric === "risk") {
    return SCORE_RGBA[score] || SCORE_RGBA[0];
  }

  if (metric === "wind") {
    if (wind === null) return SCORE_RGBA[0];
    if (wind < 25) return lerpRgba([16, 185, 129, 125], [52, 211, 153, 165], wind / 25);
    if (wind < 35) return lerpRgba([234, 179, 8, 170], [250, 204, 21, 195], (wind - 25) / 10);
    if (wind < 45) return lerpRgba([249, 115, 22, 195], [251, 146, 60, 215], (wind - 35) / 10);
    if (wind < 55) return lerpRgba([239, 68, 68, 215], [220, 38, 38, 235], (wind - 45) / 10);
    return [168, 85, 247, 245];
  }

  if (metric === "rain") {
    if (rain === null) return SCORE_RGBA[0];
    if (rain <= 0.005) return [16, 185, 129, 75];
    if (rain < 0.1) return lerpRgba([56, 189, 248, 120], [14, 165, 233, 160], rain / 0.1);
    if (rain < 0.25) return lerpRgba([234, 179, 8, 175], [245, 158, 11, 195], (rain - 0.1) / 0.15);
    if (rain < 0.5) return lerpRgba([249, 115, 22, 200], [239, 68, 68, 215], (rain - 0.25) / 0.25);
    if (rain <= 1.0) return lerpRgba([239, 68, 68, 220], [185, 28, 28, 235], (rain - 0.5) / 0.5);
    return [168, 85, 247, 245];
  }

  // snow
  if (snow === null) return SCORE_RGBA[0];
  if (snow <= 0.01) return [16, 185, 129, 75];
  if (snow < 0.5) return lerpRgba([125, 211, 252, 135], [56, 189, 248, 175], snow / 0.5);
  if (snow < 1.0) return lerpRgba([234, 179, 8, 185], [249, 115, 22, 205], (snow - 0.5) / 0.5);
  if (snow < 2.0) return lerpRgba([249, 115, 22, 205], [239, 68, 68, 225], (snow - 1.0) / 1.0);
  if (snow <= 3.0) return [239, 68, 68, 235];
  return [168, 85, 247, 245];
}

/**
 * Pre-render all 49 hourly heatmap frames (0-48h) for a single metric into smoothed PNG data URLs
 * so slider scrubbing only swaps prebuilt MapLibre image frames with zero React re-renders.
 */
export function buildHeatmapFramesForMetric(
  heatGrid: HeatGrid,
  metric: HeatmapMetric
): string[] {
  const { rows, cols, hours, cells } = heatGrid;
  const totalPixels = rows * cols;
  const frames: string[] = [];

  if (typeof document === "undefined") {
    return Array.from({ length: hours }, (_, h) => `data:image/png;base64,frame_${metric}_${h}`);
  }

  const rawCanvas = document.createElement("canvas");
  rawCanvas.width = cols;
  rawCanvas.height = rows;
  const rawCtx = rawCanvas.getContext("2d");

  const scale = 6;
  const smoothCanvas = document.createElement("canvas");
  smoothCanvas.width = cols * scale;
  smoothCanvas.height = rows * scale;
  const smoothCtx = smoothCanvas.getContext("2d");

  if (!rawCtx || !smoothCtx) {
    return Array.from({ length: hours }, (_, h) => `data:image/png;base64,frame_${metric}_${h}`);
  }

  smoothCtx.imageSmoothingEnabled = true;
  smoothCtx.imageSmoothingQuality = "high";

  for (let h = 0; h < hours; h++) {
    const imgData = rawCtx.createImageData(cols, rows);
    const buf = imgData.data;

    // 1. Paint active corridor cells
    const activeColors: (RGBA | null)[] = new Array(totalPixels).fill(null);
    for (let i = 0; i < cells.length; i++) {
      const cell = cells[i];
      const rgba = cellColorForMetric(
        metric,
        cell.score[h] ?? 0,
        cell.wind[h] ?? null,
        cell.rain[h] ?? null,
        cell.snow[h] ?? null
      );
      activeColors[cell.idx] = rgba;
      const offset = cell.idx * 4;
      buf[offset] = rgba[0];
      buf[offset + 1] = rgba[1];
      buf[offset + 2] = rgba[2];
      buf[offset + 3] = rgba[3];
    }

    // 2. Soft 1-pixel halo around corridor boundary for smooth feathering
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const idx = r * cols + c;
        if (activeColors[idx] !== null) continue;

        let rSum = 0;
        let gSum = 0;
        let bSum = 0;
        let aSum = 0;
        let count = 0;

        for (let dr = -1; dr <= 1; dr++) {
          for (let dc = -1; dc <= 1; dc++) {
            const nr = r + dr;
            const nc = c + dc;
            if (nr >= 0 && nr < rows && nc >= 0 && nc < cols) {
              const neighbor = activeColors[nr * cols + nc];
              if (neighbor !== null) {
                rSum += neighbor[0];
                gSum += neighbor[1];
                bSum += neighbor[2];
                aSum += neighbor[3];
                count++;
              }
            }
          }
        }

        if (count > 0) {
          const offset = idx * 4;
          buf[offset] = Math.round(rSum / count);
          buf[offset + 1] = Math.round(gSum / count);
          buf[offset + 2] = Math.round(bSum / count);
          buf[offset + 3] = Math.round((aSum / count) * 0.42);
        }
      }
    }

    rawCtx.putImageData(imgData, 0, 0);
    smoothCtx.clearRect(0, 0, smoothCanvas.width, smoothCanvas.height);
    smoothCtx.drawImage(
      rawCanvas,
      0,
      0,
      cols,
      rows,
      0,
      0,
      smoothCanvas.width,
      smoothCanvas.height
    );
    frames.push(smoothCanvas.toDataURL("image/png"));
  }

  return frames;
}

export interface TruckPositionPoint {
  routeId: string;
  routeName: string;
  lat: number;
  lon: number;
  mile: number;
  totalMiles: number;
  pctComplete: number;
  arrived: boolean;
}

/**
 * Interpolate each route's truck coordinates, milepost, and completion percentage at forecast hour +T.
 */
export function interpolateTruckPositionsAtHour(
  routes: RouteGeometry[],
  hourOffset: number
): TruckPositionPoint[] {
  const elapsedTarget = Math.max(0, hourOffset * 3600);

  return routes.map((route) => {
    const profile = route.progress_profile;
    if (!profile || profile.length === 0) {
      return {
        routeId: route.id,
        routeName: route.name,
        lat: 0,
        lon: 0,
        mile: 0,
        totalMiles: route.distance_mi,
        pctComplete: 0,
        arrived: false,
      };
    }

    const last = profile[profile.length - 1];
    if (elapsedTarget >= last[1]) {
      return {
        routeId: route.id,
        routeName: route.name,
        lat: last[2],
        lon: last[3],
        mile: Math.round(last[0]),
        totalMiles: route.distance_mi,
        pctComplete: 100,
        arrived: true,
      };
    }

    if (elapsedTarget <= profile[0][1]) {
      return {
        routeId: route.id,
        routeName: route.name,
        lat: profile[0][2],
        lon: profile[0][3],
        mile: 0,
        totalMiles: route.distance_mi,
        pctComplete: 0,
        arrived: false,
      };
    }

    let idx = 0;
    while (idx < profile.length - 2 && profile[idx + 1][1] < elapsedTarget) {
      idx++;
    }

    const p0 = profile[idx];
    const p1 = profile[idx + 1];
    const span = p1[1] - p0[1];
    const frac = span > 0 ? Math.max(0, Math.min(1, (elapsedTarget - p0[1]) / span)) : 0;

    const mile = p0[0] + frac * (p1[0] - p0[0]);
    const lat = p0[2] + frac * (p1[2] - p0[2]);
    const lon = p0[3] + frac * (p1[3] - p0[3]);
    const pct = route.distance_mi > 0 ? Math.round((mile / route.distance_mi) * 100) : 0;

    return {
      routeId: route.id,
      routeName: route.name,
      lat,
      lon,
      mile: Math.round(mile),
      totalMiles: route.distance_mi,
      pctComplete: Math.min(100, pct),
      arrived: false,
    };
  });
}

/**
 * Format duration in seconds as `Xh Ym` (or `Ym` when under 1 hour).
 */
export function formatDuration(seconds: number): string {
  const totalMins = Math.round(seconds / 60);
  const h = Math.floor(totalMins / 60);
  const m = totalMins % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

/**
 * Format an ISO-8601 UTC timestamp for compact UI display in local browser time.
 */
export function formatUtcTimeShort(isoUtc: string): string {
  try {
    const d = new Date(isoUtc);
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return isoUtc;
  }
}
