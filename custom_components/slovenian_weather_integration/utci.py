import logging
import aiohttp
import pandas as pd
from io import StringIO
from homeassistant.helpers.entity import Entity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN
from datetime import datetime, timezone

_LOGGER = logging.getLogger(__name__)

# Preslikava lokacij za pravilno izbiro UTCI CSV

UTCI_LOCATIONS = {
    "Bilje pri Novi Gorici": "BILJE",
    "Bovec": "BOVEC%20-%20LETALISCE",
    "Celje": "CELJE%20-%20MEDLOG",
    "Letališče Cerklje ob Krki": "CERKLJE%20-%20LETALISCE",
    "Črnomelj": "CRNOMELJ%20-%20DOBLICE",
    "Kočevje": "KOCEVJE",
    "Kranj": "KRANJ",
    "Letališče Edvarda Rusjana Maribor": "LETALISCE%20EDVARDA%20RUSJANA%20MARIBOR",
    "Ljubljana": "LJUBLJANA%20-%20BEZIGRAD",
    "Murska Sobota": "MURSKA%20SOBOTA%20-%20RAKICAN",
    "Novo mesto": "NOVO%20MESTO",
    "Letališče Portorož": "PORTOROZ%20-%20LETALISCE",
    "Postojna": "POSTOJNA%20(bober)",
    "Rateče": "RATECE",
    "Šmartno pri Slovenj Gradcu": "SMARTNO%20PRI%20SLOVENJ%20GRADCU",
}
ARSO_UTCI_URL = "https://meteo.arso.gov.si/uploads/probase/www/sproduct/biomet/table/sl/UTCI_timeseries_LJUBLJANA%20-%20BEZIGRAD.csv"

async def fetch_utci_data(hass: HomeAssistant, location: str):
    """Fetch UTCI (Apparent Temperature) data from ARSO."""
    if location not in UTCI_LOCATIONS:
        _LOGGER.warning("🌥️ No UTCI data available for location: %s", location)
        return None
    
    location_param = UTCI_LOCATIONS[location]
    utci_url = f"https://meteo.arso.gov.si/uploads/probase/www/sproduct/biomet/table/sl/UTCI_timeseries_{location_param}.csv"

    _LOGGER.info("🌡️ Fetching UTCI data for %s from %s", location, utci_url)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(utci_url) as response:
                if response.status != 200:
                    _LOGGER.warning("🌥️ Failed to fetch UTCI data. HTTP status: %s", response.status)
                    return None
                csv_data = await response.text()

        def parse_csv():
            df = pd.read_csv(StringIO(csv_data))
            df['validTime'] = pd.to_datetime(df['validTime'], utc=True)

            now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
            latest_utci = df.loc[df['validTime'] == now, 'UTCI'].values

            # Fallback: If no data for the current hour, use the most recent available UTCI
            if latest_utci.size == 0:
                _LOGGER.warning("🚨 No UTCI data for current hour (%s). Using most recent available data.", now)
                latest_utci = df.loc[df['UTCI'].notna(), 'UTCI'].values
                if latest_utci.size == 0:
                    _LOGGER.error("❌ No UTCI data available at all for location: %s", location)
                    return None
            
            return latest_utci[-1] 

        utci_value = await hass.async_add_executor_job(parse_csv)
        
        if utci_value is not None:
            utci_value = round(utci_value, 1) # zaokroži na decimalno mesto

        _LOGGER.info("UTCI for current hour (rounded): %s", utci_value)
        return utci_value
        
    except Exception as e:
        _LOGGER.error("Error fetching UTCI data: %s", e, exc_info=True)
        return None

class UTCISensor(Entity):
    """Senzor za apparent temperature (UTCI)."""
    
    def __init__(self, hass, location):
        self._hass = hass
        self._location = location
        self._state = None
        self._attr_name = f"ARSO Weather {self._location.capitalize()} - Apparent Temperature"
        self._attr_unit_of_measurement = TEMP_CELSIUS
        self._attr_icon = "mdi:thermometer"
        self._attr_device_class = DEVICE_CLASS_TEMPERATURE
        self._attr_state_class = STATE_CLASS_MEASUREMENT
        self._attr_extra_state_attributes = {}
        self._hourly_utci_forecast = {}

    @property
    def name(self):
        return self._attr_name

    @property
    def state(self):
        return self._state

    @property
    def unit_of_measurement(self):
        return self._attr_unit_of_measurement

    @property
    def icon(self):
        return self._attr_icon

    @property
    def device_class(self):
        return self._attr_device_class

    @property
    def state_class(self):
        return self._attr_state_class

    @property
    def unique_id(self):
        return f"arso_weather_{self._location.replace(' ', '_').lower()}_apparent_temperature"

    @property
    def extra_state_attributes(self):
        """Vrne dodatne atribute."""
        return self._attr_extra_state_attributes

    @property
    def device_info(self):
        """Dodajanje senzorja v ARSO Weather entiteto."""
        return {
            "identifiers": {(DOMAIN, self._location)},
            "name": f"ARSO Weather Station - {self._location.title()}",
            "manufacturer": "ARSO",
            "model": "Weather Sensors",
            "entry_type": "service",
        }

    async def async_update(self):
        """Posodobitev podatkov senzorja."""
        self._state = await fetch_utci_data(self._hass)
        if self._state is None:
            _LOGGER.warning("No UTCI data available. Keeping previous state.")

class UTCISensor(Entity):
    """Senzor za apparent temperature (UTCI)."""
    def __init__(self, hass, location):
        self._hass = hass
        self._location = location
        self._state = None
        self._attr_name = f"ARSO Weather {self._location.capitalize()} - Apparent Temperature"
        self._attr_unit_of_measurement = "°C"
        self._attr_icon = "mdi:thermometer"

    @property
    def name(self):
        return self._attr_name

    @property
    def state(self):
        return self._state

    @property
    def unit_of_measurement(self):
        return self._attr_unit_of_measurement

    @property
    def icon(self):
        return self._attr_icon

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._location)},
            "name": f"ARSO Weather Station - {self._location.title()}",
            "manufacturer": "ARSO",
            "model": "Weather Sensors",
            "entry_type": "service",
        }

    async def async_update(self):
        """Posodobitev podatkov senzorja."""
        self._state = await fetch_utci_data(self._hass, self._location)
        if self._state is None:
            _LOGGER.warning("No UTCI data available. Keeping previous state.")
            _LOGGER.debug("Final UTCI value for %s: %s", location, result)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Registracija UTCI senzorja v Home Assistant."""
    location = config_entry.data.get("location")
    if location in UTCI_LOCATIONS:
        sensor = UTCISensor(hass, location)
        async_add_entities([sensor], True)
