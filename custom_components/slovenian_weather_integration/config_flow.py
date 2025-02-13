import logging
import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN, LOCATIONS_URL
import unicodedata

_LOGGER = logging.getLogger(__name__)

async def fetch_locations(hass):
    """Pridobi lokacije iz ARSO."""
    session = async_get_clientsession(hass)
    try:
        async with session.get(LOCATIONS_URL) as response:
            if response.status != 200:
                _LOGGER.error("Neuspešno pridobivanje lokacij: %s", response.status)
                return {}
            data = await response.json()
            return {loc['properties']['title']: loc for loc in data.get("features", [])}
    except aiohttp.ClientError as e:
        _LOGGER.error("Napaka pri pridobivanju lokacij: %s", e)
        return {}

def normalize_location_name(location: str) -> str:
    # Odstrani diakritične znake in pretvori v male črke
    normalized = unicodedata.normalize("NFKD", location).encode("ASCII", "ignore").decode("ASCII")
    return normalized.lower().strip()
    
class ArsoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow za ARSO vremensko integracijo."""
    async def async_step_user(self, user_input=None):
        """Konfiguracija uporabnika."""
        errors = {}
        locations = await fetch_locations(self.hass)
        if user_input is not None:
            return self.async_create_entry(title=user_input["location"], data={"location": user_input["location"]})
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("location"): vol.In(locations.keys())}),
            errors=errors,
        )

# Minimalna implementacija OptionsFlowHandler
class OptionsFlowHandler(config_entries.OptionsFlow):
    """Minimalna implementacija OptionsFlowHandler za ARSO Weather integracijo."""
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Shrani konfiguracijski zapis."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Začetna stopnja možnosti."""
        return self.async_create_entry(title="", data=user_input or {})
