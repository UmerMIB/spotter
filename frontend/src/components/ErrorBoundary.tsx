import React from "react";
import { AlertOctagon, RotateCcw } from "lucide-react";

interface Props {
  children: React.ReactNode;
  fallbackTitle?: string;
}

interface State {
  hasError: boolean;
  errorMessage: string;
}

/**
 * React Error Boundary preventing unhandled UI or WebGL map exceptions
 * from crashing the entire page. Provides an inline reset action.
 */
export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, errorMessage: "" };
  }

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      errorMessage: error.message || "Unexpected rendering error",
    };
  }

  handleReset = (): void => {
    this.setState({ hasError: false, errorMessage: "" });
  };

  render(): React.ReactNode {
    if (this.state.hasError) {
      return (
        <div className="error-boundary-card" role="alert">
          <AlertOctagon size={28} className="icon-warn" />
          <h3>{this.props.fallbackTitle ?? "Something went wrong"}</h3>
          <p>{this.state.errorMessage}</p>
          <button
            type="button"
            className="rules-btn"
            onClick={this.handleReset}
          >
            <RotateCcw size={14} /> Try Again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
