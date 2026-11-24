import React from "react";
import { Pause, Play, Truck } from "lucide-react";
import { formatUtcTimeShort } from "../utils/heatmap";

interface Props {
  hours: number;
  startUtc: string;
  isPlaying: boolean;
  onTogglePlay: () => void;
  onScrubHour: (hour: number) => void;
  sliderInputRef: React.RefObject<HTMLInputElement>;
  hourBadgeRef: React.RefObject<HTMLSpanElement>;
  timeLabelRef: React.RefObject<HTMLSpanElement>;
  truckHudRef: React.RefObject<HTMLDivElement>;
}

/**
 * Bottom 0-48 hour forecast timeline scrubber and animated truck position HUD.
 * Uses imperative DOM refs for text labels so dragging does not re-render React.
 */
export const ForecastSlider: React.FC<Props> = ({
  hours,
  startUtc,
  isPlaying,
  onTogglePlay,
  onScrubHour,
  sliderInputRef,
  hourBadgeRef,
  timeLabelRef,
  truckHudRef,
}) => (
  <div className="forecast-slider-bar" data-testid="forecast-slider-bar">
    <div className="slider-header-row">
      <div className="slider-title-group">
        <button
          type="button"
          className="play-btn"
          onClick={onTogglePlay}
          aria-label={isPlaying ? "Pause forecast" : "Play 48h forecast"}
        >
          {isPlaying ? <Pause size={15} /> : <Play size={15} />}
        </button>
        <span className="slider-title">Corridor Forecast Timeline (0–48h)</span>
        <span ref={hourBadgeRef} className="hour-offset-badge">
          +0h
        </span>
        <span ref={timeLabelRef} className="hour-utc-label">
          {formatUtcTimeShort(startUtc)}
        </span>
      </div>

      <div className="truck-position-hud">
        <Truck size={15} className="truck-icon" />
        <div ref={truckHudRef} className="truck-hud-text">
          Truck at Origin (0 mi)
        </div>
      </div>
    </div>

    <div className="slider-track-row">
      <span className="tick-label">0h (Dep)</span>
      <input
        ref={sliderInputRef}
        type="range"
        min={0}
        max={hours - 1}
        step={1}
        defaultValue={0}
        aria-label="0 to 48 hour forecast slider"
        className="forecast-range-input"
        onChange={(e) => onScrubHour(Number(e.target.value))}
      />
      <span className="tick-label">+48h</span>
    </div>
  </div>
);
