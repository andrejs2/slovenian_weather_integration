import aiohttp
import voluptuous as vol
import logging
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import callback
from homeassistant.const import CONF_LOCATION
from .const import DOMAIN, LOCATIONS_URL
from typing import Any, Dict 
from homeassistant.data_entry_flow import FlowResult
from .helpers import async_remove_sensors

from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class ArsoWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for ARSO Weather."""

    VERSION = 1

    async def async_step_user(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            _LOGGER.debug("User input received: %s", user_input)

            # Check for duplicate locations
            if any(entry.data[CONF_LOCATION] == user_input[CONF_LOCATION] for entry in self._async_current_entries()):
                errors["base"] = "location_exists"
                _LOGGER.warning("Location %s already exists", user_input[CONF_LOCATION])
            else:
                _LOGGER.debug("Creating new entry for location: %s", user_input[CONF_LOCATION])
                return self.async_create_entry(title=user_input[CONF_LOCATION], data=user_input)

        # Fetch locations and validate
        locations = await self._fetch_locations()
        if not locations or "Error" in locations[0]:
            errors["base"] = "cannot_fetch_locations"
            _LOGGER.error("Failed to fetch locations: %s", locations)
            locations = ["Error: No locations found"]

        schema = vol.Schema({
            vol.Required(CONF_LOCATION): vol.In(locations)
        })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


    async def async_step_import(self, import_config: Dict[str, Any]) -> FlowResult:
        """Handle import from configuration.yaml."""
        _LOGGER.debug("Importing config: %s", import_config)

        if any(entry.data[CONF_LOCATION] == import_config[CONF_LOCATION] for entry in self._async_current_entries()):
            _LOGGER.warning("Location %s already exists, skipping import", import_config[CONF_LOCATION])
            return self.async_abort(reason="location_exists")

        return self.async_create_entry(title=import_config[CONF_LOCATION], data=import_config)

    async def _fetch_locations(self):
        """Fetch the list of locations from the external JSON."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(LOCATIONS_URL) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            locations = [item['properties']['title'] for item in data['features']]
                            if not locations:
                                _LOGGER.warning("No locations found in API response")
                                return ["No locations found"]
                            return locations
                        except ValueError as e:
                            _LOGGER.error("Error decoding JSON from API: %s", e)
                            return ["Error decoding JSON"]
                    else:
                        _LOGGER.error("API returned status code %s", response.status)
                        return [f"Error: Received status code {response.status}"]
        except aiohttp.ClientError as e:
            _LOGGER.error("Error fetching locations: %s", e)
            return ["Error: Network issue when fetching locations"]

@callback
def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
    """Get the options flow handler."""
    return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle the options flow for ARSO Weather."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle the options menu."""
        _LOGGER.debug("Options flow initialized with options: %s", self.config_entry.options)

        if user_input is not None:
            _LOGGER.debug("User input received: %s", user_input)

            platforms = []
            if user_input.get("enable_weather"):
                platforms.append("weather")
            if user_input.get("enable_sensor"):
                platforms.append("sensor")

            self.hass.config_entries.async_update_entry(
                self.config_entry, options={"platforms": platforms}
            )
            _LOGGER.debug("Updated platforms: %s", platforms)

            return self.async_create_entry(title="", data={})

        current_options = self.config_entry.options.get("platforms", ["weather", "sensor"])
        _LOGGER.debug("Current options: %s", current_options)

        schema = vol.Schema({
            vol.Optional("enable_weather", default="weather" in current_options): bool,
            vol.Optional("enable_sensor", default="sensor" in current_options): bool,
        })

        _LOGGER.debug("Generated options schema: %s", schema)

        return self.async_show_form(
            step_id="init",
            data_schema=schema
        )
