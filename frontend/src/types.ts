export type RiskLevel =
  | "Low"
  | "Moderate"
  | "High"
  | "Severe"
  | "No Travel"
  | "Unknown";

export type SamplingInterval = 10 | 25 | 50;

export type HeatmapMetric = "risk" | "wind" | "rain" | "snow";

export interface GeocodePlace {
  label: string;
  lat: number;
  lon: number;
  country_code?: string;
  is_north_america?: boolean;
}

export interface Checkpoint {
  index: number;
  route_id: string;
  route_name: string;
  interval_mi: SamplingInterval;
  mile: number;
  segment_miles: number;
  lat: number;
  lon: number;
  elapsed_s: number;
  eta_ts: number;
  eta_utc: string;
  wind_mph: number | null;
  gust_mph: number | null;
  rain_in_hr: number | null;
  snow_in_hr: number | null;
  wind_level: RiskLevel;
  rain_level: RiskLevel;
  snow_level: RiskLevel;
  level: RiskLevel;
  score: number | null;
  load_rule_triggered: boolean;
  factors: string[];
}

export interface RouteSummary {
  route_id: string;
  route_name: string;
  interval_mi: SamplingInterval;
  distance_mi: number;
  duration_s: number;
  miles_by_level: Record<RiskLevel, number>;
  avg_score: number | null;
  coverage_pct: number;
  has_no_travel: boolean;
  warnings: string[];
  rank: number;
  recommended: boolean;
  deciding_criterion: string;
  reasons: string[];
}

export interface RouteGeometry {
  id: string;
  name: string;
  source: "osrm" | "via-point";
  polyline: string;
  geojson_coords: [number, number][]; // [lon, lat]
  progress_profile: [number, number, number, number][]; // [mile, elapsed_s, lat, lon]
  distance_mi: number;
  duration_s: number;
  eta_utc: string;
}

export interface HeatGridCell {
  idx: number;
  row: number;
  col: number;
  lat: number;
  lon: number;
  wind: (number | null)[];
  rain: (number | null)[];
  snow: (number | null)[];
  score: number[];
}

export interface HeatGrid {
  bbox: [number, number, number, number]; // [minLon, minLat, maxLon, maxLat]
  rows: number;
  cols: number;
  mask: number[];
  start_utc: string;
  start_ts: number;
  hours: number;
  hour_utc: string[];
  cells: HeatGridCell[];
}

export interface TripBundle {
  request: {
    origin: GeocodePlace;
    destination: GeocodePlace;
    departure_utc: string;
    departure_ts: number;
    load_lb: number;
    truck_max_speed_mph: number;
    default_interval_mi: SamplingInterval;
  };
  routes: RouteGeometry[];
  intervals: Record<
    "10" | "25" | "50",
    {
      summaries: RouteSummary[];
      checkpoints: Record<string, Checkpoint[]>;
    }
  >;
  heat_grid: HeatGrid;
  notices: string[];
}

export interface ApiError {
  error: string;
  field?: string | null;
  provider?: string | null;
}
