import React from "react";
import { X } from "lucide-react";

interface Props {
  open: boolean;
  onClose: () => void;
}

/**
 * Modal dialog documenting weather classification thresholds, truck load rules,
 * and route recommendation ranking criteria.
 */
export const RulesModal: React.FC<Props> = ({ open, onClose }) => {
  if (!open) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="rules-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Risk and Load Rules"
      >
        <div className="modal-header">
          <h2>Weather Risk Thresholds & Load Rules</h2>
          <button
            type="button"
            className="close-btn"
            onClick={onClose}
            aria-label="Close rules modal"
          >
            <X size={18} />
          </button>
        </div>

        <table className="rules-table">
          <thead>
            <tr>
              <th>Condition</th>
              <th>Low (1)</th>
              <th>Moderate (2)</th>
              <th>High (3)</th>
              <th>Severe (4)</th>
              <th>No Travel (5)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <strong>Wind (mph)</strong>
              </td>
              <td>&lt; 25</td>
              <td>[25, 35)</td>
              <td>[35, 45)</td>
              <td>[45, 55)</td>
              <td>&ge; 55</td>
            </tr>
            <tr>
              <td>
                <strong>Rain (in/hr)</strong>
              </td>
              <td>&lt; 0.10</td>
              <td>[0.10, 0.25)</td>
              <td>[0.25, 0.50)</td>
              <td>[0.50, 1.00]</td>
              <td>&gt; 1.00</td>
            </tr>
            <tr>
              <td>
                <strong>Snow (in/hr)</strong>
              </td>
              <td>&lt; 0.5</td>
              <td>[0.5, 1.0)</td>
              <td>[1.0, 2.0)</td>
              <td>[2.0, 3.0]</td>
              <td>&gt; 3.0</td>
            </tr>
          </tbody>
        </table>

        <div className="rules-columns">
          <div>
            <h3>Load Weight Rules (Wind)</h3>
            <ul>
              <li>
                <strong>&ge; 55 mph</strong> &rarr; <strong>No Travel</strong>{" "}
                for any load
              </li>
              <li>
                <strong>45–54 mph + &gt; 30,000 lb</strong> &rarr;{" "}
                <strong>No Travel</strong>
              </li>
              <li>
                <strong>35–44 mph + &gt; 40,000 lb</strong> &rarr;{" "}
                <strong>Severe</strong>
              </li>
            </ul>
          </div>
          <div>
            <h3>Recommendation Ranking</h3>
            <ol>
              <li>
                Fewest <strong>No Travel</strong> miles (&ge;90% forecast
                coverage required)
              </li>
              <li>
                Fewest <strong>Severe</strong> miles
              </li>
              <li>
                Fewest <strong>High</strong> miles
              </li>
              <li>
                Lowest distance-weighted <strong>average risk score</strong>
              </li>
              <li>
                Shortest <strong>travel time</strong> (at 65 mph truck speed cap)
              </li>
            </ol>
          </div>
        </div>
      </div>
    </div>
  );
};
