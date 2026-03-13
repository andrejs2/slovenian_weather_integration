"""Image platform for the Slovenian Weather Integration — webcams + radar."""

from __future__ import annotations

import logging
from collections import deque

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
import homeassistant.util.dt as dt_util

from .const import (
    DOMAIN,
    EU_WEATHER_MAP_TODAY_URL,
    EU_WEATHER_MAP_TOMORROW_URL,
    MODULE_RADAR,
    MODULE_WEBCAMS,
    RADAR_ANIMATION_URL,
    RADAR_CURRENT_URL,
    ArsoConfigEntry,
    get_enabled_modules,
)

_LOGGER = logging.getLogger(__name__)

# Compass directions with display names
WEBCAM_DIRECTIONS: dict[str, str] = {
    "n": "Sever",
    "ne": "Severovzhod",
    "e": "Vzhod",
    "se": "Jugovzhod",
    "s": "Jug",
    "sw": "Jugozahod",
    "w": "Zahod",
    "nw": "Severozahod",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ArsoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ARSO image entities (webcams + radar)."""
    modules = get_enabled_modules(entry)
    entities: list[ImageEntity] = []

    # --- Webcam images (all from WebcamCoordinator) ---
    if modules.get(MODULE_WEBCAMS):
        webcam_coord = entry.runtime_data.webcam_coordinator
        if webcam_coord and webcam_coord.data:
            for loc_name, cams in webcam_coord.data.items():
                device = DeviceInfo(
                    identifiers={(DOMAIN, f"{loc_name}_webcams")},
                    name=f"ARSO Spletne kamere {loc_name}",
                    manufacturer="ARSO",
                    model="Spletne kamere",
                    entry_type="service",
                )
                for cam in cams:
                    direction = cam.get("direction", "")
                    if direction in WEBCAM_DIRECTIONS:
                        entities.append(
                            ArsoWebcamImage(
                                webcam_coord, entry, device,
                                loc_name, direction,
                            )
                        )

    # --- Radar images ---
    if modules.get(MODULE_RADAR):
        try:
            radar_device = DeviceInfo(
                identifiers={(DOMAIN, "radar")},
                name="ARSO Radar",
                manufacturer="ARSO",
                model="Radar",
                entry_type="service",
            )
            entities.append(
                ArsoRadarImage(
                    hass, entry, radar_device,
                    name="Radar",
                    unique_suffix="radar_current",
                    url=RADAR_CURRENT_URL,
                    content_type="image/gif",
                )
            )
            entities.append(
                ArsoRadarImage(
                    hass, entry, radar_device,
                    name="Radar animacija",
                    unique_suffix="radar_animation",
                    url=RADAR_ANIMATION_URL,
                    content_type="image/gif",
                )
            )
        except Exception:
            _LOGGER.exception("Failed to create radar image entities")

        # European weather map images (under radar module)
        try:
            eu_map_device = DeviceInfo(
                identifiers={(DOMAIN, "eu_weather_maps")},
                name="ARSO Vremenske karte",
                manufacturer="ARSO",
                model="Vremenske karte",
                entry_type="service",
            )
            entities.append(
                ArsoRadarImage(
                    hass, entry, eu_map_device,
                    name="Vremenska karta Evrope danes",
                    unique_suffix="eu_weather_map_today",
                    url=EU_WEATHER_MAP_TODAY_URL,
                    content_type="image/png",
                )
            )
            entities.append(
                ArsoRadarImage(
                    hass, entry, eu_map_device,
                    name="Vremenska karta Evrope jutri",
                    unique_suffix="eu_weather_map_tomorrow",
                    url=EU_WEATHER_MAP_TOMORROW_URL,
                    content_type="image/png",
                )
            )
        except Exception:
            _LOGGER.exception("Failed to create EU weather map entities")

    if entities:
        _LOGGER.info("Adding %d ARSO image entities", len(entities))
        async_add_entities(entities)


class ArsoWebcamImage(
    CoordinatorEntity[DataUpdateCoordinator], ImageEntity
):
    """Representation of an ARSO webcam image.

    All webcams (primary + extra locations) use the WebcamCoordinator
    which fetches from the dedicated webcam JSON API.
    """

    _attr_has_entity_name = True
    _attr_content_type = "image/jpeg"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ArsoConfigEntry,
        device_info: DeviceInfo,
        location_name: str,
        direction: str,
    ) -> None:
        """Initialize the webcam image entity."""
        super().__init__(coordinator)
        # BaseCoordinatorEntity.__init__ does not call super().__init__(),
        # so ImageEntity.__init__ is never reached via MRO.
        self.access_tokens: deque[str] = deque([], 2)
        self.async_update_token()
        self._location_name = location_name
        self._direction = direction
        self._attr_name = f"Kamera {location_name} {WEBCAM_DIRECTIONS[direction]}"
        self._attr_unique_id = (
            f"{DOMAIN}_{entry.entry_id}_cam_{location_name}_{direction}"
        )
        self._attr_device_info = device_info

    def _get_image_url(self) -> str | None:
        """Get the latest webcam image URL from coordinator data."""
        if not self.coordinator.data:
            return None
        cams = self.coordinator.data.get(self._location_name, [])
        for cam in cams:
            if cam.get("direction") == self._direction:
                return cam.get("image_url")
        return None

    async def async_image(self) -> bytes | None:
        """Fetch and return the webcam image bytes."""
        url = self._get_image_url()
        if not url:
            return None
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
                _LOGGER.warning("Webcam HTTP %s for %s", resp.status, url)
        except Exception:
            _LOGGER.debug(
                "Failed to fetch webcam from %s", url, exc_info=True
            )
        return None

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Expose the source URL for debugging."""
        return {"image_url": self._get_image_url()}


class ArsoRadarImage(ImageEntity):
    """ARSO radar image (current or animation).

    Radar images are public static URLs that don't need a coordinator —
    they are fetched directly each time HA requests the image.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ArsoConfigEntry,
        device_info: DeviceInfo,
        *,
        name: str,
        unique_suffix: str,
        url: str,
        content_type: str,
    ) -> None:
        """Initialize the radar image entity."""
        super().__init__(hass)
        self._url = url
        self._attr_name = name
        self._attr_content_type = content_type
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{unique_suffix}"
        self._attr_device_info = device_info

    async def async_image(self) -> bytes | None:
        """Fetch the radar image bytes from ARSO."""
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(self._url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    self._attr_image_last_updated = dt_util.utcnow()
                    return data
                _LOGGER.warning("Radar HTTP %s for %s", resp.status, self._url)
        except Exception:
            _LOGGER.debug(
                "Failed to fetch radar from %s", self._url, exc_info=True
            )
        return None

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Expose the source URL."""
        return {"image_url": self._url}
