from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, HttpRequest, HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from routing_app.pipeline import TripValidationError, build_trip_bundle
from routing_app.providers.exceptions import ProviderError
from routing_app.providers.geocoding import search_places

logger = logging.getLogger(__name__)


@api_view(["GET"])
def health_view(request: Request) -> Response:
    """Return service liveness status for health checks and deployment probes."""
    return Response({"status": "ok", "service": "weather-aware-truck-routing"})


@api_view(["GET"])
def geocode_view(request: Request) -> Response:
    """Search North America places matching query parameter `q`.

    Proxies Photon (with Nominatim fallback) so API caching, rate-limit
    headers, and US/Canada biasing stay server-side.
    """
    query = (request.query_params.get("q") or "").strip()
    if len(query) < 2:
        return Response({"results": []})

    try:
        results = search_places(query, limit=6)
        return Response({"results": results})
    except ProviderError as exc:
        return Response(
            {
                "error": exc.message,
                "provider": exc.provider,
                "field": exc.field,
            },
            status=exc.status_code,
        )
    except Exception as exc:
        logger.exception("Unexpected error during geocoding lookup for %r", query)
        return Response(
            {
                "error": f"Unexpected geocoding error: {exc}",
                "provider": "server",
                "field": None,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def trips_view(request: Request) -> Response:
    """Compute 3 weather-aware truck routes, 10/25/50 mi checkpoints, and a 0-48h heatgrid.

    Expects JSON body with `origin`, `destination`, `departure_time` (ISO-8601),
    and `load_lb` (0..80000). Returns HTTP 400 on validation/geocoding errors,
    HTTP 503 if upstream routing fails, or HTTP 500 with structured JSON on
    unexpected server errors.
    """
    payload = request.data if isinstance(request.data, dict) else {}
    try:
        bundle = build_trip_bundle(payload)
        return Response(bundle, status=status.HTTP_200_OK)
    except TripValidationError as exc:
        return Response(
            {
                "error": exc.message,
                "field": exc.field,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    except ProviderError as exc:
        return Response(
            {
                "error": exc.message,
                "provider": exc.provider,
                "field": exc.field,
            },
            status=exc.status_code,
        )
    except Exception as exc:
        logger.exception("Unexpected error building trip bundle")
        return Response(
            {
                "error": f"Unexpected server error while planning trip: {exc}",
                "provider": "server",
                "field": None,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def spa_index_view(request: HttpRequest) -> HttpResponse:
    """Serve the built React SPA entrypoint when running as a single Render/Django service."""
    index_path: Path = settings.FRONTEND_DIST_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path.open("rb"), content_type="text/html")
    return HttpResponse(
        "Spotter Weather-Aware Truck Routing API is running. Visit /api/health.",
        content_type="text/plain",
    )
