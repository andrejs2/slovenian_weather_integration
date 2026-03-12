"""Binary sensor platform for the Slovenian Weather Integration.

Provides weather warning binary sensors:
- 1 overview binary sensor (ON when any warning level >= 2)
- 10 per-type binary sensors (one per warning type, disabled by default)
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import CONF_LOCATION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .arso_weather.warnings_client import WARNING_TYPES
from .const import (
    DOMAIN,
    MODULE_WARNINGS,
    ArsoConfigEntry,
    get_enabled_modules,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ArsoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ARSO warning binary sensor entities."""
    modules = get_enabled_modules(entry)
    if not modules.get(MODULE_WARNINGS):
        return

    warn_coord = entry.runtime_data.warnings_coordinator
    if not warn_coord:
        return

    location_name = entry.data[CONF_LOCATION]
    device_info = DeviceInfo(
        identifiers={(DOMAIN, f"{location_name}_warnings")},
        name=f"ARSO Opozorila ({location_name})",
        manufacturer="ARSO",
        model="Vremenska opozorila",
        entry_type="service",
    )

    entities: list[BinarySensorEntity] = []

    # Overview binary sensor (always enabled)
    entities.append(
        ArsoWarningsOverviewBinarySensor(
            warn_coord, device_info, entry.entry_id, location_name,
        )
    )

    # Per-type binary sensors (disabled by default)
    for type_code, type_name in WARNING_TYPES.items():
        entities.append(
            ArsoWarningTypeBinarySensor(
                warn_coord, device_info, entry.entry_id,
                location_name, type_code, type_name,
            )
        )

    async_add_entities(entities)


class ArsoWarningsOverviewBinarySensor(
    CoordinatorEntity[DataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor ON when any weather warning level >= 2 is active.

    Attributes include count and highest severity level.
    """

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_icon = "mdi:weather-hurricane"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_info: DeviceInfo,
        config_entry_id: str,
        location_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._location_name = location_name
        self._attr_name = "Aktivno opozorilo"
        self._attr_device_info = device_info
        self._attr_unique_id = (
            f"{DOMAIN}_{config_entry_id}_warnings_active"
        )

    def _active_warnings(self) -> list[dict]:
        if not self.coordinator.data:
            return []
        return [
            w for w in self.coordinator.data.get("warnings", [])
            if w.get("level", 0) >= 2
        ]

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return len(self._active_warnings()) > 0

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self.coordinator.data:
            return None
        active = self._active_warnings()
        attrs: dict[str, Any] = {
            "regija": self.coordinator.data.get("region_name", ""),
            "stevilo_opozoril": len(active),
        }
        if active:
            attrs["najvisja_stopnja"] = max(
                w.get("level", 0) for w in active
            )
            attrs["najvisja_barva"] = active[0].get("level_color", "")
            attrs["tipi"] = [w.get("type_name", "") for w in active]
        return attrs

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self.coordinator.data is not None


class ArsoWarningTypeBinarySensor(
    CoordinatorEntity[DataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor for a specific warning type (e.g., wind, rain).

    ON when that specific warning type has level >= 2.
    Disabled by default — users enable the types they care about.
    """

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_entity_registry_enabled_default = False

    # Icon mapping per warning type
    _TYPE_ICONS: dict[str, str] = {
        "wind": "mdi:weather-windy",
        "rain": "mdi:weather-pouring",
        "TS": "mdi:weather-lightning",
        "snow": "mdi:weather-snowy-heavy",
        "ice": "mdi:snowflake-alert",
        "Tx": "mdi:thermometer-high",
        "Tn": "mdi:thermometer-low",
        "forestFire": "mdi:fire-alert",
        "avalanche": "mdi:landslide",
        "coastal": "mdi:waves",
    }

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_info: DeviceInfo,
        config_entry_id: str,
        location_name: str,
        type_code: str,
        type_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._type_code = type_code
        self._type_name = type_name
        self._attr_name = f"Opozorilo {type_name}"
        self._attr_device_info = device_info
        self._attr_icon = self._TYPE_ICONS.get(type_code, "mdi:alert")
        self._attr_unique_id = (
            f"{DOMAIN}_{config_entry_id}_warnings_{type_code.lower()}"
        )

    def _type_warning(self) -> dict | None:
        """Get warning for this type (level >= 2)."""
        if not self.coordinator.data:
            return None
        for w in self.coordinator.data.get("warnings", []):
            if w.get("type") == self._type_code and w.get("level", 0) >= 2:
                return w
        return None

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return self._type_warning() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self.coordinator.data:
            return None
        w = self._type_warning()
        if not w:
            return {"tip": self._type_code, "tip_ime": self._type_name}
        return {
            "tip": self._type_code,
            "tip_ime": self._type_name,
            "stopnja": w.get("level"),
            "barva": w.get("level_color"),
            "opis_stopnje": w.get("level_text"),
            "naslov": w.get("title"),
            "opis": w.get("description", ""),
            "navodila": w.get("instruction", ""),
            "veljavnost_od": w.get("onset"),
            "veljavnost_do": w.get("expires"),
        }

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self.coordinator.data is not None
