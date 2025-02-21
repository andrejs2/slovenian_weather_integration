import logging
import aiohttp
import pandas as pd
from io import StringIO
from homeassistant.helpers.entity import Entity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
#from homeassistant.const import TEMP_CELSIUS
from datetime import datetime, timezone
from homeassistant.const import UnitOfTemperature
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

async def fetch_utci_forecast_data(hass: HomeAssistant, location: str) -> dict:
    """Fetch UTCI forecast data as a dict mapping rounded validTime (ISO format) to UTCI value."""
    if location not in UTCI_LOCATIONS:
        _LOGGER.warning("🌥️ No UTCI data available for location: %s", location)
        return {}
    
    location_param = UTCI_LOCATIONS[location]
    utci_url = f"https://meteo.arso.gov.si/uploads/probase/www/sproduct/biomet/table/sl/UTCI_timeseries_{location_param}.csv"
    _LOGGER.info("🌡️ Fetching UTCI forecast data for %s from %s", location, utci_url)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(utci_url) as response:
                if response.status != 200:
                    _LOGGER.warning("🌥️ Failed to fetch UTCI forecast data. HTTP status: %s", response.status)
                    return {}
                csv_data = await response.text()

        def parse_csv():
            df = pd.read_csv(StringIO(csv_data))
            df['validTime'] = pd.to_datetime(df['validTime'], utc=True)
            df = df.dropna(subset=['UTCI'])
            forecast = {}
            for _, row in df.iterrows():
                # Zaokrožimo čas na celo uro
                rounded_time = row['validTime'].replace(minute=0, second=0, microsecond=0)
                # Shrani vrednost (zaokroženo na 1 decimalno mesto)
                forecast[rounded_time.isoformat()] = round(row['UTCI'], 1)
            return forecast

        utci_forecast = await hass.async_add_executor_job(parse_csv)
        return utci_forecast
        
    except Exception as e:
        _LOGGER.error("Error fetching UTCI forecast data: %s", e, exc_info=True)
        return {}

async def fetch_utci_data(hass: HomeAssistant, location: str):
    """Fetch current apparent temperature (UTCI) for the given location."""
    if location not in UTCI_LOCATIONS:
        _LOGGER.warning("No UTCI data available for location: %s", location)
        return None
    location_param = UTCI_LOCATIONS[location]
    utci_url = f"https://meteo.arso.gov.si/uploads/probase/www/sproduct/biomet/table/sl/UTCI_timeseries_{location_param}.csv"
    _LOGGER.info("Fetching current UTCI data for %s from %s", location, utci_url)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(utci_url) as response:
                if response.status != 200:
                    _LOGGER.warning("Failed to fetch UTCI data. HTTP status: %s", response.status)
                    return None
                csv_data = await response.text()

        def parse_csv():
            df = pd.read_csv(StringIO(csv_data))
            df['validTime'] = pd.to_datetime(df['validTime'], utc=True)
            now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
            # Poiščemo točno vrednost za trenutni čas
            current_row = df.loc[df['validTime'] == now]
            if current_row.empty:
                _LOGGER.warning("No UTCI data for current hour (%s). Using most recent available data.", now)
                current_row = df.dropna(subset=['UTCI'])
                if current_row.empty:
                    return None
                # Uporabimo zadnjo razpoložljivo vrednost
                return round(current_row.iloc[-1]['UTCI'], 1)
            return round(current_row.iloc[-1]['UTCI'], 1)

        utci_value = await hass.async_add_executor_job(parse_csv)
        return utci_value

    except Exception as e:
        _LOGGER.error("Error fetching current UTCI data: %s", e, exc_info=True)
        return None

class UTCISensor(Entity):
    """Sensor for apparent temperature (UTCI)."""
    def __init__(self, hass: HomeAssistant, location: str):
        self._hass = hass
        self._location = location
        self._state = None
        self._attr_name = f"ARSO Weather {self._location.capitalize()} - Apparent Temperature"
        self._attr_unit_of_measurement = TEMP_CELSIUS
        self._attr_icon = "mdi:thermometer"
        # Če potrebuješ device_class ali state_class, jih ustrezno uvozi in nastavi:
        # self._attr_device_class = DEVICE_CLASS_TEMPERATURE
        # self._attr_state_class = STATE_CLASS_MEASUREMENT

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
            "name": f"ARSO vremenska postaja - {self._location.title()}",
            "manufacturer": "ARSO",
            "model": "Vremenski podatki",
            "entry_type": "service",
        }

    async def async_update(self):
        """Update the sensor state."""
        self._state = await fetch_utci_data(self._hass, self._location)
        if self._state is None:
            _LOGGER.warning("No UTCI data available for %s. Keeping previous state.", self._location)
        else:
            _LOGGER.debug("Final UTCI value for %s: %s", self._location, self._state)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the UTCI sensor in Home Assistant."""
    location = config_entry.data.get("location")
    if location in UTCI_LOCATIONS:
        sensor = UTCISensor(hass, location)
        async_add_entities([sensor], True)
