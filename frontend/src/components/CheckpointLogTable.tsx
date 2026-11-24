import React from "react";
import { ShieldAlert, Wind } from "lucide-react";
import type { Checkpoint } from "../types";
import {
  RISK_BG_COLORS,
  RISK_COLORS,
  formatUtcTimeShort,
} from "../utils/heatmap";

interface Props {
  checkpoints: Checkpoint[];
  onSelectCheckpoint: (cp: Checkpoint) => void;
}

/**
 * Scrollable table of sampled checkpoints for the selected route showing truck ETA,
 * steady/gust wind, rain, snow, and risk level. Clicking a row focuses the map.
 */
export const CheckpointLogTable: React.FC<Props> = ({
  checkpoints,
  onSelectCheckpoint,
}) => {
  if (checkpoints.length === 0) return null;

  return (
    <div className="checkpoints-table-section">
      <div className="panel-section-header">
        <h3>
          <Wind size={16} /> Checkpoint Weather Log ({checkpoints.length}{" "}
          samples)
        </h3>
        <span className="hint-text">Click row to focus map</span>
      </div>
      <div className="checkpoints-scroll">
        <table className="checkpoints-table">
          <thead>
            <tr>
              <th>Mile</th>
              <th>ETA</th>
              <th>Wind / Gust</th>
              <th>Rain</th>
              <th>Snow</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            {checkpoints.map((cp) => (
              <tr
                key={`${cp.route_id}-${cp.index}`}
                onClick={() => onSelectCheckpoint(cp)}
                className={`cp-row ${
                  cp.level === "No Travel"
                    ? "cp-row-notravel"
                    : cp.level === "Severe"
                    ? "cp-row-severe"
                    : ""
                }`}
              >
                <td className="mono">{cp.mile.toFixed(0)} mi</td>
                <td className="mono">{formatUtcTimeShort(cp.eta_utc)}</td>
                <td className="mono">
                  {cp.wind_mph !== null ? `${cp.wind_mph.toFixed(0)}` : "—"}
                  {cp.gust_mph !== null
                    ? ` (g ${cp.gust_mph.toFixed(0)}) mph`
                    : " mph"}
                </td>
                <td className="mono">
                  {cp.rain_in_hr !== null
                    ? `${cp.rain_in_hr.toFixed(2)}"`
                    : "—"}
                </td>
                <td className="mono">
                  {cp.snow_in_hr !== null
                    ? `${cp.snow_in_hr.toFixed(2)}"`
                    : "—"}
                </td>
                <td>
                  <span
                    className="level-tag"
                    style={{
                      backgroundColor: RISK_BG_COLORS[cp.level],
                      borderColor: RISK_COLORS[cp.level],
                    }}
                  >
                    <span
                      className="chip-dot"
                      style={{ backgroundColor: RISK_COLORS[cp.level] }}
                    />
                    {cp.level}
                    {cp.load_rule_triggered && (
                      <ShieldAlert
                        size={12}
                        aria-label="Escalated by load weight rule"
                      />
                    )}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
