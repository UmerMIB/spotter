import React, { useEffect, useRef, useState } from "react";
import { MapPin, Loader2 } from "lucide-react";
import { searchGeocode } from "../api/client";
import type { GeocodePlace } from "../types";

interface Props {
  id: string;
  label: string;
  placeholder: string;
  value: string;
  selectedPlace: GeocodePlace | null;
  error?: string | null;
  onChangeText: (text: string) => void;
  onSelectPlace: (place: GeocodePlace) => void;
}

/**
 * Debounced place-search input backed by `/api/geocode` (Photon with Nominatim fallback).
 */
export const LocationAutocomplete: React.FC<Props> = ({
  id,
  label,
  placeholder,
  value,
  selectedPlace,
  error,
  onChangeText,
  onSelectPlace,
}) => {
  const [suggestions, setSuggestions] = useState<GeocodePlace[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    const trimmed = value.trim();
    if (
      trimmed.length < 2 ||
      (selectedPlace && selectedPlace.label === trimmed)
    ) {
      setSuggestions([]);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const res = await searchGeocode(trimmed, controller.signal);
        setSuggestions(res);
        setOpen(res.length > 0);
      } catch {
        // Ignore abort or transient autocomplete errors; submit will validate
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }, 300);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [value, selectedPlace]);

  return (
    <div className="field-group" ref={containerRef}>
      <label htmlFor={id} className="field-label">
        {label}
      </label>
      <div className={`input-wrapper ${error ? "input-error" : ""}`}>
        <MapPin size={16} className="input-icon" />
        <input
          id={id}
          type="text"
          value={value}
          placeholder={placeholder}
          autoComplete="off"
          onFocus={() => {
            if (suggestions.length > 0) setOpen(true);
          }}
          onChange={(e) => {
            onChangeText(e.target.value);
            setOpen(true);
          }}
          className="text-input"
        />
        {loading && <Loader2 size={15} className="spin-icon" />}
      </div>
      {error && <div className="field-error-msg">{error}</div>}
      {open && suggestions.length > 0 && (
        <ul className="autocomplete-dropdown" role="listbox">
          {suggestions.map((item, idx) => (
            <li
              key={`${item.lat}-${item.lon}-${idx}`}
              role="option"
              className="autocomplete-item"
              onMouseDown={(e) => {
                e.preventDefault();
                onSelectPlace(item);
                setOpen(false);
              }}
            >
              <MapPin size={14} className="item-pin" />
              <div className="item-text">
                <span className="item-primary">{item.label}</span>
                <span className="item-coords">
                  {item.lat.toFixed(3)}, {item.lon.toFixed(3)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
