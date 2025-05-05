import voluptuous as vol
import logging
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import callback
from homeassistant.const import CONF_LOCATION
from .const import DOMAIN
from typing import Any, Dict
from homeassistant.data_entry_flow import FlowResult

from homeassistant import config_entries
from .arso_weather import ArsoWeather
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


class ArsoWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for ARSO Weather."""

    VERSION = 1

    async def async_step_user(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}

        # Get the HA-managed session
        session = async_get_clientsession(self.hass)

        client = ArsoWeather(
            location_name="Ljubljana",  # just use a default for the initial call to get locations.
            session=session,
        )

        locations = []
        try:
            # Fetch locations using the client with the HA session
            locations_raw = await client.get_all_locations()
            # Basic validation on fetched data
            if isinstance(locations_raw, list) and all(
                isinstance(loc, str) for loc in locations_raw
            ):
                locations = sorted(locations_raw)  # Sort for better UI
            else:
                _LOGGER.error(
                    "Fetched locations data is not a list of strings: %s", locations_raw
                )
                errors["base"] = "invalid_location_data"

            if not locations and "base" not in errors:  # Check if list is empty
                _LOGGER.error("Fetched locations list is empty.")
                errors["base"] = "no_locations_found"

        except Exception as exc:
            _LOGGER.exception("Error fetching locations: %s", exc)
            errors["base"] = "cannot_connect"

        # --- handle user input or show form ---
        if user_input is not None:
            # Input received, proceed to create entry if no errors during fetch
            if not errors:
                # Check if selected location is valid (it should be if vol.In)
                selected_location = user_input[CONF_LOCATION]
                if selected_location not in locations:
                    # This shouldn't happen if vol.In is working correctly
                    errors["base"] = "invalid_selection"
                    _LOGGER.error(
                        "Selected location '%s' not in fetched list.", selected_location
                    )
                else:
                    _LOGGER.debug("Creating entry for location: %s", selected_location)
                    return self.async_create_entry(
                        title=selected_location, data=user_input
                    )

        # If there were errors during fetch, prevent showing the form with bad data
        if errors and errors.get("base") != "invalid_selection":
            return self.async_show_form(step_id="user", errors=errors)

        # Define schema using fetched locations (only if no fetch errors)
        schema = vol.Schema({vol.Required(CONF_LOCATION): vol.In(locations)})

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_import(self, import_config: Dict[str, Any]) -> FlowResult:
        """Handle import from configuration.yaml."""
        _LOGGER.debug("Importing config: %s", import_config)

        if any(
            entry.data[CONF_LOCATION] == import_config[CONF_LOCATION]
            for entry in self._async_current_entries()
        ):
            _LOGGER.warning(
                "Location %s already exists, skipping import",
                import_config[CONF_LOCATION],
            )
            return self.async_abort(reason="location_exists")

        return self.async_create_entry(
            title=import_config[CONF_LOCATION], data=import_config
        )


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
        _LOGGER.debug(
            "Options flow initialized with options: %s", self.config_entry.options
        )

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

        current_options = self.config_entry.options.get(
            "platforms", ["weather", "sensor"]
        )
        _LOGGER.debug("Current options: %s", current_options)

        schema = vol.Schema(
            {
                vol.Optional(
                    "enable_weather", default="weather" in current_options
                ): bool,
                vol.Optional(
                    "enable_sensor", default="sensor" in current_options
                ): bool,
            }
        )

        _LOGGER.debug("Generated options schema: %s", schema)

        return self.async_show_form(step_id="init", data_schema=schema)
