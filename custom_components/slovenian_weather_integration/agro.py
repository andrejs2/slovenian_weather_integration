import aiohttp
import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN, LOCATIONS_URL
from .helpers import normalize_location

_LOGGER = logging.getLogger(__name__)

ARSO_AGRO_URL = "https://meteo.arso.gov.si/uploads/probase/www/agromet/json/sl/forecastKlima_si-agro.json"

# Preslikava merilnih postaj na Home Assistant lokacije
AGRO_STATION_MAPPING = {
    "Ljubljana": "Ljubljana",
    "Celje": "Celje",
    "Bilje pri Novi Gorici": "Bilje pri Novi Gorici",
    "Bovec": "Bovec",
    "Novo mesto": "Novo mesto",
    "Murska Sobota": "Murska Sobota",
    "Črnomelj": "Črnomelj",
    "Kočevje": "Kočevje",
    "Letališče Cerklje ob Krki": "Letališče Cerklje ob Krki",
    "Letališče Edvarda Rusjana Maribor": "Letališče Edvarda Rusjana Maribor",
    "Letališče Jožeta Pučnika Ljubljana": "Letališče Jožeta Pučnika Ljubljana",
    "Letališče Portorož": "Letališče Portorož",
    "Postojna": "Postojna",
    "Rateče": "Rateče",
    "Šmartno pri Slovenj Gradcu": "Šmartno pri Slovenj Gradcu",
}

async def fetch_agro_data():
    """Fetch agrometeorological data from ARSO."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(ARSO_AGRO_URL) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to fetch ARSO Agro data: HTTP %s", response.status)
                    return None
                return await response.json()
        except Exception as e:
            _LOGGER.error("Exception fetching ARSO Agro data: %s", e)
            return None

async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up ARSO agrometeorological sensors."""
    location = config_entry.data.get("location")
    if not location:
        _LOGGER.error("No location specified in the config entry!")
        return

    location_normalized = normalize_location(location)
    agro_data = await fetch_agro_data()
    if agro_data and location_normalized in AGRO_STATION_MAPPING:
        async_add_entities([ArsoAgroSensor(hass, location_normalized, agro_data)], True)

class ArsoAgroSensor(Entity):
    """Representation of an ARSO Agrometeorology sensor with forecast.

    Sedaj bo senzor v state imel trenutno (prvi dan) trajanje sončne svetlobe,
    dodatni atribut 'forecast' pa bo vseboval seznam napovednih podatkov za vse dneve.
    """

    def __init__(self, hass, location, agro_data):
        """Initialize the sensor."""
        self._hass = hass
        self._location = normalize_location(location)
        self._state = None
        self._attributes = {}
        self.update_agro_data(agro_data)

    def update_agro_data(self, agro_data):
        """Update sensor attributes with the latest agrometeorology data including forecast."""
        for location_entry in agro_data.get("features", []):
            location_title = normalize_location(location_entry["properties"].get("title", ""))
            if location_title == self._location:
                days = location_entry["properties"].get("days", [])
                if not days:
                    _LOGGER.warning("Ni dnevnih podatkov za lokacijo %s", self._location)
                    continue

                forecast = []
                for day in days:
                    timeline = day.get("timeline", [])
                    if timeline:
                        entry = timeline[0]  # Uporabimo prvi zapis iz timeline za dan
                        forecast.append({
                            "Evapotranspiration (mm)": entry.get("etp", "No Data"),
                            "Avg Temperature (°C)": entry.get("tklim", "No Data"),
                            "Min Temperature (°C)": entry.get("tn", "No Data"),
                            "Max Temperature (°C)": entry.get("tx", "No Data"),
                            "Sun Duration (h)": entry.get("sunDur", "No Data"),
                            "Temperature Humidity Index": entry.get("thi", "No Data"),
                            "Precipitation (mm)": entry.get("tp_24h_acc", "No Data"),
                            "Water Balance (mm)": entry.get("wBal", "No Data"),
                            "Date": day.get("date", "No Data")
                        })
                if forecast:
                    # State bo trenutni dan (prvi element); celotna napoved v atributu 'forecast'
                    self._state = forecast[0].get("Sun Duration (h)", "No Data")
                    self._attributes = {
                        "forecast": forecast,
                        "Source": "Agencija RS za okolje"
                    }
                    _LOGGER.info("Agro senzor za %s posodobljen z napovedjo: %s", self._location, forecast)
                break

    async def async_update(self):
        """Fetch the latest agrometeorology data."""
        agro_data = await fetch_agro_data()
        if agro_data:
            self.update_agro_data(agro_data)

    @property
    def unique_id(self):
        """Return the unique ID for this sensor."""
        return f"arso_weather_{self._location}_agro"

    @property
    def name(self):
        """Return the name of the sensor."""
        # Dodamo 'Forecast' v ime, da je razvidno, da gre za napoved.
        return f"ARSO Weather {self._location.capitalize()} - Agro Forecast"

    @property
    def state(self):
        """Return the current state (current day's Sun Duration)."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return additional attributes including forecast data for all days."""
        return self._attributes

    @property
    def icon(self):
        """Return the icon for the sensor."""
        return "mdi:weather-sunny"
