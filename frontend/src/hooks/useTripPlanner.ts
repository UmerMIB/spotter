import { useCallback, useEffect, useState } from "react";
import { ApiRequestError, planTrip } from "../api/client";
import { CORRIDOR_PRESETS } from "../components/TripForm";
import { DEFAULT_INTERVAL_MI } from "../constants";
import type {
  Checkpoint,
  GeocodePlace,
  SamplingInterval,
  TripBundle,
} from "../types";

export interface SubmitTripParams {
  origin: string | GeocodePlace;
  destination: string | GeocodePlace;
  departure_time: string;
  load_lb: number;
}

/**
 * Custom hook encapsulating trip planning state, API error handling,
 * active route/interval selection, and initial default corridor loading.
 */
export function useTripPlanner() {
  const [trip, setTrip] = useState<TripBundle | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [intervalMi, setIntervalMi] =
    useState<SamplingInterval>(DEFAULT_INTERVAL_MI);
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null);
  const [inspectedCheckpoint, setInspectedCheckpoint] =
    useState<Checkpoint | null>(null);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const submitTrip = useCallback(
    async (params: SubmitTripParams) => {
      setLoading(true);
      setGlobalError(null);
      setFieldErrors({});
      setInspectedCheckpoint(null);

      try {
        const bundle = await planTrip(params);
        setTrip(bundle);
        const ikey = String(intervalMi) as "10" | "25" | "50";
        const summaries = bundle.intervals[ikey].summaries;
        const rec = summaries.find((s) => s.recommended) || summaries[0];
        setSelectedRouteId(rec ? rec.route_id : bundle.routes[0]?.id || null);
      } catch (err) {
        if (err instanceof ApiRequestError) {
          if (err.field) {
            setFieldErrors({ [err.field]: err.message });
          } else {
            setGlobalError(err.message);
          }
        } else {
          setGlobalError(
            err instanceof Error
              ? err.message
              : "Unable to reach routing server. Please check your connection."
          );
        }
      } finally {
        setLoading(false);
      }
    },
    [intervalMi]
  );

  // Auto-load default Denver -> Salt Lake City corridor on initial mount
  useEffect(() => {
    const preset = CORRIDOR_PRESETS[0];
    const dep = new Date(Date.now() + 30 * 60 * 1000).toISOString();
    submitTrip({
      origin: preset.origin,
      destination: preset.destination,
      departure_time: dep,
      load_lb: preset.load_lb,
    });
  }, []);

  const ikey = String(intervalMi) as "10" | "25" | "50";
  const currentSummaries = trip ? trip.intervals[ikey].summaries : [];
  const activeRouteId =
    selectedRouteId || currentSummaries[0]?.route_id || null;
  const activeCheckpoints =
    trip && activeRouteId
      ? trip.intervals[ikey].checkpoints[activeRouteId] || []
      : [];
  const allRoutesHaveNoTravel =
    currentSummaries.length > 0 &&
    currentSummaries.every((s) => s.has_no_travel);

  const changeInterval = useCallback((next: SamplingInterval) => {
    setIntervalMi(next);
    setInspectedCheckpoint(null);
  }, []);

  const selectRoute = useCallback((routeId: string) => {
    setSelectedRouteId(routeId);
    setInspectedCheckpoint(null);
  }, []);

  return {
    trip,
    loading,
    intervalMi,
    activeRouteId,
    currentSummaries,
    activeCheckpoints,
    allRoutesHaveNoTravel,
    inspectedCheckpoint,
    globalError,
    fieldErrors,
    submitTrip,
    changeInterval,
    selectRoute,
    setInspectedCheckpoint,
  };
}
