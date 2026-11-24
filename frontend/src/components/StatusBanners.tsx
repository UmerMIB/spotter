import React from "react";
import { AlertOctagon, AlertTriangle } from "lucide-react";

interface Props {
  globalError: string | null;
  allRoutesHaveNoTravel: boolean;
  notices: string[];
  loadingInitial: boolean;
}

/**
 * Displays provider/server error alerts, all-route No Travel advisories,
 * partial-route notices, and the initial loading skeleton.
 */
export const StatusBanners: React.FC<Props> = ({
  globalError,
  allRoutesHaveNoTravel,
  notices,
  loadingInitial,
}) => (
  <>
    {globalError && (
      <div className="alert-banner alert-error" role="alert">
        <AlertOctagon size={18} />
        <div>
          <strong>Routing / Weather Error</strong>
          <p>{globalError}</p>
        </div>
      </div>
    )}

    {allRoutesHaveNoTravel && (
      <div className="alert-banner alert-notravel" role="alert">
        <AlertOctagon size={18} />
        <div>
          <strong>NO TRAVEL ADVISORY ACROSS ALL CORRIDORS</strong>
          <p>
            Every available route encounters No Travel conditions at your
            scheduled departure and load weight. Delay departure or reduce load
            if possible.
          </p>
        </div>
      </div>
    )}

    {notices.length > 0 && (
      <div className="alert-banner alert-warn" role="status">
        <AlertTriangle size={17} />
        <div>
          {notices.map((n, idx) => (
            <p key={idx}>{n}</p>
          ))}
        </div>
      </div>
    )}

    {loadingInitial && (
      <div className="loading-skeleton" data-testid="loading-skeleton">
        <div className="skeleton-card" />
        <div className="skeleton-card" />
        <div className="skeleton-card" />
      </div>
    )}
  </>
);
