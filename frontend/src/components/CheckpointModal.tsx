import React from "react";
import { ShieldAlert, X } from "lucide-react";
import type { Checkpoint } from "../types";
import {
  RISK_BG_COLORS,
  RISK_COLORS,
  formatUtcTimeShort,
} from "../utils/heatmap";

interface Props {
  checkpoint: Checkpoint | null;
  onClose: () => void;
}

/**
 * Floating checkpoint inspector card displaying truck ETA, steady/gust wind,
 * rain/snow rates, load-rule triggers, and contributing risk factors.
 */
export const CheckpointModal: React.FC<Props> = ({ checkpoint, onClose }) => {
  if (!checkpoint) return null;

  return (
    <div
      className="checkpoint-inspector-card"
      data-testid="checkpoint-inspector"
    >
      <div className="inspector-header">
        <div>
          <span className="inspector-subtitle">{checkpoint.route_name}</span>
          <h4>
            Mile {checkpoint.mile.toFixed(1)}{" "}
            <span className="inspector-seg">
              (covers {checkpoint.segment_miles.toFixed(1)} mi)
            </span>
          </h4>
        </div>
        <button
          type="button"
          className="close-btn"
          onClick={onClose}
          aria-label="Close checkpoint details"
        >
          <X size={16} />
        </button>
      </div>

      <div className="inspector-eta-row">
        <span>
          Truck ETA: <strong>{formatUtcTimeShort(checkpoint.eta_utc)}</strong>
        </span>
        <span
          className="level-tag"
          style={{
            backgroundColor: RISK_BG_COLORS[checkpoint.level],
            borderColor: RISK_COLORS[checkpoint.level],
          }}
        >
          <span
            className="chip-dot"
            style={{ backgroundColor: RISK_COLORS[checkpoint.level] }}
          />
          {checkpoint.level}
        </span>
      </div>

      <div className="inspector-conditions-grid">
        <div className="cond-item">
          <span className="cond-label">Wind (Steady / Gust)</span>
          <span className="cond-val">
            {checkpoint.wind_mph !== null
              ? `${checkpoint.wind_mph.toFixed(1)} mph`
              : "N/A"}
            {checkpoint.gust_mph !== null
              ? ` / ${checkpoint.gust_mph.toFixed(1)} mph`
              : ""}
          </span>
          <span
            className="cond-lvl"
            style={{ color: RISK_COLORS[checkpoint.wind_level] }}
          >
            {checkpoint.wind_level}
            {checkpoint.load_rule_triggered && " (Load Rule)"}
          </span>
        </div>

        <div className="cond-item">
          <span className="cond-label">Rain Rate</span>
          <span className="cond-val">
            {checkpoint.rain_in_hr !== null
              ? `${checkpoint.rain_in_hr.toFixed(2)} in/hr`
              : "N/A"}
          </span>
          <span
            className="cond-lvl"
            style={{ color: RISK_COLORS[checkpoint.rain_level] }}
          >
            {checkpoint.rain_level}
          </span>
        </div>

        <div className="cond-item">
          <span className="cond-label">Snow Rate</span>
          <span className="cond-val">
            {checkpoint.snow_in_hr !== null
              ? `${checkpoint.snow_in_hr.toFixed(2)} in/hr`
              : "N/A"}
          </span>
          <span
            className="cond-lvl"
            style={{ color: RISK_COLORS[checkpoint.snow_level] }}
          >
            {checkpoint.snow_level}
          </span>
        </div>
      </div>

      <div className="inspector-factors">
        {checkpoint.factors.map((f, i) => (
          <div key={i} className="factor-line">
            {checkpoint.load_rule_triggered ? (
              <ShieldAlert size={13} className="icon-warn" />
            ) : null}
            <span>{f}</span>
          </div>
        ))}
      </div>
    </div>
  );
};
