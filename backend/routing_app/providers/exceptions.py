from __future__ import annotations


class ProviderError(Exception):
    """Base exception raised by external geocoding, routing, or weather adapters."""

    def __init__(
        self,
        message: str,
        provider: str,
        status_code: int = 503,
        field: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.status_code = status_code
        self.field = field


class GeocodingNotFoundError(ProviderError):
    """Raised when an origin or destination cannot be resolved to coordinates."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(
            message=message,
            provider="geocoding",
            status_code=400,
            field=field,
        )


class RoutingUnavailableError(ProviderError):
    """Raised when OSRM fails after retries or finds no drivable route."""

    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(
            message=message,
            provider="routing",
            status_code=status_code,
        )


class WeatherProviderError(ProviderError):
    """Raised when the weather provider encounters an unrecoverable error."""

    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(
            message=message,
            provider="weather",
            status_code=status_code,
        )
