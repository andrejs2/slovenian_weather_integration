import logging
from datetime import timedelta
import asyncio

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
import homeassistant.helpers.aiohttp_client as hass_aiohttp

from .arso_weather import ArsoWeather

from homeassistant.const import CONF_LOCATION

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(minutes=2)
REQUEST_TIMEOUT = 120

# Define the type of data the coordinator will hold
CoordinatorDataType = dict[str, list]


class ArsoDataUpdateCoordinator(DataUpdateCoordinator[CoordinatorDataType]):
    """Class to manage fetching ARSO weather data."""

    config_entry: ConfigEntry
    client: ArsoWeather

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the data update coordinator."""
        self.hass = hass
        self.config_entry = entry
        location = entry.data[CONF_LOCATION]

        session = hass_aiohttp.async_get_clientsession(hass)

        self.client = ArsoWeather(location_name=location, session=session)
        coordinator_name = f"ARSO Weather Coordinator ({location})"

        super().__init__(
            hass, _LOGGER, name=coordinator_name, update_interval=UPDATE_INTERVAL
        )

    async def _async_update_data(self) -> CoordinatorDataType:
        """Fetch combined weather data from ARSO API via the library."""
        location = self.config_entry.data.get(CONF_LOCATION, "Unknown")

        _LOGGER.debug("Attempting to fetch combined ARSO data for %s", location)

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                all_weather_data = await self.client.get_weather()

            # validation
            if (
                not all_weather_data
                or "current" not in all_weather_data
                or not all_weather_data["current"]
            ):
                _LOGGER.warning(
                    "Fetched ARSO data is missing 'current' key or data for %s",
                    location,
                )

            _LOGGER.debug(
                "Successfully fetched combined ARSO data for %s. Keys: %s",
                location,
                list(all_weather_data.keys()),
            )

            return all_weather_data

        except TimeoutError as err:
            _LOGGER.warning("Timeout fetching ARSO data for %s", location)
            raise UpdateFailed("API request timed out") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error fetching ARSO data for %s", location)
            raise UpdateFailed(f"Unexpected error: {err}") from err
