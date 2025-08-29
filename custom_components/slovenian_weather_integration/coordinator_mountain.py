from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession  # <-- PRAVILNO

from .const import CONF_MOUNTAIN_REGION, DEFAULT_MOUNTAIN_REGION
from .arso_mountain.client_mountain import MountainClient

_LOGGER = logging.getLogger(__name__)

class MountainDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Koordinator za gorsko napoved (MVP)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        super().__init__(
            hass,
            _LOGGER,
            name="ARSO Mountain Coordinator",
            update_interval=timedelta(minutes=60),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            session = async_get_clientsession(self.hass)
            region = self.entry.options.get(CONF_MOUNTAIN_REGION, DEFAULT_MOUNTAIN_REGION)
            client = MountainClient(session, region=region)
            data = await client.fetch_upper_air_html()
            return data
        except Exception as err:
            raise UpdateFailed(str(err)) from err
