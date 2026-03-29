"""Config flow for the Slovenian Weather Integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_LOCATION
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .arso_weather import ArsoWeather
from .arso_weather.agrometeo_client import AGRO_STATIONS
from .arso_weather.air_quality_client import AQ_STATIONS
from .arso_weather.utci_client import UTCI_STATIONS
from .arso_weather.mountain_client import MOUNTAIN_REGIONS
from .arso_weather.ski_client import SKI_RESORTS
from .arso_weather.avalanche_client import AVALANCHE_REGIONS
from .arso_weather.station_map import ALL_LOCATIONS, OBSERVATION_STATIONS
from .arso_weather.webcam_stations import WEBCAM_STATIONS
from .const import (
    DOMAIN,
    GLOBAL_MODULES,
    MODULE_AGROMETEO,
    MODULE_AIR_QUALITY,
    MODULE_AVALANCHE,
    MODULE_BIO_WEATHER,
    MODULE_UTCI,
    MODULE_MOUNTAIN,
    MODULE_RADAR,
    MODULE_SKI,
    MODULE_TEXT_FORECAST,
    MODULE_WARNINGS,
    MODULE_WEBCAMS,
    MODULE_WEATHER,
    get_enabled_modules,
)

_LOGGER = logging.getLogger(__name__)

# Config option keys for selections
CONF_SKI_RESORTS = "ski_resorts"
CONF_MOUNTAIN_REGIONS = "mountain_regions"
CONF_WEBCAM_LOCATIONS = "webcam_locations"
CONF_AGRO_STATIONS = "agro_stations"
CONF_AQ_STATIONS = "aq_stations"
CONF_UTCI_STATIONS = "utci_stations"
CONF_AVALANCHE_REGIONS = "avalanche_regions"


def _get_claimed_global_modules(
    hass: HomeAssistant,
    exclude_entry_id: str | None = None,
) -> set[str]:
    """Return global modules already enabled by another config entry."""
    claimed: set[str] = set()
    for entry in hass.config_entries.async_entries(DOMAIN):
        if exclude_entry_id and entry.entry_id == exclude_entry_id:
            continue
        modules = get_enabled_modules(entry)
        for mod in GLOBAL_MODULES:
            if modules.get(mod):
                claimed.add(mod)
    return claimed


def _build_module_schema(
    claimed: set[str],
    defaults: dict[str, bool] | None = None,
) -> vol.Schema:
    """Build module selection schema, hiding claimed global modules."""
    if defaults is None:
        defaults = {}
    fields: dict[vol.Optional, type] = {
        vol.Optional(
            MODULE_WEBCAMS, default=defaults.get(MODULE_WEBCAMS, False)
        ): bool,
        vol.Optional(
            MODULE_WARNINGS, default=defaults.get(MODULE_WARNINGS, False)
        ): bool,
    }
    for mod in (
        MODULE_TEXT_FORECAST,
        MODULE_BIO_WEATHER,
        MODULE_MOUNTAIN,
        MODULE_SKI,
        MODULE_RADAR,
        MODULE_AGROMETEO,
        MODULE_AIR_QUALITY,
        MODULE_UTCI,
        MODULE_AVALANCHE,
    ):
        if mod not in claimed:
            fields[vol.Optional(mod, default=defaults.get(mod, False))] = bool
    return vol.Schema(fields)


def _extract_modules(user_input: dict, claimed: set[str]) -> dict[str, bool]:
    """Build modules dict from form input, respecting claimed globals."""
    result: dict[str, bool] = {
        MODULE_WEATHER: True,
        MODULE_WEBCAMS: user_input.get(MODULE_WEBCAMS, False),
        MODULE_WARNINGS: user_input.get(MODULE_WARNINGS, False),
    }
    for mod in (
        MODULE_TEXT_FORECAST,
        MODULE_BIO_WEATHER,
        MODULE_MOUNTAIN,
        MODULE_SKI,
        MODULE_RADAR,
        MODULE_AGROMETEO,
        MODULE_AIR_QUALITY,
        MODULE_UTCI,
        MODULE_AVALANCHE,
    ):
        result[mod] = (
            user_input.get(mod, False) if mod not in claimed else False
        )
    return result


class ArsoWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for ARSO Weather."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._location: str | None = None
        self._modules: dict[str, bool] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ArsoOptionsFlow:
        """Get the options flow handler."""
        return ArsoOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Location selection."""
        errors: dict[str, str] = {}

        session = async_get_clientsession(self.hass)
        client = ArsoWeather(location_name="Ljubljana", session=session)

        locations: list[str] = []
        try:
            locations_raw = await client.get_all_locations()
            if isinstance(locations_raw, list) and all(
                isinstance(loc, str) for loc in locations_raw
            ):
                locations = sorted(locations_raw)
            else:
                errors["base"] = "invalid_location_data"

            if not locations and "base" not in errors:
                errors["base"] = "no_locations_found"
        except Exception:
            _LOGGER.warning(
                "ARSO locations API unavailable, using station list fallback"
            )
            # Fallback to hardcoded location list when API is down
            locations = sorted(ALL_LOCATIONS)

        if user_input is not None and not errors:
            selected = user_input[CONF_LOCATION]
            if selected not in locations:
                errors["base"] = "invalid_selection"
            else:
                await self.async_set_unique_id(selected)
                self._abort_if_unique_id_configured()
                self._location = selected
                return await self.async_step_modules()

        if errors and errors.get("base") != "invalid_selection":
            return self.async_show_form(step_id="user", errors=errors)

        schema = vol.Schema(
            {vol.Required(CONF_LOCATION): vol.In(locations)}
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: Module selection."""
        claimed = _get_claimed_global_modules(self.hass)

        if user_input is not None:
            self._modules = _extract_modules(user_input, claimed)
            return await self._next_conditional_step()

        return self.async_show_form(
            step_id="modules",
            data_schema=_build_module_schema(claimed),
        )

    async def _next_conditional_step(self) -> ConfigFlowResult:
        """Route to the next conditional step based on enabled modules."""
        if self._modules.get(MODULE_WEBCAMS) and "_webcam_locations" not in self._modules:
            return await self.async_step_webcam_locations()
        if self._modules.get(MODULE_MOUNTAIN) and "_mountain_regions" not in self._modules:
            return await self.async_step_mountain_regions()
        if self._modules.get(MODULE_SKI) and "_ski_resorts" not in self._modules:
            return await self.async_step_ski_resorts()
        if self._modules.get(MODULE_AGROMETEO) and "_agro_stations" not in self._modules:
            return await self.async_step_agro_stations()
        if self._modules.get(MODULE_AIR_QUALITY) and "_aq_stations" not in self._modules:
            return await self.async_step_aq_stations()
        if self._modules.get(MODULE_UTCI) and "_utci_stations" not in self._modules:
            return await self.async_step_utci_stations()
        if self._modules.get(MODULE_AVALANCHE) and "_avalanche_regions" not in self._modules:
            return await self.async_step_avalanche_regions()
        return self._create_entry()

    async def async_step_webcam_locations(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3a (conditional): Webcam location selector."""
        if user_input is not None:
            self._modules["_webcam_locations"] = user_input.get(
                CONF_WEBCAM_LOCATIONS, []
            )
            return await self._next_conditional_step()

        # Default: include primary location if it has webcams
        default = []
        if self._location and self._location in WEBCAM_STATIONS:
            default = [self._location]
        station_options = {k: k for k in sorted(WEBCAM_STATIONS.keys())}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_WEBCAM_LOCATIONS, default=default
                ): cv.multi_select(station_options),
            }
        )
        return self.async_show_form(
            step_id="webcam_locations", data_schema=schema
        )

    async def async_step_mountain_regions(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3b (conditional): Mountain region selector."""
        if user_input is not None:
            self._modules["_mountain_regions"] = user_input.get(
                CONF_MOUNTAIN_REGIONS, []
            )
            return await self._next_conditional_step()

        region_options = {v: k for k, v in MOUNTAIN_REGIONS.items()}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MOUNTAIN_REGIONS, default=[]
                ): cv.multi_select(region_options),
            }
        )
        return self.async_show_form(
            step_id="mountain_regions", data_schema=schema
        )

    async def async_step_ski_resorts(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3b (conditional): Ski resort selector."""
        if user_input is not None:
            self._modules["_ski_resorts"] = user_input.get(CONF_SKI_RESORTS, [])
            return await self._next_conditional_step()

        resort_options = {k: k for k in sorted(SKI_RESORTS.keys())}
        schema = vol.Schema(
            {
                vol.Required(CONF_SKI_RESORTS, default=[]): cv.multi_select(
                    resort_options
                ),
            }
        )
        return self.async_show_form(
            step_id="ski_resorts", data_schema=schema
        )

    async def async_step_agro_stations(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3d (conditional): Agrometeo station selector."""
        if user_input is not None:
            self._modules["_agro_stations"] = user_input.get(
                CONF_AGRO_STATIONS, []
            )
            return await self._next_conditional_step()

        station_options = {k: k for k in sorted(AGRO_STATIONS.keys())}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_AGRO_STATIONS, default=[]
                ): cv.multi_select(station_options),
            }
        )
        return self.async_show_form(
            step_id="agro_stations", data_schema=schema
        )

    async def async_step_aq_stations(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3e (conditional): Air quality station selector."""
        if user_input is not None:
            self._modules["_aq_stations"] = user_input.get(
                CONF_AQ_STATIONS, []
            )
            return await self._next_conditional_step()

        station_options = {k: k for k in sorted(AQ_STATIONS.keys())}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_AQ_STATIONS, default=[]
                ): cv.multi_select(station_options),
            }
        )
        return self.async_show_form(
            step_id="aq_stations", data_schema=schema
        )

    async def async_step_utci_stations(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3f (conditional): UTCI station selector."""
        if user_input is not None:
            self._modules["_utci_stations"] = user_input.get(
                CONF_UTCI_STATIONS, []
            )
            return await self._next_conditional_step()

        station_options = {k: k for k in sorted(UTCI_STATIONS.keys())}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UTCI_STATIONS, default=[]
                ): cv.multi_select(station_options),
            }
        )
        return self.async_show_form(
            step_id="utci_stations", data_schema=schema
        )

    async def async_step_avalanche_regions(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3g (conditional): Avalanche region selector."""
        if user_input is not None:
            self._modules["_avalanche_regions"] = user_input.get(
                CONF_AVALANCHE_REGIONS, []
            )
            return await self._next_conditional_step()

        region_options = {k: k for k in sorted(AVALANCHE_REGIONS.keys())}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_AVALANCHE_REGIONS, default=[]
                ): cv.multi_select(region_options),
            }
        )
        return self.async_show_form(
            step_id="avalanche_regions", data_schema=schema
        )

    def _create_entry(self) -> ConfigFlowResult:
        """Create the config entry with collected data."""
        ski_selection = self._modules.pop("_ski_resorts", [])
        mountain_selection = self._modules.pop("_mountain_regions", [])
        webcam_selection = self._modules.pop("_webcam_locations", [])
        agro_selection = self._modules.pop("_agro_stations", [])
        aq_selection = self._modules.pop("_aq_stations", [])
        utci_selection = self._modules.pop("_utci_stations", [])
        avalanche_selection = self._modules.pop("_avalanche_regions", [])
        options: dict[str, Any] = {"modules": self._modules}
        if ski_selection:
            options[CONF_SKI_RESORTS] = ski_selection
        if mountain_selection:
            options[CONF_MOUNTAIN_REGIONS] = mountain_selection
        if webcam_selection:
            options[CONF_WEBCAM_LOCATIONS] = webcam_selection
        if agro_selection:
            options[CONF_AGRO_STATIONS] = agro_selection
        if aq_selection:
            options[CONF_AQ_STATIONS] = aq_selection
        if utci_selection:
            options[CONF_UTCI_STATIONS] = utci_selection
        if avalanche_selection:
            options[CONF_AVALANCHE_REGIONS] = avalanche_selection
        return self.async_create_entry(
            title=self._location,
            data={CONF_LOCATION: self._location},
            options=options,
        )

    async def async_step_import(
        self, import_config: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle import from configuration.yaml."""
        if any(
            entry.data[CONF_LOCATION] == import_config[CONF_LOCATION]
            for entry in self._async_current_entries()
        ):
            return self.async_abort(reason="location_exists")

        return self.async_create_entry(
            title=import_config[CONF_LOCATION], data=import_config
        )


class ArsoOptionsFlow(OptionsFlow):
    """Handle options flow for ARSO Weather — module toggling."""

    def __init__(self) -> None:
        """Initialize."""
        self._modules: dict[str, bool] = {}
        self._webcam_done = False
        self._mountain_done = False
        self._ski_done = False
        self._agro_done = False
        self._aq_done = False
        self._utci_done = False
        self._avalanche_done = False

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the options menu."""
        claimed = _get_claimed_global_modules(
            self.hass, exclude_entry_id=self.config_entry.entry_id
        )

        if user_input is not None:
            self._modules = _extract_modules(user_input, claimed)
            return await self._next_options_step()

        current = get_enabled_modules(self.config_entry)
        return self.async_show_form(
            step_id="init",
            data_schema=_build_module_schema(claimed, defaults=current),
        )

    async def _next_options_step(self) -> ConfigFlowResult:
        """Route to the next conditional options step."""
        if self._modules.get(MODULE_WEBCAMS) and not self._webcam_done:
            return await self.async_step_webcam_locations()
        if self._modules.get(MODULE_MOUNTAIN) and not self._mountain_done:
            return await self.async_step_mountain_regions()
        if self._modules.get(MODULE_SKI) and not self._ski_done:
            return await self.async_step_ski_resorts()
        if self._modules.get(MODULE_AGROMETEO) and not self._agro_done:
            return await self.async_step_agro_stations()
        if self._modules.get(MODULE_AIR_QUALITY) and not self._aq_done:
            return await self.async_step_aq_stations()
        if self._modules.get(MODULE_UTCI) and not self._utci_done:
            return await self.async_step_utci_stations()
        if self._modules.get(MODULE_AVALANCHE) and not self._avalanche_done:
            return await self.async_step_avalanche_regions()
        return self._save_options()

    def _save_options(self) -> ConfigFlowResult:
        """Save collected options."""
        options: dict[str, Any] = {"modules": self._modules}
        if self._modules.get(MODULE_WEBCAMS):
            options[CONF_WEBCAM_LOCATIONS] = self._modules.pop(
                "_webcam_locations",
                self.config_entry.options.get(CONF_WEBCAM_LOCATIONS, []),
            )
        if self._modules.get(MODULE_SKI):
            options[CONF_SKI_RESORTS] = self._modules.pop(
                "_ski_resorts",
                self.config_entry.options.get(CONF_SKI_RESORTS, []),
            )
        if self._modules.get(MODULE_MOUNTAIN):
            options[CONF_MOUNTAIN_REGIONS] = self._modules.pop(
                "_mountain_regions",
                self.config_entry.options.get(CONF_MOUNTAIN_REGIONS, []),
            )
        if self._modules.get(MODULE_AGROMETEO):
            options[CONF_AGRO_STATIONS] = self._modules.pop(
                "_agro_stations",
                self.config_entry.options.get(CONF_AGRO_STATIONS, []),
            )
        if self._modules.get(MODULE_AIR_QUALITY):
            options[CONF_AQ_STATIONS] = self._modules.pop(
                "_aq_stations",
                self.config_entry.options.get(CONF_AQ_STATIONS, []),
            )
        if self._modules.get(MODULE_UTCI):
            options[CONF_UTCI_STATIONS] = self._modules.pop(
                "_utci_stations",
                self.config_entry.options.get(CONF_UTCI_STATIONS, []),
            )
        if self._modules.get(MODULE_AVALANCHE):
            options[CONF_AVALANCHE_REGIONS] = self._modules.pop(
                "_avalanche_regions",
                self.config_entry.options.get(CONF_AVALANCHE_REGIONS, []),
            )
        # Clean internal keys
        self._modules.pop("_webcam_locations", None)
        self._modules.pop("_ski_resorts", None)
        self._modules.pop("_mountain_regions", None)
        self._modules.pop("_agro_stations", None)
        self._modules.pop("_aq_stations", None)
        self._modules.pop("_utci_stations", None)
        self._modules.pop("_avalanche_regions", None)
        return self.async_create_entry(data=options)

    async def async_step_webcam_locations(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Webcam location selector in options flow."""
        if user_input is not None:
            self._modules["_webcam_locations"] = user_input.get(
                CONF_WEBCAM_LOCATIONS, []
            )
            self._webcam_done = True
            return await self._next_options_step()

        current_locations = self.config_entry.options.get(
            CONF_WEBCAM_LOCATIONS, []
        )
        # Default to primary location if no webcam locations set
        if not current_locations:
            primary = self.config_entry.data.get(CONF_LOCATION, "")
            if primary in WEBCAM_STATIONS:
                current_locations = [primary]
        station_options = {k: k for k in sorted(WEBCAM_STATIONS.keys())}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_WEBCAM_LOCATIONS, default=current_locations
                ): cv.multi_select(station_options),
            }
        )
        return self.async_show_form(
            step_id="webcam_locations", data_schema=schema
        )

    async def async_step_mountain_regions(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Mountain region selector in options flow."""
        if user_input is not None:
            self._modules["_mountain_regions"] = user_input.get(
                CONF_MOUNTAIN_REGIONS, []
            )
            self._mountain_done = True
            return await self._next_options_step()

        current_regions = self.config_entry.options.get(
            CONF_MOUNTAIN_REGIONS, []
        )
        region_options = {v: k for k, v in MOUNTAIN_REGIONS.items()}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MOUNTAIN_REGIONS, default=current_regions
                ): cv.multi_select(region_options),
            }
        )
        return self.async_show_form(
            step_id="mountain_regions", data_schema=schema
        )

    async def async_step_ski_resorts(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Resort selector in options flow."""
        if user_input is not None:
            self._modules["_ski_resorts"] = user_input.get(
                CONF_SKI_RESORTS, []
            )
            self._ski_done = True
            return await self._next_options_step()

        current_resorts = self.config_entry.options.get(CONF_SKI_RESORTS, [])
        resort_options = {k: k for k in sorted(SKI_RESORTS.keys())}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SKI_RESORTS, default=current_resorts
                ): cv.multi_select(resort_options),
            }
        )
        return self.async_show_form(
            step_id="ski_resorts", data_schema=schema
        )

    async def async_step_agro_stations(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Agrometeo station selector in options flow."""
        if user_input is not None:
            self._modules["_agro_stations"] = user_input.get(
                CONF_AGRO_STATIONS, []
            )
            self._agro_done = True
            return await self._next_options_step()

        current_stations = self.config_entry.options.get(
            CONF_AGRO_STATIONS, []
        )
        station_options = {k: k for k in sorted(AGRO_STATIONS.keys())}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_AGRO_STATIONS, default=current_stations
                ): cv.multi_select(station_options),
            }
        )
        return self.async_show_form(
            step_id="agro_stations", data_schema=schema
        )

    async def async_step_aq_stations(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Air quality station selector in options flow."""
        if user_input is not None:
            self._modules["_aq_stations"] = user_input.get(
                CONF_AQ_STATIONS, []
            )
            self._aq_done = True
            return await self._next_options_step()

        current_aq = self.config_entry.options.get(CONF_AQ_STATIONS, [])
        aq_options = {k: k for k in sorted(AQ_STATIONS.keys())}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_AQ_STATIONS, default=current_aq
                ): cv.multi_select(aq_options),
            }
        )
        return self.async_show_form(
            step_id="aq_stations", data_schema=schema
        )

    async def async_step_utci_stations(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """UTCI station selector in options flow."""
        if user_input is not None:
            self._modules["_utci_stations"] = user_input.get(
                CONF_UTCI_STATIONS, []
            )
            self._utci_done = True
            return await self._next_options_step()

        current_utci = self.config_entry.options.get(CONF_UTCI_STATIONS, [])
        utci_options = {k: k for k in sorted(UTCI_STATIONS.keys())}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UTCI_STATIONS, default=current_utci
                ): cv.multi_select(utci_options),
            }
        )
        return self.async_show_form(
            step_id="utci_stations", data_schema=schema
        )

    async def async_step_avalanche_regions(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Avalanche region selector in options flow."""
        if user_input is not None:
            self._modules["_avalanche_regions"] = user_input.get(
                CONF_AVALANCHE_REGIONS, []
            )
            self._avalanche_done = True
            return await self._next_options_step()

        current_aval = self.config_entry.options.get(
            CONF_AVALANCHE_REGIONS, []
        )
        region_options = {k: k for k in sorted(AVALANCHE_REGIONS.keys())}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_AVALANCHE_REGIONS, default=current_aval
                ): cv.multi_select(region_options),
            }
        )
        return self.async_show_form(
            step_id="avalanche_regions", data_schema=schema
        )
