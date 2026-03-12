"""Client for fetching weather data from ARSO."""

from __future__ import annotations

import logging

import aiohttp

from .models import (
    MODEL_MAPPING,
    ObservationDetails,
    ObservationTimelineEntry,
    merge_observation_data,
)
from .station_map import OBSERVATION_STATIONS

_LOGGER = logging.getLogger(__name__)

PRIMARY_STATION_BASE_URL = (
    "https://meteo.arso.gov.si/uploads/probase/www/observ/surface/json"
    "/sl//recent/observationAms_METEO-{location_id}_history.json"
)
OFFICIAL_ARSO_API_URL = (
    "https://vreme.arso.gov.si/api/1.0/location/?location={location_id}"
)
LOCATIONS_URL = (
    "https://vreme.arso.gov.si/uploads/probase/www/fproduct/json/sl/locations.json"
)


class ArsoApiError(Exception):
    """Error communicating with the ARSO API."""


class ArsoWeather:
    """Client to fetch weather data from ARSO."""

    def __init__(
        self,
        location_name: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self.location_name = location_name
        self.location_id = OBSERVATION_STATIONS.get(location_name)
        self._session = session
        self.latitude: float | None = None
        self.longitude: float | None = None

    async def get_all_locations(self) -> list[str]:
        """Return list of all locations provided by ARSO."""
        data = await self._fetch_json(LOCATIONS_URL)
        return [loc["properties"]["title"] for loc in data["features"]]

    async def get_weather(self) -> dict[str, list]:
        """Fetch combined weather data from ARSO API.

        Returns dict with keys: "current", "forecast1h", "forecast3h", "forecast6h", "forecast24h".
        Values are lists of Pydantic model instances.

        The official API provides forecast data for all locations.
        It also returns an "observation" key with the real-time current
        conditions (weather phenomenon, cloud cover, temp, wind, etc.).
        Primary stations (in OBSERVATION_STATIONS) additionally have
        detailed measurements from the observationAms endpoint (dew point,
        visibility, ground temps, solar radiation, etc.).
        """
        # Fetch official API data (available for all 247 locations)
        official_url = OFFICIAL_ARSO_API_URL.format(
            location_id=self.location_name
        )
        official_data = await self._fetch_json(official_url)

        # Extract coordinates from GeoJSON if not yet known
        if self.latitude is None:
            self._extract_coordinates(official_data)

        # Extract raw timeline data per forecast type
        raw_timelines = self._extract_timelines(official_data)

        # Parse forecasts into Pydantic models
        forecasts: dict[str, list] = {}
        for key, timeline in raw_timelines.items():
            if key in MODEL_MAPPING:
                forecasts[key] = [
                    MODEL_MAPPING[key].model_validate(entry)
                    for entry in timeline
                ]

        # Build current observation from the best available source:
        # 1. "observation" key from official API — real-time current conditions
        # 2. forecast3h[0] — fallback proxy (next 3h forecast window)
        observation_proxy = self._build_observation_proxy(
            official_data, raw_timelines
        )

        if self.location_id:
            # Primary station: get detailed measurements from observationAms
            station_url = PRIMARY_STATION_BASE_URL.format(
                location_id=self.location_id
            )
            try:
                station_data = await self._fetch_json(station_url)
                station_parsed = self._parse_primary_station_data(station_data)
                detailed = ObservationDetails.model_validate(station_parsed)
                # Merge: observation_proxy provides condition/cloud fields,
                # detailed provides precise measurements (dew point, etc.)
                observation = merge_observation_data(
                    observation_proxy, detailed
                )
            except (ArsoApiError, ValueError) as err:
                _LOGGER.warning(
                    "Failed to get primary station data for %s: %s",
                    self.location_name,
                    err,
                )
                observation = observation_proxy
        else:
            observation = observation_proxy

        return {"current": [observation], **forecasts}

    async def _fetch_json(self, url: str) -> dict:
        """Fetch JSON data from a URL.

        Raises ArsoApiError on any request failure.
        """
        _LOGGER.debug("Requesting data from %s", url)
        try:
            async with self._session.get(url) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
                _LOGGER.debug("Successfully received response from %s", url)
                return data
        except aiohttp.ClientResponseError as err:
            raise ArsoApiError(
                f"HTTP {err.status} for {url}: {err.message}"
            ) from err
        except aiohttp.ClientError as err:
            raise ArsoApiError(f"Request failed for {url}: {err}") from err

    def _extract_timelines(self, data: dict) -> dict[str, list[dict]]:
        """Extract raw timeline data from official API response.

        The official API returns GeoJSON with forecast data nested under:
        data[forecast_type]["features"][0]["properties"]["days"][]["timeline"][]
        """
        result: dict[str, list[dict]] = {}
        for key in ("forecast1h", "forecast3h", "forecast6h", "forecast24h"):
            if key not in data:
                continue
            try:
                timeline: list[dict] = []
                for day in data[key]["features"][0]["properties"]["days"]:
                    timeline.extend(day["timeline"])
                result[key] = timeline
                _LOGGER.debug(
                    "Extracted %d entries for %s", len(timeline), key
                )
            except (KeyError, IndexError, TypeError) as err:
                _LOGGER.warning("Failed to extract %s timeline: %s", key, err)
        return result

    def _extract_coordinates(self, data: dict) -> None:
        """Extract lat/lon from GeoJSON API response."""
        for key in ("forecast1h", "forecast3h", "forecast6h", "forecast24h"):
            if key not in data:
                continue
            try:
                coords = data[key]["features"][0]["geometry"]["coordinates"]
                # GeoJSON uses [longitude, latitude]
                self.longitude = float(coords[0])
                self.latitude = float(coords[1])
                _LOGGER.debug(
                    "Location coordinates: lat=%s, lon=%s",
                    self.latitude,
                    self.longitude,
                )
                return
            except (KeyError, IndexError, TypeError, ValueError):
                continue

    @staticmethod
    def _parse_primary_station_data(data: dict) -> dict:
        """Parse primary weather station data (observationAms).

        Returns the most recent timeline entry as a raw dict.
        The history endpoint stores entries chronologically — the last
        entry in the last day is the latest observation.
        """
        features = data.get("features")
        if not features or not isinstance(features, list):
            raise ArsoApiError(
                "Station has no features data (station may be offline)"
            )
        try:
            feature = features[0]
            days = feature["properties"]["days"]
            timeline = days[-1]["timeline"]
            return timeline[-1]
        except (KeyError, IndexError, TypeError) as err:
            raise ArsoApiError(
                f"Invalid station data structure: {err}"
            ) from err

    @staticmethod
    def _extract_observation(data: dict) -> dict | None:
        """Extract real-time observation from official API response.

        The "observation" key contains current conditions (weather phenomenon,
        cloud cover, temperature, wind) directly from the weather station.
        """
        if "observation" not in data:
            return None
        try:
            feature = data["observation"]["features"][0]
            days = feature["properties"]["days"]
            return days[-1]["timeline"][-1]
        except (KeyError, IndexError, TypeError) as err:
            _LOGGER.debug("Failed to extract observation: %s", err)
            return None

    def _build_observation_proxy(
        self,
        official_data: dict,
        raw_timelines: dict[str, list[dict]],
    ) -> ObservationTimelineEntry:
        """Build current observation from the best available source.

        Priority:
        1. "observation" key — real-time current conditions from the station
        2. forecast3h[0] — fallback (next 3h forecast window, less accurate)
        """
        obs_raw = self._extract_observation(official_data)
        if obs_raw:
            _LOGGER.debug(
                "Using real-time observation for %s", self.location_name
            )
            return ObservationTimelineEntry.model_validate(obs_raw)

        forecast3h = raw_timelines.get("forecast3h", [])
        if forecast3h:
            _LOGGER.debug(
                "No observation available, using forecast3h proxy for %s",
                self.location_name,
            )
            return ObservationTimelineEntry.model_validate(forecast3h[0])

        return ObservationTimelineEntry()
