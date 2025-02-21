"""
ARSO Weather senzorji – sensor.py

Ta modul definira ARSO Weather senzorje, ki pridobivajo podatke neposredno
iz ARSO API-ja za večino senzorjev. Za senzorje tipa "dew_point" (temperatura rosišča)
in "visibility" (vidnost) se podatki pridobivajo iz RSS feeda.
Poleg teh vremenskih senzorjev se preko te platforme dodaja tudi senzor
kakovosti zraka (Air Quality), ki ga implementira modul air.py.
"""

import logging
from urllib.parse import quote
from asyncio import sleep
import aiohttp
import re
from homeassistant.helpers.entity import Entity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .air import ArsoAirQualitySensor
from .const import DOMAIN, API_URL
from .helpers import async_remove_sensors, normalize_location
from .pollen import fetch_pollen_data, fetch_pollen_forecast
from .agro import fetch_agro_data, ArsoAgroSensor, ArsoAgroForecastSensor
from .agro import ARSO_AGRO_FORECAST_URL, ARSO_AGRO_OBSERVATION_URL


_LOGGER = logging.getLogger(__name__)

# Definicije vremenskih senzorjev: za vsak tip definiramo [ime, enota, ikona, device_class]
SENSOR_TYPES = {
    "temperature": ["Temperature", "°C", "mdi:thermometer", "temperature"],
    "humidity": ["Humidity", "%", "mdi:water-percent", "humidity"],
    "pressure": ["Pressure", "hPa", "mdi:gauge", "pressure"],
    "wind_speed": ["Wind Speed", "km/h", "mdi:weather-windy", None],
    "wind_bearing": ["Wind Bearing", None, "mdi:compass", None],
    "wind_gust_speed": ["Wind Gust Speed", "km/h", "mdi:weather-windy-variant", None],
    "condition": ["Condition", None, "mdi:weather-cloudy", None],
    "weather_phenomenon": ["Weather Phenomenon", None, "mdi:weather-partly-rainy", None],
    "snowfall": ["Snowfall", "mm", "mdi:snowflake", None],  # Novo zapadli sneg
    "precipitation": ["Rainfall", "mm", "mdi:weather-rainy", None],
    "cloud_base": ["Cloud base height", None, "mdi:cloud-outline", None],
    "pressure_tendency": ["Pressure Tendency", None, "mdi:gauge", None],
    "cloud_coverage": ["Cloud Coverage", "%", "mdi:cloud", None],
    "dew_point": ["Dew Point", "°C", "mdi:thermometer", None],
    "visibility": ["Visibility", "km", "mdi:eye", None],
    "sun_radiation": ["Solar Radiation", "W/m2", "mdi:solar-power", "illuminance"],
    "snow_cover_thickness": ["Snow Cover Thickness", "cm", "mdi:snowflake", None],  # Debelina snežne odeje
}

WIND_DIRECTION_MAP = {
    "S": "S",
    "J": "S",
    "SZ": "NW",
    "SV": "NE",
    "Z": "W",
    "V": "E",
    "JZ": "SW",
    "JV": "SE",
    "N": "N"
}

# Pretvorba besedilne ocene oblaka v odstotke
CLOUD_COVERAGE_MAP = {
    "jasno": 0,
    "pretežno jasno": 12.5,
    "delno jasno": 25,
    "delno oblačno": 50,
    "zmerno oblačno": 62.5,
    "pretežno oblačno": 87.5,
    "oblačno": 100,
}

# Preslikava besedilnih opisov v človeško berljive vrednosti za stanje "condition"
CLOUD_CONDITION_MAP = {
    # Osnovna stanja (API vrne že v slovenščini, vendar jih želimo predstaviti v bolj človeško berljivi obliki)
    "jasno": "Jasno",
    "delno oblačno": "Delno oblačno",
    "pretežno oblačno": "Pretežno oblačno",
    "oblačno": "Oblačno",
    "megla": "Megla",
    "dežuje": "Dežuje",
    "možnost neviht": "Možnost neviht",
    "dež": "Dež",
    "plohe": "Plohe padavine",
    "sneži": "Sneži",
    "toča": "Toča",
    "sneg z dežjem": "Sneg z dežjem",
    "vetrovno": "Vetrovno",
    "veter z oblaki": "Veter z oblaki",

    # Stanja s podrobnejšo opisnostjo – vrnjeno iz "clouds_icon_wwsyn_icon"
    "overcast_heavytsra_day": "Oblačno z močnejšo nevihto in padavinami",
    "overcast_heavytsra_night": "Oblačno z močnejšo nevihto in padavinami",
    "overcast_heavyra_day": "Močno deževno",
    "overcast_heavyra_night": "Močno deževno",
    "overcast_modtsra_day": "Oblačno z zmernimi padavinami in nevihto",
    "overcast_modtsra_night": "Oblačno z zmernimi padavinami in nevihto",
    "overcast_modra_day": "Oblačno z dežjem",
    "overcast_modra_night": "Oblačno z dežjem",
    "overcast_lightra_day": "Oblačno z rahlim dežjem",
    "overcast_lightra_night": "Oblačno z rahlim dežjem",
    "overcast_lighttsra_day": "Oblačno z rahlim dežjem in sunki vetra",
    "overcast_lighttsra_night": "Oblačno z rahlim dežjem in sunki vetra",
    "overcast_day": "Oblačno",
    "overcast_night": "Oblačno",
    "overcast_lightfg_night": "Oblačno",
    "overcast_lightfg_day": "Oblačno",
    "overcast_lightra_day": "Oblačno z rahlim dežjem",
    "overcast_lightra_night": "Oblačno z rahlim dežjem",
    "overcast_modrasn_day": "Oblačno s sneženjem in dežjem",
    "overcast_modrasn_night": "Oblačno s sneženjem in dežjem",
    "overcast_lightrasn_day": "Oblačno s sneženjem",
    "overcast_lightrasn_night": "Oblačno s sneženjem",
    "overcast_heavyrasn_day": "Oblačno s močnim sneženjem",
    "overcast_heavyrasn_night": "Oblačno s močnim sneženjem",
    "overcast_modsn_day": "Oblačno s sneženjem",
    "overcast_modsn_night": "Oblačno s sneženjem",
    "overcast_lightsn_day": "Sneži",
    "overcast_lightsn_night": "Sneži",
    "overcast_heavysn_day": "Močno sneženje",
    "overcast_heavysn_night": "Močno sneženje",
    "overcast_modtssn_day": "Oblačno s strelami",
    "overcast_modtssn_night": "Oblačno s strelami",
    "overcast_heavytssn_day": "Oblačno s strelami",
    "overcast_heavytssn_night": "Oblačno s strelami",

    # Delno oblačna stanja
    "partcloudy_night": "Delno oblačno",
    "partcloudy_day": "Delno oblačno",
    "partcloudy_lightra_day": "Delno oblačno z rahlim dežjem",
    "partcloudy_lightra_night": "Delno oblačno z rahlim dežjem",
    "partcloudy_heavytsra_day": "Delno oblačno s strelami in dežjem",
    "partcloudy_heavytsra_night": "Delno oblačno s strelami in dežjem",
    "partcloudy_modsn_day": "Delno oblačno s sneženjem",
    "partcloudy_modsn_night": "Delno oblačno s sneženjem",
    "partcloudy_lightsn_day": "Delno oblačno s sneženjem",
    "partcloudy_lightsn_night": "Delno oblačno s sneženjem",
    "partcloudy_heavysn_day": "Delno oblačno s sneženjem",
    "partcloudy_heavysn_night": "Delno oblačno s sneženjem",
    "partcloudy_lightfg_day": "Rahlo oblačno",
    "partcloudy_lightfg_night": "Rahlo oblačno",
    "partcloudy_lightrasn_day": "Delno oblačno s sneženjem in dežjem",
    "partcloudy_lightrasn_night": "Delno oblačno s sneženjem in dežjem",
    "partcloudy_modrasn_day": "Delno oblačno s sneženjem in dežjem",
    "partcloudy_modrasn_night": "Delno oblačno s sneženjem in dežjem",
    "partcloudy_heavyrasn_day": "Delno oblačno s močnim sneženjem",
    "partcloudy_heavyrasn_night": "Delno oblačno s močnim sneženjem",
    "partcloudy_modra_day": "Delno oblačno z dežjem",
    "partcloudy_modra_night": "Delno oblačno z dežjem",
    "partcloudy_modtsra_day": "Delno oblačno s strelami in dežjem",
    "partcloudy_modtsra_night": "Delno oblačno s strelami in dežjem",
    "partcloudy_lighttsra_day": "Delno oblačno z rahlim dežjem in strelami",
    "partcloudy_lighttsra_night": "Delno oblačno z rahlim dežjem in strelami",

    # Stanja nevihte
    "prevcloudy_modts_day": "Oblačno s strelami",
    "prevcloudy_modts_night": "Oblačno s strelami",
    "prevcloudy_heavyts_day": "Močno oblačno s strelami",
    "prevcloudy_heavyts_night": "Močno oblačno s strelami",
    "prevcloudy_lightra_day": "Oblačno z rahlim dežjem in strelami",
    "prevcloudy_lightra_night": "Oblačno z rahlim dežjem in strelami",
    "prevcloudy_modra_day": "Oblačno z dežjem",
    "prevcloudy_modra_night": "Oblačno z dežjem",
    "prevcloudy_heavyra_day": "Močno deževno",
    "prevcloudy_heavyra_night": "Močno deževno",
    "prevcloudy_modsn_day": "Oblačno s sneženjem",
    "prevcloudy_modsn_night": "Oblačno s sneženjem",
    "prevcloudy_lightsn_day": "Sneži",
    "prevcloudy_lightsn_night": "Sneži",
    "prevcloudy_heavysn_day": "Močno sneženje",
    "prevcloudy_heavysn_night": "Močno sneženje",
    "prevcloudy_lightfg_day": "Oblačno",
    "prevcloudy_lightfg_night": "Oblačno",
    "prevcloudy_modfg_day": "Megleno",
    "prevcloudy_modfg_night": "Megleno",
    "prevcloudy_heavyfg_day": "Močno megleno",
    "prevcloudy_heavyfg_night": "Močno megleno",
    "prevcloudy_lightrasn_day": "Oblačno s sneženjem in dežjem",
    "prevcloudy_lightrasn_night": "Oblačno s sneženjem in dežjem",
    "prevcloudy_lighttsra_day": "Oblačno z dežjem",
    "prevcloudy_lighttsra_night": "Oblačno z dežjem",
    "prevcloudy_modtsra_day": "Oblačno z dežjem",
    "prevcloudy_modtsra_night": "Oblačno z dežjem",
    "prevcloudy_heavytsra_day": "Močno deževno",
    "prevcloudy_heavytsra_night": "Močno deževno",
    "prevcloudy_modrasn_day": "Oblačno s sneženjem in dežjem",
    "prevcloudy_modrasn_night": "Oblačno s sneženjem in dežjem",

    # Jasno/sončno
    "clear_night": "Jasno (nočno)",
    "clear_day": "Jasno (dnevno)",
    "clear_lightfg_night": "Rahlo jasno (nočno)",
    "clear_lightfg_day": "Rahlo jasno (dnevno)",
    "mostly_clear_night": "Pretežno jasno (nočno)",
    "mostly_clear_day": "Pretežno jasno (dnevno)",
    "foggy": "Megleno",
    "drizzle": "Rahel dež",
    "light_snow": "Rahlo sneženje",
    "heavy_snow": "Močno sneženje",
    "partly_cloudy_rain": "Delno oblačno z dežjem",
    "partly_cloudy_day": "Delno oblačno",
    "partly_cloudy_night": "Delno oblačno",
    "thunderstorm": "Nevihte s strelami",
    "hailstorm": "Toča",
    "blizzard": "Snežni vihar",
    "prevcloudy_day": "Oblačno",
    "prevcloudy_night": "Oblačno",
}


###########################################################################
# ASINHRONA POSTAVITEV SENZORJEV
###########################################################################

async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Inicializacija ARSO Weather senzorjev preko config entry."""
    location = config_entry.data.get("location")
    monitored_conditions = config_entry.data.get("monitored_conditions", list(SENSOR_TYPES.keys()))
    _LOGGER.debug(f"Monitored conditions for {location}: {monitored_conditions}")
    if not monitored_conditions:
        _LOGGER.warning("No monitored_conditions specified for location: %s. No sensors will be added.", location)
        return

    entities = []

    # Naprava za senzorje vremenskih podatkov (lokalni senzorji)
    local_device_info = {
        "identifiers": {(DOMAIN, f"arso_weather_sensors_{location}")},
        "name": f"ARSO vremenska postaja - {location.title()}",
        "manufacturer": "ARSO",
        "model": "Vremenski podatki",
        "entry_type": "service",
    }

    # Dodajamo Sun/Snow senzorje - snow_cover_thickness
    if "snow_cover_thickness" in monitored_conditions or "sun_radiation" in monitored_conditions:
        from .sun_snow import fetch_sun_snow_data # Dodaj lokalni import
        from custom_components.slovenian_weather_integration.helpers import normalize_location #dodaj lokalni import
        data = await fetch_sun_snow_data()
        location_norm = normalize_location(location.lower())
        if data and location_norm in data:
             station_data = data[location_norm]
        else:
            station_data = {} #prazen dictionary
            _LOGGER.warning(f"No Sun/Snow data available for {location} (normalized: {location_norm})")
        sun_snow_device_info = local_device_info
        if "sun_radiation" in monitored_conditions:
            entities.append(ArsoSunSnowSensor(hass, location, "sun_radiation", sun_snow_device_info,station_data))
            _LOGGER.debug("Dodajam Sun Radiation")

        if "snow_cover_thickness" in monitored_conditions:
            entities.append(ArsoSunSnowSensor(hass, location, "snow_cover_thickness", sun_snow_device_info, station_data))
            _LOGGER.debug("Dodajam Snow Cover Thickness")



    weather_sensor_types = [
        st for st in monitored_conditions if st not in ("sun_radiation", "snow_cover_thickness")
    ]

    # Dodajamo vremenske senzorje (npr. temperature, vlažnost, pritisek, itd.)
    for sensor_type in weather_sensor_types:
        entities.append(ArsoWeatherSensor(hass, location, sensor_type, monitored_conditions))

    # Dodamo tudi senzor kakovosti zraka (Air Quality) kot senzor, ki bo prikazan kot 'sensor.air_quality_<lokacija>'
    if location:
        entities.append(ArsoAirQualitySensor(hass, location))

    # **Pridobitev agro podatkov (forecast in observation)**
    forecast_data = await fetch_agro_data(ARSO_AGRO_FORECAST_URL)
    observation_data = await fetch_agro_data(ARSO_AGRO_OBSERVATION_URL)

    if not forecast_data:
        _LOGGER.warning("No forecast agro data available for %s", location)
    if not observation_data:
        _LOGGER.warning("No observation agro data available for %s", location)

    # **Dodajanje agro senzorjev v Weather Sensors**
    if forecast_data or observation_data:
        entities.append(ArsoAgroSensor(hass, location, observation_data, forecast_data, local_device_info))
        entities.append(ArsoAgroForecastSensor(hass, location, forecast_data, local_device_info))
    else:
        _LOGGER.warning("No agro data available, skipping Agro sensors!")

    # ✅ **Dodamo Pollen senzorje**
    global_device_info = {
        "identifiers": {(DOMAIN, "arso_weather_pollen_radar")},
        "name": "ARSO Biovreme in vremenski radar",
        "manufacturer": "ARSO",
        "model": "Cvetni prah, vremenski radar in napoved v sliki",
        "entry_type": "service",
    }

    entities.append(ArsoPollenSensor(global_device_info))
    entities.append(ArsoPollenForecastSensor(global_device_info))

    _LOGGER.info("Adding %d sensors", len(entities))
    async_add_entities(entities, True)

###########################################################################
# DEFINICIJA SENZORJA: ArsoWeatherSensor
###########################################################################

class ArsoWeatherSensor(Entity):
    """
    Reprezentacija ARSO Weather senzorja, ki pridobiva podatke direktno iz API-ja in (za dew_point in visibility)
    iz RSS feeda.
    """
    def __init__(self, hass: HomeAssistant, location: str, sensor_type: str, monitored_conditions: list):
        self._hass = hass
        self._location = location  # Ime, kot je konfigurirano
        self._sensor_type = sensor_type.strip().lower()
        self._monitored_conditions = monitored_conditions
        self._attr_name = f"ARSO Weather {location.capitalize()} - {SENSOR_TYPES[sensor_type][0]}"
        self._attr_unit_of_measurement = SENSOR_TYPES[sensor_type][1]
        self._icon = SENSOR_TYPES[sensor_type][2]
        self._device_class = SENSOR_TYPES[sensor_type][3]
        self._state = None
        # Poskušamo pridobiti _station_code iz mappinga (RSS_STATION_CODES)
        from .const import RSS_STATION_CODES
        self._station_code = RSS_STATION_CODES.get(location)

    @property
    def unique_id(self) -> str:
        return f"arso_weather_{self._location.replace(' ', '_').lower()}_{self._sensor_type}"

    @property
    def name(self) -> str:
        return self._attr_name

    @property
    def state(self):
        return self._state

    @property
    def unit_of_measurement(self) -> str:
        return self._attr_unit_of_measurement

    @property
    def icon(self) -> str:
        return self._icon

    @property
    def device_class(self):
        return self._device_class

    @property
    def available(self):
        return self._state is not None

    @property
    def extra_state_attributes(self):
        """V tej osnovni različici ne definiramo dodatnih atributov za vremenske senzorje.
        (Podatke o vremenskih parametrih najdete v atributeh posameznih entitet, če jih API nudi.)
        """
        return {}

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._location)},
            "name": f"ARSO Weather Station - {self._location.title()}",
            "manufacturer": "ARSO",
            "model": "Vremenski podatki",
            "entry_type": "service",
        }

    @property
    def entity_registry_enabled_default(self) -> bool:
        return True

    async def async_update(self):
        """
        Posodobi stanje senzorja z najnovejšimi podatki.
        Za senzorje tipa "dew_point" in "visibility" se podatki pridobivajo iz RSS feeda,
        medtem ko se ostali senzorji osvežujejo iz API-ja.
        """
        sensor_type = self._sensor_type  # že v male črke
        session = async_get_clientsession(self._hass)
        encoded_location = quote(self._location, safe="")
        api_url = f"{API_URL}?location={encoded_location}"
        current_data = {}
        # Če senzor NI "dew_point" in "visibility": pridobi podatke iz API-ja
        if sensor_type not in ["dew_point", "visibility"]:
            try:
                async with session.get(api_url) as response:
                    if response.status != 200:
                        _LOGGER.warning("Failed to fetch API data for %s: HTTP %s", self._location, response.status)
                        self._state = None
                        return
                    data = await response.json()
                    # Poskus pridobitve podatkov iz "observation"
                    observation = data.get("observation", {}).get("features", [])
                    if observation:
                        obs_days = observation[0].get("properties", {}).get("days", [])
                        if obs_days:
                            obs_timeline = obs_days[0].get("timeline", [])
                            if obs_timeline:
                                obs_entry = obs_timeline[0]
                                current_data["temperature"] = float(obs_entry.get("t", 0))
                                current_data["pressure"] = float(obs_entry.get("msl", 0))
                                raw_obs_condition = obs_entry.get("clouds_icon_wwsyn_icon", "").strip().lower()
                                current_data["condition"] = (CLOUD_CONDITION_MAP.get(raw_obs_condition, "unknown")
                                                             if raw_obs_condition else None)
                                obs_cloud_text = obs_entry.get("clouds_shortText", "jasno").strip().lower()
                                current_data["cloud_coverage"] = CLOUD_COVERAGE_MAP.get(obs_cloud_text, 0)
                                current_data["humidity"] = float(obs_entry.get("rh", 0))
                                current_data["wind_speed"] = float(obs_entry.get("ff_val", 0))
                                current_data["wind_gust_speed"] = float(obs_entry.get("ffmax_val", 0) or 0)
                                current_data["wind_bearing"] = WIND_DIRECTION_MAP.get(obs_entry.get("dd_shortText", ""), "")
                            else:
                                _LOGGER.warning("No timeline data in observation for %s", self._location)
                        else:
                            _LOGGER.warning("No days data in observation for %s", self._location)
                    else:
                        _LOGGER.warning("No observation data available for %s", self._location)
                    # Fallback: če ključni podatki niso na voljo, uporabimo forecast1h
                    if data.get("forecast1h"):
                        forecast1h = data.get("forecast1h", {}).get("features", [])
                        if forecast1h:
                            f1h_entry = forecast1h[0].get("properties", {}).get("days", [])[0]["timeline"][0]
                            if "temperature" not in current_data or current_data["temperature"] is None:
                                current_data["temperature"] = float(f1h_entry.get("t", 0))
                            if "pressure" not in current_data or current_data["pressure"] is None:
                                current_data["pressure"] = float(f1h_entry.get("msl", 0))
                            if "condition" not in current_data or current_data["condition"] is None:
                                raw_fcast_condition = f1h_entry.get("clouds_icon_wwsyn_icon", "").strip().lower()
                                current_data["condition"] = (CLOUD_CONDITION_MAP.get(raw_fcast_condition, "unknown")
                                                             if raw_fcast_condition else None)
                            if "cloud_coverage" not in current_data or current_data["cloud_coverage"] is None:
                                fallback_cloud_text = f1h_entry.get("clouds_shortText", "jasno").strip().lower()
                                current_data["cloud_coverage"] = CLOUD_COVERAGE_MAP.get(fallback_cloud_text, 0)
                            if "humidity" not in current_data or current_data["humidity"] is None:
                                current_data["humidity"] = float(f1h_entry.get("rh", 0))
                            if "wind_speed" not in current_data or current_data["wind_speed"] is None:
                                current_data["wind_speed"] = float(f1h_entry.get("ff_val", 0))
                            if "wind_gust_speed" not in current_data or current_data["wind_gust_speed"] is None:
                                current_data["wind_gust_speed"] = float(f1h_entry.get("ffmax_val", 0) or 0)
                            if "wind_bearing" not in current_data or current_data["wind_bearing"] is None:
                                current_data["wind_bearing"] = WIND_DIRECTION_MAP.get(f1h_entry.get("dd_shortText", ""), "")
                            # Dodatni senzorji, ki jih ni v observation
                            if sensor_type == "weather_phenomenon":
                                current_data["weather_phenomenon"] = f1h_entry.get("clouds_shortText_wwsyn_shortText", None)
                            elif sensor_type == "snowfall":
                                current_data["snowfall"] = f1h_entry.get("sn_acc", None) #Sprememba
                            elif sensor_type == "precipitation":
                                current_data["precipitation"] = f1h_entry.get("tp_acc", None)
                            elif sensor_type == "cloud_base":
                                current_data["cloud_base"] = f1h_entry.get("cloudBase_shortText", None)
                            elif sensor_type == "pressure_tendency":
                                current_data["pressure_tendency"] = f1h_entry.get("pa_shortText", None)
                        else:
                            _LOGGER.warning("No forecast1h data available for %s", self._location)
                    # Nastavimo stanje senzorja (API podatki)
                    if sensor_type in current_data:
                        self._state = current_data[sensor_type]
                    else:
                        _LOGGER.warning("Unknown sensor type or missing data: %s", sensor_type)
                        self._state = None
            except Exception as e:
                _LOGGER.error("Error fetching API data for %s: %s", self._location, e)
                self._state = None
        # Če je tip senzorja "dew_point" ali "visibility", uporabimo RSS feed
        if sensor_type in ["dew_point", "visibility"]:
            if self._station_code:
                rss_url = f"https://meteo.arso.gov.si/uploads/probase/www/observ/surface/text/sl/{self._station_code}_latest.rss"
                try:
                    async with session.get(rss_url) as rss_response:
                        if rss_response.status == 200:
                            rss_text = await rss_response.text()
                            import feedparser
                            feed = await self._hass.async_add_executor_job(feedparser.parse, rss_text)
                            if feed.entries:
                                details = self._extract_weather_details(feed.entries[0])
                                if sensor_type == "dew_point" and "native_dew_point" in details:
                                    self._state = float(details["native_dew_point"])
                                elif sensor_type == "visibility" and "native_visibility" in details:
                                    self._state = float(details["native_visibility"])
                                else:
                                    _LOGGER.warning("RSS feed does not contain data for %s at %s", sensor_type, self._location)
                                    self._state = None
                        else:
                            _LOGGER.warning("Failed to fetch RSS data for %s: HTTP %s", self._location, rss_response.status)
                            self._state = None
                except Exception as e:
                    _LOGGER.error("Error fetching RSS data for %s: %s", self._location, e)
                    self._state = None
            else:
                _LOGGER.info("No station code available for RSS feed for %s", self._location)
                self._state = None

    def _extract_weather_details(self, entry):
        """Extract additional details (npr. dew point, visibility) from RSS feed."""
        details = {}
        patterns = {
            "native_dew_point": r"Temperatura rosišča:\s*(-?\d+\.?\d*)\s*°C",
            "native_visibility": r"Vidnost:\s*(\d+\.?\d*)\s*km",
        }
        combined_text = f"{entry.title} {entry.summary}"
        for key, pattern in patterns.items():
            match = re.search(pattern, combined_text)
            if match:
                details[key] = match.group(1)
        if "dew_point" not in details and "native_dew_point" in details:
            details["dew_point"] = details["native_dew_point"]
        if "visibility" not in details and "native_visibility" in details:
            details["visibility"] = details["native_visibility"]
        return details

# ------------------------------------------------------------------
# ArsoPollenSensor: Senzor za cvetni prah
# ------------------------------------------------------------------
class ArsoPollenSensor(Entity):
    """Representation of the ARSO Pollen sensor."""

    def __init__(self, device_info):
        """Initialize the sensor."""
        self._state = None
        self._attributes = {}
        self._device_info = device_info
        _LOGGER.info("Initialized ARSO Pollen sensor.")

    async def async_update(self):
        """Fetch the latest pollen data."""
        _LOGGER.debug("Updating ARSO Pollen sensor...")
        data = await fetch_pollen_data()
        if data:
            # Preoblikujemo state: seznam imen rastlin z malo začetnico
            plant_names = [rastlina["ime"].lower() for rastlina in data]
            self._state = ", ".join(plant_names) if plant_names else "Ni podatkov"

            # Atribute preoblikujemo v bolj berljivo obliko
            self._attributes = {
                rastlina["ime"].lower(): {
                    "id": rastlina.get("id", "Ni podatkov"),
                    "ime": rastlina["ime"].lower(),
                    "lat": rastlina.get("ime_lat", "Ni podatkov"),
                    "faza": rastlina["faze"][0]["id_faze"] if rastlina.get("faze") else "Ni podatkov",
                    "ime_faze": rastlina["faze"][0]["ime_faze"] if rastlina.get("faze") else "Ni podatkov",
                }
                for rastlina in data
            }

            _LOGGER.info("ARSO Pollen sensor updated: %s", self._state)
        else:
            self._state = "Ni podatkov"
            self._attributes = {}
            _LOGGER.warning("No pollen data available!")

    @property
    def name(self):
        return "ARSO Pollen Sensor"

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return {
            **self._attributes,
            "icon": "mdi:flower",
            "attribution": "Vir: Agencija RS za okolje & Nacionalni laboratorij za zdravje, okolje in hrano",
            "friendly_name": "ARSO Biovreme cvetni prah"
        }

    @property
    def unique_id(self):
        return f"{DOMAIN}_pollen_{self._device_info['identifiers']}"


    @property
    def icon(self):
        return "mdi:flower"

    @property
    def device_info(self):
        return self._device_info

class ArsoPollenForecastSensor(Entity):
    """Representation of the ARSO Pollen Forecast sensor."""

    def __init__(self, device_info):
        """Initialize the forecast sensor."""
        self._state = None
        self._attributes = {}
        self._device_info = device_info
        _LOGGER.info("Initialized ARSO Pollen Forecast sensor.")

    async def async_update(self):
        """Fetch the latest pollen forecast data."""
        _LOGGER.debug("Updating ARSO Pollen Forecast sensor...")
        data = await fetch_pollen_forecast()
        if data:
            pubdate = data["articleinfo"].get("pubdate", "Ni podatkov")
            ts_updated = data.get("tsUpdated", "Ni podatkov")

            # Poiščemo napoved cvetnega prahu
            pollen_forecast_section = next(
                (section for section in data["section"] if section["title"] == "NAPOVED CVETNEGA PRAHU V ZRAKU"),
                None
            )

            pollen_forecast_text = "\n".join(pollen_forecast_section["para"]) if pollen_forecast_section else "Ni podatkov"

            self._state = "Napoved na voljo" if pollen_forecast_text else "Ni podatkov"
            self._attributes = {
                "napoved": pollen_forecast_text,
                "datum": pubdate,
                "posodobljeno": ts_updated,
                "icon": "mdi:flower-pollen",
                "friendly_name": "ARSO Biovreme napoved cvetnega prahu"
            }

            _LOGGER.info("ARSO Pollen Forecast sensor updated.")
        else:
            self._state = "Ni podatkov"
            self._attributes = {}
            _LOGGER.warning("No pollen forecast data available!")

    @property
    def name(self):
        return "ARSO Pollen Forecast"

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    @property
    def unique_id(self):
        return f"{DOMAIN}_pollen_forecast_{self._device_info['identifiers']}"


    @property
    def icon(self):
        return "mdi:flower-pollen"

    @property
    def device_info(self):
        return self._device_info

      
      
class ArsoSunSnowSensor(Entity):
    """
    Reprezentacija senzorja za sončno sevanje ali snežno odejo.
    """

    def __init__(self, hass: HomeAssistant, location: str, sensor_type: str, device_info,station_data):
        """Inicializacija senzorja."""
        self._hass = hass
        self._location = location
        self._sensor_type = sensor_type
        self._station_data = station_data
        self._attr_name = f"ARSO Weather {location.capitalize()} - {SENSOR_TYPES[sensor_type][0]}"
        self._attr_unique_id = f"arso_weather_{self._location.replace(' ', '_').lower()}_{self._sensor_type}"
        self._device_info = device_info
        self._state = None
        self._attr_unit_of_measurement = "W/m2" if sensor_type == "sun_radiation" else "cm"
        self._attr_icon = "mdi:weather-sunny" if sensor_type == "sun_radiation" else "mdi:snowflake"
        self._attr_device_class = "illuminance" if sensor_type == "sun_radiation" else None
        self._attr_state_class = "measurement"

    @property
    def name(self):
        """Vrne ime senzorja."""
        return self._attr_name

    @property
    def unique_id(self) -> str:
        return self._attr_unique_id

    @property
    def state(self):
        """Vrne stanje senzorja."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Vrne enoto merjenja."""
        return self._attr_unit_of_measurement

    @property
    def icon(self):
        """Vrne ikono senzorja."""
        return self._attr_icon

    @property
    def device_class(self):
        return self._attr_device_class

    @property
    def state_class(self):
        return self._attr_state_class

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._location)},
            "name": f"ARSO vremenska postaja - {self._location.title()}",
            "manufacturer": "ARSO",
            "model": "Vremenski podatki",
            "entry_type": "service",
        }


    async def async_update(self):
        """Posodobi stanje senzorja."""

        if self._sensor_type == "sun_radiation":
             if self._station_data:
                self._state = self._station_data.get("sun_radiation")
                _LOGGER.debug("Sončno sevanje za %s: %s", self._location, self._state)
             else:
                 _LOGGER.warning("Ni podatkov o sončnem sevanju za %s", self._location)
                 self._state = None
        elif self._sensor_type == "snow_cover_thickness":
            if self._station_data:
               self._state = self._station_data.get("snow_height") #spremenimo snow height v snow_cover_thickness, ker beremo odejo
               _LOGGER.debug("Debelina snežne odeje za %s: %s", self._location, self._state)
            else:
                _LOGGER.warning("Ni podatkov o debelini snežne odeje za %s",self._location)
                self._state = None

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Če v prihodnosti dodajaš listenerje ali pahraniš reference na entitete,
    # jih tukaj sprosti ali prekliči.
    return True
