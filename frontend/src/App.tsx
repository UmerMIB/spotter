import React, { Suspense, lazy, useState } from "react";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Header } from "./components/Header";
import { RouteCards } from "./components/RouteCards";
import { RulesModal } from "./components/RulesModal";
import { StatusBanners } from "./components/StatusBanners";
import { TripForm } from "./components/TripForm";
import { DEFAULT_TRUCK_MAX_SPEED_MPH } from "./constants";
import { useTripPlanner } from "./hooks/useTripPlanner";

const LazyMapView = lazy(() =>
  import("./components/MapView").then((m) => ({ default: m.MapView }))
);

/**
 * Root application shell coordinating trip form submission, error/advisory banners,
 * route ranking cards, and the lazy-loaded MapLibre forecast visualization.
 */
export const App: React.FC = () => {
  const {
    trip,
    loading,
    intervalMi,
    activeRouteId,
    currentSummaries,
    activeCheckpoints,
    allRoutesHaveNoTravel,
    inspectedCheckpoint,
    globalError,
    fieldErrors,
    submitTrip,
    changeInterval,
    selectRoute,
    setInspectedCheckpoint,
  } = useTripPlanner();

  const [showRulesModal, setShowRulesModal] = useState(false);

  return (
    <div className="app-shell">
      <Header
        truckMaxSpeedMph={
          trip?.request.truck_max_speed_mph ?? DEFAULT_TRUCK_MAX_SPEED_MPH
        }
        onOpenRules={() => setShowRulesModal(true)}
      />

      <main className="workspace-grid">
        <aside className="sidebar-column">
          <TripForm
            loading={loading}
            intervalMi={intervalMi}
            onChangeInterval={changeInterval}
            fieldErrors={fieldErrors}
            onSubmitTrip={submitTrip}
          />

          <StatusBanners
            globalError={globalError}
            allRoutesHaveNoTravel={allRoutesHaveNoTravel}
            notices={trip?.notices ?? []}
            loadingInitial={loading && !trip}
          />

          {trip && (
            <RouteCards
              summaries={currentSummaries}
              selectedRouteId={activeRouteId}
              onSelectRoute={selectRoute}
              selectedCheckpoints={activeCheckpoints}
              onSelectCheckpoint={setInspectedCheckpoint}
              loadLb={trip.request.load_lb}
            />
          )}
        </aside>

        <section className="map-column">
          <ErrorBoundary fallbackTitle="Map Rendering Error">
            <Suspense
              fallback={
                <div className="map-loading-fallback">
                  Loading interactive weather map...
                </div>
              }
            >
              <LazyMapView
                trip={trip}
                intervalMi={intervalMi}
                selectedRouteId={activeRouteId}
                onSelectRoute={selectRoute}
                inspectedCheckpoint={inspectedCheckpoint}
                onInspectCheckpoint={setInspectedCheckpoint}
              />
            </Suspense>
          </ErrorBoundary>
        </section>
      </main>

      <RulesModal
        open={showRulesModal}
        onClose={() => setShowRulesModal(false)}
      />
    </div>
  );
};
