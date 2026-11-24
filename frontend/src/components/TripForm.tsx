import React, { useState } from "react";
import {
  Calendar,
  Compass,
  Loader2,
  Navigation,
  Scale,
  SlidersHorizontal,
} from "lucide-react";
import {
  FORECAST_MAX_DAYS,
  MAX_LOAD_LB,
  SAMPLING_INTERVALS,
} from "../constants";
import { LocationAutocomplete } from "./LocationAutocomplete";
import type { GeocodePlace, SamplingInterval } from "../types";

export interface CorridorPreset {
  name: string;
  origin: GeocodePlace;
  destination: GeocodePlace;
  load_lb: number;
}

export const CORRIDOR_PRESETS: CorridorPreset[] = [
  {
    name: "Denver → Salt Lake City (I-80 / I-70)",
    origin: { label: "Denver, CO, US", lat: 39.7392, lon: -104.9903 },
    destination: { label: "Salt Lake City, UT, US", lat: 40.7608, lon: -111.891 },
    load_lb: 42000,
  },
  {
    name: "Chicago → Minneapolis (I-90 / I-94)",
    origin: { label: "Chicago, IL, US", lat: 41.8781, lon: -87.6298 },
    destination: { label: "Minneapolis, MN, US", lat: 44.9778, lon: -93.265 },
    load_lb: 36000,
  },
  {
    name: "Seattle → Boise (I-84 Mountain Pass)",
    origin: { label: "Seattle, WA, US", lat: 47.6062, lon: -122.3321 },
    destination: { label: "Boise, ID, US", lat: 43.615, lon: -116.2023 },
    load_lb: 45000,
  },
];

function getDefaultLocalDateTime(): string {
  const d = new Date(Date.now() + 30 * 60 * 1000);
  d.setMinutes(Math.ceil(d.getMinutes() / 15) * 15, 0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
}

interface Props {
  loading: boolean;
  intervalMi: SamplingInterval;
  onChangeInterval: (interval: SamplingInterval) => void;
  fieldErrors: Record<string, string>;
  onSubmitTrip: (params: {
    origin: string | GeocodePlace;
    destination: string | GeocodePlace;
    departure_time: string;
    load_lb: number;
  }) => void;
}

/**
 * Trip planning form for origin/destination, departure time, load weight (lb),
 * and instant 10 / 25 / 50 mile weather sampling interval switching.
 */
export const TripForm: React.FC<Props> = ({
  loading,
  intervalMi,
  onChangeInterval,
  fieldErrors,
  onSubmitTrip,
}) => {
  const [originText, setOriginText] = useState(CORRIDOR_PRESETS[0].origin.label);
  const [originPlace, setOriginPlace] = useState<GeocodePlace | null>(
    CORRIDOR_PRESETS[0].origin
  );
  const [destText, setDestText] = useState(
    CORRIDOR_PRESETS[0].destination.label
  );
  const [destPlace, setDestPlace] = useState<GeocodePlace | null>(
    CORRIDOR_PRESETS[0].destination
  );
  const [departureLocal, setDepartureLocal] = useState<string>(
    getDefaultLocalDateTime
  );
  const [loadLb, setLoadLb] = useState<string>("42000");
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  const combinedErrors = { ...fieldErrors, ...localErrors };

  const handleApplyPreset = (preset: CorridorPreset) => {
    setOriginText(preset.origin.label);
    setOriginPlace(preset.origin);
    setDestText(preset.destination.label);
    setDestPlace(preset.destination);
    setLoadLb(String(preset.load_lb));
    setLocalErrors({});
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};

    if (!originText.trim()) {
      errs.origin = "Origin city or address is required.";
    }
    if (!destText.trim()) {
      errs.destination = "Destination city or address is required.";
    }

    const parsedDate = new Date(departureLocal);
    if (Number.isNaN(parsedDate.getTime())) {
      errs.departure_time = "Please enter a valid departure date and time.";
    } else {
      const now = Date.now();
      if (parsedDate.getTime() < now - 60 * 60 * 1000) {
        errs.departure_time = "Departure time cannot be in the past.";
      } else if (
        parsedDate.getTime() >
        now + FORECAST_MAX_DAYS * 86400 * 1000 + 3600 * 1000
      ) {
        errs.departure_time = `Departure time must be within the next ${FORECAST_MAX_DAYS} days.`;
      }
    }

    const numericLoad = Number(loadLb);
    if (
      loadLb.trim() === "" ||
      Number.isNaN(numericLoad) ||
      numericLoad < 0 ||
      numericLoad > MAX_LOAD_LB
    ) {
      errs.load_lb = `Load weight must be between 0 and ${MAX_LOAD_LB.toLocaleString()} lb.`;
    }

    setLocalErrors(errs);
    if (Object.keys(errs).length > 0) return;

    onSubmitTrip({
      origin:
        originPlace && originPlace.label === originText.trim()
          ? originPlace
          : originText.trim(),
      destination:
        destPlace && destPlace.label === destText.trim()
          ? destPlace
          : destText.trim(),
      departure_time: parsedDate.toISOString(),
      load_lb: numericLoad,
    });
  };

  return (
    <form className="trip-form" onSubmit={handleSubmit} noValidate>
      <div className="presets-bar">
        <span className="presets-label">
          <Compass size={13} /> Sample Freight Corridors:
        </span>
        <div className="presets-chips">
          {CORRIDOR_PRESETS.map((p) => (
            <button
              key={p.name}
              type="button"
              className="preset-chip"
              onClick={() => handleApplyPreset(p)}
            >
              {p.name}
            </button>
          ))}
        </div>
      </div>

      <LocationAutocomplete
        id="origin-input"
        label="Origin"
        placeholder="e.g. Denver, CO"
        value={originText}
        selectedPlace={originPlace}
        error={combinedErrors.origin}
        onChangeText={(txt) => {
          setOriginText(txt);
          setOriginPlace(null);
          setLocalErrors((prev) => ({ ...prev, origin: "" }));
        }}
        onSelectPlace={(place) => {
          setOriginText(place.label);
          setOriginPlace(place);
          setLocalErrors((prev) => ({ ...prev, origin: "" }));
        }}
      />

      <LocationAutocomplete
        id="destination-input"
        label="Destination"
        placeholder="e.g. Salt Lake City, UT"
        value={destText}
        selectedPlace={destPlace}
        error={combinedErrors.destination}
        onChangeText={(txt) => {
          setDestText(txt);
          setDestPlace(null);
          setLocalErrors((prev) => ({ ...prev, destination: "" }));
        }}
        onSelectPlace={(place) => {
          setDestText(place.label);
          setDestPlace(place);
          setLocalErrors((prev) => ({ ...prev, destination: "" }));
        }}
      />

      <div className="form-row-2">
        <div className="field-group">
          <label htmlFor="departure-input" className="field-label">
            Departure Date / Time
          </label>
          <div
            className={`input-wrapper ${
              combinedErrors.departure_time ? "input-error" : ""
            }`}
          >
            <Calendar size={16} className="input-icon" />
            <input
              id="departure-input"
              type="datetime-local"
              value={departureLocal}
              onChange={(e) => {
                setDepartureLocal(e.target.value);
                setLocalErrors((prev) => ({ ...prev, departure_time: "" }));
              }}
              className="text-input"
            />
          </div>
          {combinedErrors.departure_time && (
            <div className="field-error-msg">
              {combinedErrors.departure_time}
            </div>
          )}
        </div>

        <div className="field-group">
          <label htmlFor="load-input" className="field-label">
            Load Weight (lb)
          </label>
          <div
            className={`input-wrapper ${
              combinedErrors.load_lb ? "input-error" : ""
            }`}
          >
            <Scale size={16} className="input-icon" />
            <input
              id="load-input"
              type="number"
              min={0}
              max={MAX_LOAD_LB}
              step={1000}
              value={loadLb}
              onChange={(e) => {
                setLoadLb(e.target.value);
                setLocalErrors((prev) => ({ ...prev, load_lb: "" }));
              }}
              className="text-input"
            />
          </div>
          <div className="load-quick-pills">
            {[
              { label: "20k lb (Light)", val: "20000" },
              { label: "35k lb (>30k Rule)", val: "35000" },
              { label: "45k lb (>40k Rule)", val: "45000" },
            ].map((pill) => (
              <button
                key={pill.val}
                type="button"
                className={`mini-pill ${loadLb === pill.val ? "active" : ""}`}
                onClick={() => {
                  setLoadLb(pill.val);
                  setLocalErrors((prev) => ({ ...prev, load_lb: "" }));
                }}
              >
                {pill.label}
              </button>
            ))}
          </div>
          {combinedErrors.load_lb && (
            <div className="field-error-msg">{combinedErrors.load_lb}</div>
          )}
        </div>
      </div>

      <div className="interval-Submit-row">
        <div className="interval-selector">
          <span className="field-label">
            <SlidersHorizontal size={13} /> Weather Sample Interval
          </span>
          <div className="segmented-toggle" role="group" aria-label="Sampling Interval">
            {SAMPLING_INTERVALS.map((val) => (
              <button
                key={val}
                type="button"
                className={`seg-btn ${intervalMi === val ? "active" : ""}`}
                onClick={() => onChangeInterval(val)}
              >
                {val} mi
              </button>
            ))}
          </div>
        </div>

        <button
          type="submit"
          className="submit-btn"
          disabled={loading}
          data-testid="analyze-routes-btn"
        >
          {loading ? (
            <>
              <Loader2 size={17} className="spin-icon" /> Analyzing Weather &
              Routes...
            </>
          ) : (
            <>
              <Navigation size={17} /> Analyze 3 Safe Routes
            </>
          )}
        </button>
      </div>
    </form>
  );
};
