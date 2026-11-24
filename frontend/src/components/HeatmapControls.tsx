import React from "react";
import { CloudRain, CloudSnow, Eye, EyeOff, Flame, Wind } from "lucide-react";
import { LEGEND_RISK_LEVELS } from "../constants";
import type { HeatmapMetric } from "../types";
import { RISK_COLORS } from "../utils/heatmap";

const METRIC_TABS: readonly {
  id: HeatmapMetric;
  label: string;
  icon: typeof Flame;
}[] = [
  { id: "risk", label: "Combined Risk", icon: Flame },
  { id: "wind", label: "Wind (mph)", icon: Wind },
  { id: "rain", label: "Rain (in/hr)", icon: CloudRain },
  { id: "snow", label: "Snow (in/hr)", icon: CloudSnow },
];

interface Props {
  metric: HeatmapMetric;
  showHeatmap: boolean;
  onChangeMetric: (metric: HeatmapMetric) => void;
  onToggleHeatmap: () => void;
}

/**
 * Top map overlay containing the heatmap metric switcher (Risk/Wind/Rain/Snow),
 * visibility toggle, and risk color legend.
 */
export const HeatmapControls: React.FC<Props> = ({
  metric,
  showHeatmap,
  onChangeMetric,
  onToggleHeatmap,
}) => (
  <div className="map-top-bar">
    <div className="heatmap-controls-card">
      <div className="metric-tabs" role="tablist" aria-label="Heatmap Metric">
        {METRIC_TABS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={metric === item.id}
              className={`metric-tab ${metric === item.id ? "active" : ""}`}
              onClick={() => onChangeMetric(item.id)}
            >
              <Icon size={14} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>

      <button
        type="button"
        className="toggle-heatmap-btn"
        onClick={onToggleHeatmap}
        title="Toggle Corridor Weather Heatmap"
      >
        {showHeatmap ? <Eye size={14} /> : <EyeOff size={14} />}
        <span>{showHeatmap ? "Heatmap On" : "Heatmap Off"}</span>
      </button>
    </div>

    <div className="risk-legend-card">
      {LEGEND_RISK_LEVELS.map((lvl) => (
        <span key={lvl} className="legend-item">
          <span
            className="legend-dot"
            style={{ backgroundColor: RISK_COLORS[lvl] }}
          />
          {lvl}
        </span>
      ))}
    </div>
  </div>
);
