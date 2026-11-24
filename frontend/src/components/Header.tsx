import React from "react";
import { HelpCircle, ShieldCheck, Truck } from "lucide-react";

interface Props {
  truckMaxSpeedMph: number;
  onOpenRules: () => void;
}

/**
 * Top application bar displaying branding, truck speed cap badge, and rules modal trigger.
 */
export const Header: React.FC<Props> = ({
  truckMaxSpeedMph,
  onOpenRules,
}) => (
  <header className="app-header">
    <div className="brand-group">
      <div className="brand-logo">
        <Truck size={20} />
      </div>
      <div>
        <h1>Spotter Weather-Aware Truck Routing</h1>
        <p className="brand-subtitle">
          Real-Time Corridor Weather Risk, Load Rules & 48h Forecast
          Intelligence
        </p>
      </div>
    </div>

    <div className="header-actions">
      <div className="speed-cap-pill">
        <ShieldCheck size={14} /> Truck Speed Cap:{" "}
        <strong>{truckMaxSpeedMph} mph</strong>
      </div>
      <button type="button" className="rules-btn" onClick={onOpenRules}>
        <HelpCircle size={15} /> Risk & Load Rules
      </button>
    </div>
  </header>
);
