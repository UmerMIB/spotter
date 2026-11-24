import type { GeocodePlace, TripBundle } from "../types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

/**
 * Error thrown when an API request fails with an HTTP error status or server failure.
 */
export class ApiRequestError extends Error {
  status: number;
  field?: string | null;
  provider?: string | null;

  constructor(
    message: string,
    status: number,
    field?: string | null,
    provider?: string | null
  ) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.field = field;
    this.provider = provider;
  }
}

/**
 * Search places matching a query string via `/api/geocode`.
 * Returns an empty list for queries shorter than 2 characters.
 */
export async function searchGeocode(
  query: string,
  signal?: AbortSignal
): Promise<GeocodePlace[]> {
  const q = query.trim();
  if (q.length < 2) return [];

  const resp = await fetch(
    `${API_BASE}/api/geocode?q=${encodeURIComponent(q)}`,
    { signal }
  );
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const fallbackMsg =
      resp.status >= 500
        ? `Geocoding server error (HTTP ${resp.status}). Ensure Django is running on port 8000.`
        : `Geocoding failed (HTTP ${resp.status})`;
    throw new ApiRequestError(
      data.error || fallbackMsg,
      resp.status,
      data.field,
      data.provider
    );
  }
  return Array.isArray(data.results) ? data.results : [];
}

/**
 * Request payload for `POST /api/trips`.
 */
export interface PlanTripPayload {
  origin: string | GeocodePlace;
  destination: string | GeocodePlace;
  departure_time: string;
  load_lb: number;
}

/**
 * Plan up to 3 weather-aware truck routes and fetch the 10/25/50 mi checkpoint
 * bundles plus the 0-48h corridor heatmap grid.
 */
export async function planTrip(payload: PlanTripPayload): Promise<TripBundle> {
  const resp = await fetch(`${API_BASE}/api/trips`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const fallbackMsg =
      resp.status >= 500
        ? `Backend server error (HTTP ${resp.status}). Check that Django is running on port 8000 and inspect its logs.`
        : `Failed to plan trip (HTTP ${resp.status})`;
    throw new ApiRequestError(
      data.error || fallbackMsg,
      resp.status,
      data.field,
      data.provider
    );
  }
  return data as TripBundle;
}
