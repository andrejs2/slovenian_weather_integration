import logging
from datetime import timedelta
import asyncio # Make sure asyncio is imported if not already
from typing import Any # Added Any for broader type hinting if necessary

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
import homeassistant.helpers.aiohttp_client as hass_aiohttp

# Assuming your client and models are correctly structured in the .arso_weather sub-package
from .arso_weather.client import ArsoWeather
# Models are used by the client, coordinator primarily deals with the dict returned by client.get_weather()
# from .arso_weather.models import ObservationDetails # Example, not directly used here but good to keep in mind

from homeassistant.const import CONF_LOCATION

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(minutes=10) # Original was 2 minutes, adjust as needed for API rate limits
REQUEST_TIMEOUT = 120 # Timeout for the entire update operation, including all API calls by the client

# Define the type of data the coordinator will hold.
# The client now returns dict[str, list[PydanticModelInstance]], which fits dict[str, list].
CoordinatorDataType = dict[str, list[Any]] # Using Any for the list elements for flexibility


class ArsoDataUpdateCoordinator(DataUpdateCoordinator[CoordinatorDataType]):
    """Class to manage fetching ARSO weather and other related data."""

    config_entry: ConfigEntry
    client: ArsoWeather

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the data update coordinator."""
        self.hass = hass
        self.config_entry = entry
        location_name = entry.data[CONF_LOCATION] # Changed from location to location_name for clarity

        session = hass_aiohttp.async_get_clientsession(hass)

        # Pass the session to the ArsoWeather client
        self.client = ArsoWeather(location_name=location_name, session=session)
        coordinator_name = f"ARSO Weather Data Coordinator ({location_name})"

        super().__init__(
            hass, _LOGGER, name=coordinator_name, update_interval=UPDATE_INTERVAL
        )
        _LOGGER.debug(f"Coordinator initialized for {location_name} with update interval {UPDATE_INTERVAL}")

    async def _async_update_data(self) -> CoordinatorDataType:
        """Fetch combined weather data from ARSO API and other sources via the library."""
        location_name = self.config_entry.data.get(CONF_LOCATION, "Unknown Location")

        _LOGGER.debug("Attempting to fetch combined weather data for %s", location_name)

        try:
            # The client's get_weather method now handles all data fetching, including UV index.
            # The timeout here applies to the entire self.client.get_weather() call.
            async with asyncio.timeout(REQUEST_TIMEOUT):
                all_weather_data = await self.client.get_weather()

            # Basic validation: Check if data was returned and if 'current' key exists and is not empty.
            # The client should ensure 'current' key is present, even if with an empty list or None model.
            if not all_weather_data:
                _LOGGER.warning("Fetched weather data is empty for %s.", location_name)
                raise UpdateFailed("No data returned from weather client.")
            
            if "current" not in all_weather_data or not isinstance(all_weather_data.get("current"), list):
                _LOGGER.warning(
                    "Fetched data is missing 'current' key or 'current' is not a list for %s. Data: %s",
                    location_name, str(all_weather_data.get("current"))
                )
                # Depending on strictness, you might raise UpdateFailed or try to proceed.
                # For now, we'll allow proceeding if other data (forecasts) might be present.
                # However, entities relying on 'current' will likely fail or show as unavailable.
                # Ensure client.get_weather() always returns {"current": [model_or_none]} or {"current": []}
                if not all_weather_data.get("current"): # If current is empty list or None
                     _LOGGER.info("Current weather data specifically is missing for %s.", location_name)


            _LOGGER.debug(
                "Successfully fetched combined data for %s. Top-level keys: %s",
                location_name,
                list(all_weather_data.keys()),
            )
            # Example: Log how many items are in 'current' and 'forecast24h' if they exist
            if "current" in all_weather_data:
                _LOGGER.debug(f"Number of 'current' observation items: {len(all_weather_data['current'])}")
            if "forecast24h" in all_weather_data:
                 _LOGGER.debug(f"Number of 'forecast24h' items: {len(all_weather_data['forecast24h'])}")


            return all_weather_data

        except TimeoutError as err:
            _LOGGER.warning("Timeout fetching combined weather data for %s after %s seconds.", location_name, REQUEST_TIMEOUT)
            raise UpdateFailed(f"API request timed out after {REQUEST_TIMEOUT} seconds.") from err
        except aiohttp.ClientError as err: # Catch client errors from the session used by ArsoWeather client
            _LOGGER.error("ClientError during data update for %s: %s", location_name, err)
            raise UpdateFailed(f"Network client error: {err}") from err
        except UpdateFailed: # Re-raise UpdateFailed if client itself raises it
            raise
        except Exception as err:
            _LOGGER.exception("Unexpected error fetching combined weather data for %s: %s", location_name, err)
            raise UpdateFailed(f"Unexpected error during data update: {err}") from err

    async def _async_close_client_session(self) -> None:
        """Close the client session if it's managed by the coordinator's client."""
        # This assumes your ArsoWeather client has a 'close' method.
        if hasattr(self.client, 'close') and callable(self.client.close):
            await self.client.close()
            _LOGGER.debug("Closed ArsoWeather client session via coordinator.")
