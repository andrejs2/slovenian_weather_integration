from __future__ import annotations

import logging
from typing import Any, Dict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.const import CONF_LOCATION
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_ENABLE_MOUNTAIN,
    CONF_MOUNTAIN_REGION,
    DEFAULT_MOUNTAIN_REGION,
)
from .arso_weather.client import ArsoWeather

_LOGGER = logging.getLogger(__name__)


class ArsoWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for ARSO Weather."""

    VERSION = 1

    def __init__(self) -> None:
        self._init_data: dict[str, Any] = {}

    async def async_step_user(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Step 1: select location."""
        errors: Dict[str, str] = {}

        session = async_get_clientsession(self.hass)
        client = ArsoWeather(location_name="Ljubljana", session=session)

        locations: list[str] = []
        try:
            locations_raw = await client.get_all_locations()
            if isinstance(locations_raw, list) and all(isinstance(loc, str) for loc in locations_raw):
                locations = sorted(locations_raw)
            else:
                _LOGGER.error("Fetched locations are not a list of strings: %s", locations_raw)
                errors["base"] = "invalid_location_data"
            if not locations and "base" not in errors:
                _LOGGER.error("Fetched locations list is empty.")
                errors["base"] = "no_locations_found"
        except Exception as exc:
            _LOGGER.exception("Error fetching locations: %s", exc)
            errors["base"] = "cannot_connect"

        if user_input is not None:
            if not errors:
                selected_location = user_input[CONF_LOCATION]
                if selected_location not in locations:
                    errors["base"] = "invalid_selection"
                else:
                    # store and go to options step
                    self._init_data = user_input
                    return await self.async_step_options()

        if errors and errors.get("base") != "invalid_selection":
            return self.async_show_form(step_id="user", errors=errors)

        schema = vol.Schema({vol.Required(CONF_LOCATION): vol.In(locations)})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_options(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Step 2: initial options (platforms + mountain)."""
        defaults = {
            "platforms": ["weather", "sensor"],
            CONF_ENABLE_MOUNTAIN: False,
            CONF_MOUNTAIN_REGION: DEFAULT_MOUNTAIN_REGION,
        }

        if user_input is not None:
            # create entry with both data and options
            location = self._init_data.get(CONF_LOCATION, "ARSO")
            return self.async_create_entry(
                title=location,
                data=self._init_data,
                options=user_input,
            )

        schema = vol.Schema({
            vol.Optional("platforms", default=defaults["platforms"]):
                cv.multi_select({"weather": "Weather", "sensor": "Sensor"}),
            vol.Optional(CONF_ENABLE_MOUNTAIN, default=defaults[CONF_ENABLE_MOUNTAIN]): bool,
            vol.Optional(CONF_MOUNTAIN_REGION, default=defaults[CONF_MOUNTAIN_REGION]): str,
        })
        return self.async_show_form(step_id="options", data_schema=schema)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow for ARSO Weather."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry
        _LOGGER.debug("OptionsFlowHandler __init__ for entry %s", config_entry.entry_id)

    async def async_step_init(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        options = dict(self.config_entry.options)

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema({
            vol.Optional(
                "platforms",
                default=options.get("platforms", ["weather", "sensor"])
            ): cv.multi_select({"weather": "Weather", "sensor": "Sensor"}),
            vol.Optional(
                CONF_ENABLE_MOUNTAIN,
                default=options.get(CONF_ENABLE_MOUNTAIN, False)
            ): bool,
            vol.Optional(
                CONF_MOUNTAIN_REGION,
                default=options.get(CONF_MOUNTAIN_REGION, DEFAULT_MOUNTAIN_REGION)
            ): str,
        })
        return self.async_show_form(step_id="init", data_schema=schema)
