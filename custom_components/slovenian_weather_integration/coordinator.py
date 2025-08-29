from __future__ import annotations

import logging
import asyncio
from datetime import timedelta
from typing import Any

from aiohttp import ClientError  # <-- pravilni uvoz
from homeassistant.const import CONF_LOCATION
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.helpers.aiohttp_client as hass_aiohttp

from .arso_weather.client import ArsoWeather

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(minutes=10)  # prilagodi po želji (prej 2 min)
REQUEST_TIMEOUT = 120

CoordinatorDataType = dict[str, list[Any]]


class ArsoDataUpdateCoordinator(DataUpdateCoordinator[CoordinatorDataType]):
    """Fetch & združevanje ARSO podatkov."""

    config_entry: ConfigEntry
    client: ArsoWeather

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.config_entry = entry

        location_name = entry.data[CONF_LOCATION]
        session = hass_aiohttp.async_get_clientsession(hass)

        self.client = ArsoWeather(location_name=location_name, session=session)

        super().__init__(
            hass,
            _LOGGER,
            name=f"ARSO Weather Data Coordinator ({location_name})",
            update_interval=UPDATE_INTERVAL,
        )
        _LOGGER.debug(
            "Coordinator initialized for %s with update interval %s",
            location_name,
            UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> CoordinatorDataType:
        """Prenesi in vrni združene podatke iz odjemalca."""
        location_name = self.config_entry.data.get(CONF_LOCATION, "Unknown Location")
        _LOGGER.debug("Fetching combined weather data for %s", location_name)

        try:
            # Celoten klic na klienta ovijemo v timeout
            async with asyncio.timeout(REQUEST_TIMEOUT):
                all_weather_data = await self.client.get_weather()

            if not all_weather_data:
                _LOGGER.warning("Empty data for %s", location_name)
                raise UpdateFailed("No data returned from weather client")

            current_ok = isinstance(all_weather_data.get("current"), list)
            if not current_ok:
                _LOGGER.warning(
                    "Missing or invalid 'current' for %s (type=%s)",
                    location_name,
                    type(all_weather_data.get("current")).__name__,
                )

            _LOGGER.debug(
                "Fetched keys for %s: %s",
                location_name,
                list(all_weather_data.keys()),
            )
            if "current" in all_weather_data:
                _LOGGER.debug(
                    "Current items: %d",
                    len(all_weather_data.get("current") or []),
                )
            if "forecast24h" in all_weather_data:
                _LOGGER.debug(
                    "Forecast24h items: %d",
                    len(all_weather_data.get("forecast24h") or []),
                )

            return all_weather_data

        except asyncio.TimeoutError as err:
            _LOGGER.warning(
                "Timeout fetching data for %s after %s seconds",
                location_name,
                REQUEST_TIMEOUT,
            )
            raise UpdateFailed(f"API request timed out after {REQUEST_TIMEOUT}s") from err

        except ClientError as err:
            _LOGGER.error("Network client error for %s: %s", location_name, err)
            raise UpdateFailed(f"Network client error: {err}") from err

        except UpdateFailed:
            # že pravilno opremljen
            raise

        except Exception as err:
            _LOGGER.exception(
                "Unexpected error fetching data for %s: %s",
                location_name,
                err,
            )
            raise UpdateFailed(f"Unexpected error: {err}") from err

    async def _async_close_client_session(self) -> None:
        """Zapri sejo, če jo klient upravlja sam (trenutno ne)."""
        if hasattr(self.client, "close") and callable(self.client.close):
            await self.client.close()
            _LOGGER.debug("Closed ArsoWeather client session via coordinator")
