class ArsoWeatherError(Exception):
    """Base exception for the ArsoWeather library."""

    pass


class ArsoApiError(ArsoWeatherError):
    """Exception raised for errors from the ARSO API."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"API Error {status_code}: {message}")


class ArsoDataError(ArsoWeatherError):
    """Exception raised for errors parsing or finding data in the API response."""

    pass
