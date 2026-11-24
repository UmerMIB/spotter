import React from "react";
import {
  AlertOctagon,
  AlertTriangle,
  Award,
  CheckCircle2,
  Clock,
  Info,
  Route,
} from "lucide-react";
import { ORDERED_RISK_LEVELS } from "../constants";
import type { Checkpoint, RouteSummary } from "../types";
import {
  RISK_BG_COLORS,
  RISK_COLORS,
  formatDuration,
} from "../utils/heatmap";
import { CheckpointLogTable } from "./CheckpointLogTable";

interface Props {
  summaries: RouteSummary[];
  selectedRouteId: string | null;
  onSelectRoute: (routeId: string) => void;
  selectedCheckpoints: Checkpoint[];
  onSelectCheckpoint: (cp: Checkpoint) => void;
  loadLb: number;
}

/**
 * Ranked route summary cards with mileage risk bars, recommendation explanations,
 * and the clickable Checkpoint Weather Log table for the active route.
 */
export const RouteCards: React.FC<Props> = ({
  summaries,
  selectedRouteId,
  onSelectRoute,
  selectedCheckpoints,
  onSelectCheckpoint,
  loadLb,
}) => (
  <div className="routes-panel">
    <div className="panel-section-header">
      <h3>
        <Route size={16} /> Route Options & Safety Ranking
      </h3>
      <span className="load-badge">Load: {loadLb.toLocaleString()} lb</span>
    </div>

    <div className="route-cards-list">
      {summaries.map((s) => {
        const isSelected = s.route_id === selectedRouteId;
        const totalMi = Math.max(0.1, s.distance_mi);

        return (
          <div
            key={s.route_id}
            data-testid={`route-card-${s.route_id}`}
            className={`route-card ${isSelected ? "selected" : ""} ${
              s.recommended ? "recommended" : ""
            } ${s.has_no_travel ? "has-no-travel" : ""}`}
            onClick={() => onSelectRoute(s.route_id)}
          >
            <div className="route-card-top">
              <div className="route-title-group">
                <span className="rank-pill">#{s.rank}</span>
                <h4 className="route-name">{s.route_name}</h4>
              </div>
              <div className="route-badges">
                {s.recommended && (
                  <span className="badge-recommended">
                    <Award size={13} /> RECOMMENDED
                  </span>
                )}
                {s.has_no_travel && (
                  <span className="badge-no-travel">
                    <AlertOctagon size={13} /> NO TRAVEL
                  </span>
                )}
              </div>
            </div>

            <div className="route-metrics-grid">
              <div className="metric-box">
                <span className="metric-label">Travel Time</span>
                <span className="metric-val">
                  <Clock size={13} /> {formatDuration(s.duration_s)}
                </span>
              </div>
              <div className="metric-box">
                <span className="metric-label">Distance</span>
                <span className="metric-val">
                  {s.distance_mi.toFixed(0)} mi
                </span>
              </div>
              <div className="metric-box">
                <span className="metric-label">Avg Risk (1–5)</span>
                <span className="metric-val">
                  {s.avg_score !== null ? s.avg_score.toFixed(2) : "N/A"}
                </span>
              </div>
              <div className="metric-box">
                <span className="metric-label">Forecast Cov.</span>
                <span className="metric-val">{s.coverage_pct.toFixed(0)}%</span>
              </div>
            </div>

            <div className="risk-bar-track" title="Route miles by weather risk">
              {ORDERED_RISK_LEVELS.map((lvl) => {
                const mi = s.miles_by_level[lvl] || 0;
                if (mi <= 0) return null;
                return (
                  <div
                    key={lvl}
                    style={{
                      width: `${(mi / totalMi) * 100}%`,
                      backgroundColor: RISK_COLORS[lvl],
                    }}
                    className="risk-bar-seg"
                    title={`${lvl}: ${mi.toFixed(1)} mi`}
                  />
                );
              })}
            </div>

            <div className="miles-chips">
              {ORDERED_RISK_LEVELS.map((lvl) => {
                const mi = s.miles_by_level[lvl] || 0;
                if (mi <= 0) return null;
                return (
                  <span
                    key={lvl}
                    className="mile-chip"
                    style={{
                      backgroundColor: RISK_BG_COLORS[lvl],
                      borderColor: RISK_COLORS[lvl],
                      color: "#f8fafc",
                    }}
                  >
                    <span
                      className="chip-dot"
                      style={{ backgroundColor: RISK_COLORS[lvl] }}
                    />
                    {lvl}: <strong>{mi.toFixed(0)} mi</strong>
                  </span>
                );
              })}
            </div>

            <div className="route-reasons">
              {s.reasons.map((reason, idx) => (
                <div key={idx} className="reason-item">
                  {s.recommended ? (
                    <CheckCircle2 size={13} className="icon-green" />
                  ) : (
                    <Info size={13} className="icon-muted" />
                  )}
                  <span>{reason}</span>
                </div>
              ))}
              {s.warnings.map((warn, idx) => (
                <div key={`w-${idx}`} className="warning-item">
                  <AlertTriangle size={13} className="icon-warn" />
                  <span>{warn}</span>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>

    <CheckpointLogTable
      checkpoints={selectedCheckpoints}
      onSelectCheckpoint={onSelectCheckpoint}
    />
  </div>
);
