import type { RiskLevel, SamplingInterval } from "./types";

export const DEFAULT_INTERVAL_MI: SamplingInterval = 25;
export const SAMPLING_INTERVALS: readonly SamplingInterval[] = [10, 25, 50];
export const DEFAULT_TRUCK_MAX_SPEED_MPH = 65;
export const MAX_LOAD_LB = 80000;
export const FORECAST_MAX_DAYS = 7;

export const ORDERED_RISK_LEVELS: readonly RiskLevel[] = [
  "Low",
  "Moderate",
  "High",
  "Severe",
  "No Travel",
  "Unknown",
];

export const LEGEND_RISK_LEVELS: readonly RiskLevel[] = [
  "Low",
  "Moderate",
  "High",
  "Severe",
  "No Travel",
];
