import aiohttp
import voluptuous as vol
import logging
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import callback
from .const import DOMAIN, LOCATIONS_URL
from typing import Any, Dict  # Adjust depending on Python version
from homeassistant.data_entry_flow import FlowResult

_LOGGER = logging.getLogger(__name__)

class ArsoWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for ARSO Weather."""

    async def async_step_user(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Check if the location has already been added
            if any(entry.data["location"] == user_input["location"] for entry in self._async_current_entries()):
                errors["base"] = "location_exists"
            else:
                # Proceed to create an entry if the location is selected
                return self.async_create_entry(title=user_input["location"], data=user_input)

        # Fetch locations from the external JSON
        locations = await self._fetch_locations()

        # Handle error in case no valid locations are returned
        if "Error" in locations[0]:
            errors["base"] = "cannot_fetch_locations"

        # Define the schema for the form
        schema = vol.Schema({
            vol.Required("location"): vol.In(locations)
        })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def _fetch_locations(self):
        """Fetch the list of locations from the external JSON."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(LOCATIONS_URL) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()

                            # Extract 'title' from each element in 'features'
                            locations = [item['properties']['title'] for item in data['features']]
                            return locations if locations else ["No locations found"]
                        except ValueError:
                            return ["Error decoding JSON"]
                    else:
                        return [f"Error: Received status code {response.status}"]
        except aiohttp.ClientError as e:
            _LOGGER.error(f"Error fetching locations: {e}")
            return ["Error: Network issue when fetching locations"]

@callback
def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
    """Get the options flow handler."""
    return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for ARSO Weather."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("location", default=self.config_entry.data.get("location")): str
            }),
        )
