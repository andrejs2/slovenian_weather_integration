import aiohttp
import logging
from homeassistant.helpers.entity import Entity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN
from .helpers import normalize_location
from datetime import datetime
import locale
from homeassistant.helpers import location as loc_helper

_LOGGER = logging.getLogger(__name__)

# URL-ji za ARSO podatke
ARSO_AGRO_FORECAST_URL = "https://meteo.arso.gov.si/uploads/probase/www/agromet/json/sl/forecastKlima_si-agro.json"
ARSO_AGRO_OBSERVATION_URL = "https://meteo.arso.gov.si/uploads/probase/www/agromet/json/sl/observationKlima_si-agro.json"

async def fetch_agro_data(url):
    """Fetch agrometeorological data from ARSO."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to fetch ARSO Agro data from %s: HTTP %s", url, response.status)
                    return None
                return await response.json()
        except Exception as e:
            _LOGGER.error("Exception fetching ARSO Agro data from %s: %s", url, e)
            return None

class ArsoAgroSensor(Entity):
    """Representation of an ARSO Agro sensor."""

    def __init__(self, hass, location, agro_forecast_data, agro_observation_data, device_info):
        """Initialize the Agro sensor."""
        self._hass = hass
        self._location = location
        self._state = "unknown"
        self._attributes = {}
        self._update_agro_data(agro_forecast_data, agro_observation_data)

    async def async_update(self):
        """Fetch latest data."""
        _LOGGER.debug("Updating ARSO Agro data for %s", self._location)
        agro_forecast_data = await fetch_agro_data(ARSO_AGRO_FORECAST_URL)
        agro_observation_data = await fetch_agro_data(ARSO_AGRO_OBSERVATION_URL)
        if agro_forecast_data and agro_observation_data:
            self._update_agro_data(agro_forecast_data, agro_observation_data)

    def _update_agro_data(self, agro_forecast_data, agro_observation_data):
        """Update sensor attributes with the latest agrometeorology data."""
        # Pridobivanje podatkov iz forecast API
        forecast_entry = None
        for location_entry in agro_forecast_data.get("features", []):
            if location_entry["properties"].get("title") == self._location:
                days = location_entry["properties"].get("days", [])
                if days:
                    forecast_entry = days[0]["timeline"][0]
                    break

        # Pridobivanje podatkov iz observation API (včerajšnji podatki)
        observation_entry = None
        for location_entry in agro_observation_data.get("features", []):
            if location_entry["properties"].get("title") == self._location:
                days = location_entry["properties"].get("days", [])
                if days:
                    observation_entry = days[-1]["timeline"][0]  # Zadnji datum (običajno včerajšnji)
                    break

        # Nastavitev podatkov v atribute
        if forecast_entry:
            self._state = forecast_entry.get("sunDur", "unknown")
            self._attributes = {
                "Klimatološka povprečna dnevna temperatura (°C)": forecast_entry.get("tklim", "Ni podatka"),
                "Minimalna temperatura (°C)": forecast_entry.get("tn", "Ni podatka"),
                "Maksimalna temperatura (°C)": forecast_entry.get("tx", "Ni podatka"),
                "Evapotranspiracija (mm)": forecast_entry.get("etp", "Ni podatka"),
                "Temperaturno-vlažnostni indeks": forecast_entry.get("thi", "Ni podatka"),
                "Padavine (mm)": forecast_entry.get("tp_24h_acc", "Ni podatka"),
                "Trajanje sončnega obsevanja (h)": forecast_entry.get("sunDur", "Ni podatka"),
                "Vodna bilanca (mm)": forecast_entry.get("wBal", "Ni podatka"),
                "Datum": days[0].get("date", "Ni podatka"),
            }

        if observation_entry:
            self._attributes.update({
                "Minimalna temperatura 5 cm nad tlemi (°C)": observation_entry.get("tn_5_cm", "Ni podatka"),
                "Temperatura tal 5 cm globine (°C)": observation_entry.get("tg_5_cm", "Ni podatka"),
                "Temperatura tal 10 cm globine (°C)": observation_entry.get("tg_10_cm", "Ni podatka"),
                "Temperatura tal 30 cm globine (°C)": observation_entry.get("tg_30_cm", "Ni podatka"),
            })

        # Dodaj vir podatkov
        self._attributes["attribution"] = "Vir: Agencija RS za okolje"

    @property
    def name(self):
        return f"ARSO Agro {self._location}"

    @property
    def unique_id(self):
        return f"arso_agro_{self._location}"

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    @property
    def unit_of_measurement(self):
        """Vrne enoto merjenja za senzor, npr. '°C' za temperaturo ali 'h' za trajanje sonca."""
        return "h" if self._state != "unknown" else None

    @property
    def state_class(self):
        """Vrne tip stanja senzorja (measurement)."""
        return "measurement" if self._state != "unknown" else None

    @property
    def icon(self):
        return "mdi:weather-sunset"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._location)},
            "name": f"ARSO Weather Station - {self._location.title()}",
            "manufacturer": "ARSO",
            "model": "Vremenski podatki",
            "entry_type": "service",
        }

class ArsoAgroForecastSensor(Entity):
    """Representation of an ARSO Agro Forecast sensor."""

    def __init__(self, hass, location, agro_data, device_info):
        """Initialize the Agro Forecast sensor."""
        self._hass = hass
        self._location = location
        self._state = "unknown"
        self._attributes = {}
        self._update_forecast(agro_data)

    async def async_update(self):
        """Fetch latest agro data."""
        _LOGGER.debug("Updating ARSO Agro data for %s", self._location)
        agro_forecast_data = await fetch_agro_data(ARSO_AGRO_FORECAST_URL) 
        agro_observation_data = await fetch_agro_data(ARSO_AGRO_OBSERVATION_URL)
        if agro_forecast_data and agro_observation_data:
            self._update_forecast(agro_forecast_data)

    def _update_forecast(self, agro_data):
        """Update forecast attributes with the latest agrometeorology forecast data."""
        lang = self._hass.config.language
        _LOGGER.debug(f"Using language: {lang}")

        # Poskusi nastaviti lokalizacijo na slovenščino, če ni možno, izpiši opozorilo
        try:
            locale.setlocale(locale.LC_TIME, 'sl_SI.UTF-8')
        except locale.Error:
            _LOGGER.warning("Lokalizacija 'sl_SI.UTF-8' ni podprta na tem sistemu. Datum ne bo lokaliziran.")

        for location_entry in agro_data.get("features", []):
            if location_entry["properties"].get("title") == self._location:
                days = location_entry["properties"].get("days", [])
                forecast_list = []
                for day in days:
                    timeline = day.get("timeline", [])
                    if timeline:
                        entry = timeline[0]
                        date_str = day.get("date", "Ni podatkov")
                        if date_str != "Ni podatkov":
                            try:
                                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                                formatted_date = date_obj.strftime("%d.%m.%Y")  
                            except ValueError:
                                formatted_date = date_str 
                        else:
                            formatted_date = date_str
                        
                        forecast_list.append({
                            "Datum": formatted_date,
                            "Klimatološka povprečna dnevna temperatura (°C)": entry.get("tklim", "Ni podatka"),
                            "Minimalna temperatura (°C)": entry.get("tn", "Ni podatka"),
                            "Maksimalna temperatura (°C)": entry.get("tx", "Ni podatka"),
                            "Evapotranspiracija (mm)": entry.get("etp", "Ni podatka"),
                            "Temperaturno-vlažnostni indeks": entry.get("thi", "Ni podatka"),
                            "Padavine (mm)": entry.get("tp_24h_acc", "Ni podatka"),
                            "Trajanje sončnega obsevanja (h)": entry.get("sunDur", "Ni podatka"),
                            "Vodna bilanca (mm)": entry.get("wBal", "Ni podatka")
                        })

                if forecast_list:
                    self._state = "Napoved na voljo"
                    self._attributes = {
                        "Napoved": forecast_list,
                        "attribution": "Vir: Agencija RS za okolje"
                    }

    @property
    def name(self):
        return f"ARSO Agro Forecast {self._location}"

    @property
    def unique_id(self):
        return f"arso_agro_forecast_{self._location}"

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    @property
    def icon(self):
        return "mdi:tractor"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._location)},
            "name": f"ARSO vremenska postaja - {self._location.title()}",
            "manufacturer": "ARSO",
            "model": "Vremenski podatki",
            "entry_type": "service",
        }
