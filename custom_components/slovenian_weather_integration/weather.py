
import aiohttp
import asyncio
import logging
import re
import feedparser
from datetime import datetime, timedelta
import pytz
import math
from homeassistant.components.weather import WeatherEntity, WeatherEntityFeature
from homeassistant.const import UnitOfTemperature, UnitOfPressure, UnitOfSpeed, UnitOfLength
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.dt import as_local
from .const import DOMAIN, API_URL, RSS_STATION_CODES, LOCATIONS_URL
from .utci import fetch_utci_data, fetch_utci_forecast_data
from .air import fetch_air_quality_data, normalize_location
from .utci_calc import fetch_all_station_data

_LOGGER = logging.getLogger(__name__)

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

# Podatki za pretvorbo oblaka iz besedilne ocene v odstotno vrednost
CLOUD_COVERAGE_MAP = {
    "jasno": 0,
    "pretežno jasno": 12.5,
    "delno jasno": 25,
    "delno oblačno": 50,
    "zmerno oblačno": 62.5,
    "pretežno oblačno": 87.5,
    "oblačno": 100,
}

# Preslikava stanj – uporabljamo jo zgolj za "condition" (ki se ločeno določi)

CLOUD_CONDITION_MAP = {
    # Common weather conditions from 'wwsyn_shortText' and 'clouds_shortText'
    "jasno": "sunny",
    "delno oblačno": "partlycloudy",
    "pretežno oblačno": "cloudy",
    "oblačno": "cloudy",
    "megla": "fog",
    "dežuje": "rainy",
    "možnost neviht": "lightning-rainy",
    "dež": "rainy",
    "plohe": "pouring",
    "sneži": "snowy",
    "toča": "hail",
    "sneg z dežjem": "snowy-rainy",
    "vetrovno": "windy",
    "veter z oblaki": "windy-variant",

    # Overcast conditions with thunderstorms and rain ('clouds_icon_wwsyn_icon')
    "overcast_heavytsra_day": "lightning-rainy",
    "overcast_heavytsra_night": "lightning-rainy",
    "overcast_heavyra_day": "rainy",  
    "overcast_heavyra_night": "rainy",
    "overcast_modtsra_day": "lightning-rainy",
    "overcast_modtsra_night": "lightning-rainy",
    "overcast_modra_day": "rainy",  
    "overcast_modra_night": "rainy",
    "overcast_lightra_day": "rainy",
    "overcast_lightra_night": "rainy",
    "overcast_lighttsra_day": "lightning-rainy",
    "overcast_lighttsra_night": "lightning-rainy",
    "overcast_day": "cloudy",
    "overcast_night": "cloudy",
    "overcast_lightfg_night": "cloudy",
    "overcast_lightfg_day": "cloudy",
    "overcast_lightra_night": "rainy",
    "overcast_lightra_day": "rainy",
    "overcast_modrasn_night": "snowy-rainy",
    "overcast_modrasn_day": "snowy-rainy",
    "overcast_lightrasn_day": "snowy-rainy",
    "overcast_lightrasn_night": "snowy-rainy",
    "overcast_heavyrasn_night": "snowy-rainy",
    "overcast_heavyrasn_day": "snowy-rainy",
    "overcast_modsn_day": "snowy",
    "overcast_modsn_night": "snowy",
    "overcast_lightsn_day": "snowy",
    "overcast_lightsn_night": "snowy",
    "overcast_modra_night": "rainy",
    "overcast_modra_day": "rainy",
    "overcast_heavysn_night": "snowy",
    "overcast_heavysn_day": "snowy",
    "overcast_modtssn_night": "lightning",
    "overcast_modtssn_day": "lightning",
    "overcast_heavytssn_day": "lightning",
    "overcast_heavytssn_night": "lightning",
    

    # Partly cloudy and rainy conditions ('clouds_icon_wwsyn_icon')
    "partcloudy_night": "partlycloudy", 
    "partcloudy_day": "partlycloudy", 
    "partcloudy_lightra_day": "pouring", 
    "partcloudy_lightra_night": "pouring", 
    "partcloudy_heavytsra_day": "lightning-rainy", 
    "partcloudy_heavytsra_night": "lightning-rainy",
    "partcloudy_modsn_night": "snowy",
    "partcloudy_modsn_day": "snowy",
    "partcloudy_lightsn_night": "snowy",
    "partcloudy_lightsn_day": "snowy",
    "partcloudy_heavysn_night": "snowy",
    "partcloudy_heavysn_day": "snowy",
    "partcloudy_lightfg_day": "fog",
    "partcloudy_lightfg_night": "fog",
    "partcloudy_lightrasn_day": "snowy-rainy",
    "partcloudy_lightrasn_night": "snowy-rainy",
    "partcloudy_modrasn_day": "snowy-rainy",
    "partcloudy_modrasn_night": "snowy-rainy",
    "partcloudy_heavyrasn_day": "snowy-rainy",
    "partcloudy_heavyrasn_night": "snowy-rainy",
    "partcloudy_modra_day": "rainy",
    "partcloudy_modra_night": "rainy",
    "partcloudy_modtsra_day": "lightning-rainy",
    "partcloudy_modtsra_night": "lightning-rainy",
    "partcloudy_lighttsra_day": "lightning-rainy",
    "partcloudy_lighttsra_night": "lightning-rainy",
    "partcloudy_heavytsra_day": "lightning-rainy",
    "partcloudy_heavytsra_night": "lightning-rainy",
    "partCloudy_lighttssn_day": "snowy",
    "partCloudy_lighttssn_night": "snowy",
    
    # Storm conditions ('clouds_icon_wwsyn_icon')
    "prevcloudy_modts_day": "lightning",  
    "prevcloudy_modts_night": "lightning",  
    "prevcloudy_heavyts_day": "lightning",  
    "prevcloudy_heavyts_night": "lightning",  
    "prevcloudy_lightra_night": "rainy",
    "prevcloudy_lightra_day": "rainy",
    "prevcloudy_modra_day": "rainy",
    "prevcloudy_modra_night": "rainy",
    "prevcloudy_heavyra_day": "rainy",
    "prevcloudy_heavyra_night": "rainy",
    "prevcloudy_modsn_day": "snowy",
    "prevcloudy_modsn_night": "snowy",
    "prevcloudy_lightsn_day": "snowy",
    "prevcloudy_lightsn_night": "snowy",
    "prevcloudy_heavysn_day": "snowy",
    "prevcloudy_heavysn_night": "snowy",
    "prevcloudy_lightfg_night": "cloudy",
    "prevcloudy_lightfg_day": "cloudy",
    "prevcloudy_modfg_night": "fog",
    "prevcloudy_modfg_day": "fog",
    "prevcloudy_heavyfg_night": "fog",
    "prevcloudy_heavyfg_day": "fog",
    "prevcloudy_lightrasn_day": "snowy-rainy",
    "prevcloudy_lightrasn_night": "snowy-rainy",
    "prevcloudy_lighttsra_day": "rainy",
    "prevcloudy_lighttsra_night": "rainy",
    "prevcloudy_modtsra_day": "rainy",
    "prevcloudy_modtsra_night": "rainy",
    "prevcloudy_heavytsra_day": "rainy",
    "prevcloudy_heavytsra_night": "rainy",
    "prevcloudy_modrasn_day": "snowy-rainy",
    "prevcloudy_modrasn_night": "snowy-rainy",

    # Clear conditions
    "clear_night": "clear-night",
    "clear_day": "sunny",
    "clear_lightfg_night": "fog",
    "clear_lightfg_day": "fog",
    "mostly_clear_night": "clear-night",
    "mostly_clear_day": "sunny",
    "foggy": "fog",
    "drizzle": "rainy",
    "light_snow": "snowy",
    "heavy_snow": "snowy",
    "partly_cloudy_rain": "rainy",
    "partly_cloudy_day": "partlycloudy",
    "partly_cloudy_night": "partlycloudy",
    "thunderstorm": "lightning-rainy",
    "hailstorm": "hail",
    "blizzard": "snowy",
    "prevcloudy_day": "cloudy",
    "prevcloudy_night": "cloudy",
}


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up ARSO Weather platform from a config entry."""
    location = config_entry.data.get("location", "Ljubljana")
    _LOGGER.debug("Creating ARSO Weather entity for location: %s", location)
    async_add_entities([ArsoWeather(location, config_entry.entry_id)], True)
    _LOGGER.debug("ARSO Weather entity for %s successfully created", location)

class ArsoWeather(WeatherEntity):
    """Representation of ARSO Weather entity."""

    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_HOURLY |
        WeatherEntityFeature.FORECAST_DAILY |
        WeatherEntityFeature.FORECAST_TWICE_DAILY
    )

    def __init__(self, location, entry_id):
        """Initialize the ARSO Weather entity."""
        self._location = location
        self._station_code = RSS_STATION_CODES.get(location)
        self._entry_id = entry_id

        # Current conditions
        self._attr_native_temperature = None
        self._attr_native_apparent_temperature = None
        self._attr_native_pressure = None
        self._attr_humidity = None
        self._attr_native_wind_speed = None
        self._attr_wind_bearing = None
        self._attr_native_wind_gust_speed = None
        self._attr_native_precipitation = None
        self._attr_condition = None
        # Dodan cloud coverage (v odstotkih)
        self._attr_cloud_coverage = None

        # Forecasts – initialize as empty lists
        self._daily_forecast = []
        self._hourly_forecast = []
        self._twice_daily_forecast = []

        # Additional attributes
        self._attr_native_dew_point = None
        self._attr_native_visibility = None
        self._attr_native_visibility_unit = None
        self._attr_ozone = None
        self._attr_uv_index = None

    def is_daytime(self):
        """Check if it is currently daytime based on the sun position."""
        from astral import LocationInfo
        from astral.sun import sun
        loc_info = LocationInfo(self._location)
        current_time = datetime.now(pytz.UTC)
        s = sun(loc_info.observer, date=current_time, tzinfo=pytz.UTC)
        return s["sunrise"] <= current_time <= s["sunset"]

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"{self._entry_id}_{self._location.lower().replace(' ', '_')}"

    @property
    def name(self):
        """Return the name of the entity."""
        return f"ARSO Weather - {self._location}"

    @property
    def native_temperature(self):
        return self._attr_native_temperature

    @property
    def native_temperature_unit(self):
        return UnitOfTemperature.CELSIUS

    @property
    def native_pressure(self):
        return self._attr_native_pressure

    @property
    def native_pressure_unit(self):
        return UnitOfPressure.HPA

    @property
    def humidity(self):
        return self._attr_humidity

    @property
    def native_wind_speed(self):
        return self._attr_native_wind_speed

    @property
    def native_wind_speed_unit(self):
        return UnitOfSpeed.KILOMETERS_PER_HOUR

    @property
    def native_wind_gust_speed(self):
        return self._attr_native_wind_gust_speed

    @property
    def wind_bearing(self):
        return self._attr_wind_bearing

    @property
    def native_precipitation(self):
        return self._attr_native_precipitation

    @property
    def precipitation_unit(self):
        return "mm"

    @property
    def condition(self):
        return self._attr_condition

    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        attrs = {
            "location": self._location,
            "attribution": "Vir: Agencija RS za okolje",
        }
        if self._attr_native_dew_point is not None:
            attrs["dew_point"] = self._attr_native_dew_point
        if self._attr_native_visibility is not None:
            attrs["visibility"] = self._attr_native_visibility
        if self._attr_native_apparent_temperature is not None:
            attrs["apparent_temperature"] = self._attr_native_apparent_temperature
        if self._attr_ozone is not None:
            attrs["ozone"] = self._attr_ozone
        if self._attr_uv_index is not None:
            attrs["uv_index"] = self._attr_uv_index
        if self._attr_cloud_coverage is not None:
            attrs["cloud_coverage"] = self._attr_cloud_coverage
        _LOGGER.debug("Weather entity attributes for %s: %s", self._location, attrs)
        return attrs

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

    @property
    def uv_index(self):
        return self._attr_uv_index

    async def async_update(self):
            """Fetch new state data for the entity.
            
            Note: We do not call self.async_write_ha_state() explicitly.
            """
            _LOGGER.debug("Starting update for ARSO Weather: %s", self._location)

            # Fetch UV index
            from .uv_index import fetch_uv_index, fetch_location_coords
            coords = await fetch_location_coords(self._location, LOCATIONS_URL)
            _LOGGER.debug("Fetched coordinates for UV index: %s", coords)
            if coords:
                lat, lon = coords
                uv = await fetch_uv_index(lat, lon)
                if uv is not None:
                    self._attr_uv_index = uv
                    _LOGGER.debug("UV index for %s: %s", self._location, uv)
                else:
                    self._attr_uv_index = None
                    _LOGGER.warning("UV index not available for %s", self._location)
            else:
                self._attr_uv_index = None
                _LOGGER.warning("Coordinates not found for %s", self._location)

            try:
                # 1. Pridobimo podatke iz fetch_all_station_data
                all_station_data = await fetch_all_station_data()
                if not all_station_data:
                    _LOGGER.warning("Failed to fetch all station data. Using cached data or defaults.")
                    return  # Uporabimo prejšnje podatke

                # 2. Poiščemo podatke za trenutno lokacijo
                current_station_data = None
                for station_data in all_station_data:
                    if station_data["station"].lower() == self._location.lower():
                        current_station_data = station_data
                        break

                if not current_station_data:
                    _LOGGER.warning("No data found for location: %s", self._location)
                    return  # Uporabimo prejšnje podatke

                # 3. Posodobimo atribute z novimi podatki
                # Preverjamo, ali so vrednosti prisotne v slovarju in jih šele nato uporabimo
                if "Temperatura [°C]" in current_station_data and current_station_data["Temperatura [°C]"] != "":
                    self._attr_native_temperature = float(current_station_data["Temperatura [°C]"])

                if "Vlažnost [%]" in current_station_data and current_station_data["Vlažnost [%]"] != "":
                    self._attr_humidity = float(current_station_data["Vlažnost [%]"])

                if "Hitrost vetra [km/h]" in current_station_data and current_station_data["Hitrost vetra [km/h]"] != "":
                    self._attr_native_wind_speed = float(current_station_data["Hitrost vetra [km/h]"])

                if "Sončno obsevanje [W/m2]" in current_station_data and current_station_data["Sončno obsevanje [W/m2]"] != "":
                    # Izračun UTCI samo, če imamo vse potrebne podatke
                    temperature = float(current_station_data["Temperatura [°C]"])
                    humidity = float(current_station_data["Vlažnost [%]"])
                    wind_speed_kmh = float(current_station_data["Hitrost vetra [km/h]"])
                    radiation = float(current_station_data["Sončno obsevanje [W/m2]"])
                                
                    # Izračun E (vpliv vlage)
                    e = (humidity / 100) * 6.105 * math.exp((17.27 * temperature) / (237.7 + temperature))
                                
                    # Poenostavljen izračun UTCI
                    wind_speed_ms = wind_speed_kmh/3.6
                    utci = temperature + (0.33 * e) - (0.7 * wind_speed_ms) - 4.0
                    self._attr_native_apparent_temperature = round(utci, 1)
                else:
                    self._attr_native_apparent_temperature = None
                    _LOGGER.debug("UTCI ni mogoče izračunati, ker manjkajo podatki o sončnem obsevanju za %s", self._location)

                # Condition, pressure and cloud_coverage can be obtained from API call
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{API_URL}?location={self._location}") as response:
                        if response.status == 200:
                            data = await response.json()
                            _LOGGER.debug("Data received from API for %s: %s", self._location, data)

                            # Pridobivanje trenutnih podatkov iz "observation"
                            observation = data.get("observation", {}).get("features", [])
                            if observation:
                                obs_days = observation[0].get("properties", {}).get("days", [])
                                if obs_days and len(obs_days) > 0:
                                    obs_timeline = obs_days[0].get("timeline", [])
                                    if obs_timeline and len(obs_timeline) > 0:
                                        obs_entry = obs_timeline[0]                                  
                                        raw_obs_condition = obs_entry.get("clouds_icon_wwsyn_icon", "").strip().lower()
                                        _LOGGER.debug("Observation raw condition for %s: '%s'", self._location, raw_obs_condition)
                                        if raw_obs_condition:
                                            self._attr_condition = CLOUD_CONDITION_MAP.get(raw_obs_condition, "unknown")
                                        else:
                                            self._attr_condition = None                                    
                                        obs_cloud_text = obs_entry.get("clouds_shortText", "jasno").strip().lower()
                                        self._attr_cloud_coverage = CLOUD_COVERAGE_MAP.get(obs_cloud_text, 0)
                                        self._attr_native_pressure = float(obs_entry.get("msl", 0))
                                    else:
                                        _LOGGER.warning("No timeline data in observation for %s", self._location)
                                else:
                                    _LOGGER.warning("No days data in observation for %s", self._location)
                            else:
                                _LOGGER.warning("No observation data available for %s, falling back to forecast1h", self._location)
                                
                                # Fallback: Uporabimo podatke iz forecast1h
                                forecast1h = data.get("forecast1h", {}).get("features", [])
                                if forecast1h:
                                    first_entry = forecast1h[0].get("properties", {}).get("days", [])[0]["timeline"][0]
                                    raw_fcast_condition = first_entry.get("clouds_icon_wwsyn_icon", "").strip().lower()
                                    _LOGGER.debug("Fallback - raw condition from forecast1h for %s: '%s'", self._location, raw_fcast_condition)
                                    if raw_fcast_condition:
                                        self._attr_condition = CLOUD_CONDITION_MAP.get(raw_fcast_condition, "unknown")
                                    else:
                                        self._attr_condition = None
                                    # Fallback: cloud_coverage iz forecast1h
                                    fallback_cloud_text = first_entry.get("clouds_shortText", "jasno").strip().lower()
                                    self._attr_cloud_coverage = CLOUD_COVERAGE_MAP.get(fallback_cloud_text, 0)
                                    self._attr_native_pressure = float(first_entry.get("msl", 0))
                                else:
                                    _LOGGER.warning("No forecast1h data available for %s", self._location)
                await self._fetch_forecasts()
            except Exception as err:
                _LOGGER.error("Exception during update for %s: %s", self._location, err)
            
            if self._station_code:
                try:
                    rss_url = f"https://meteo.arso.gov.si/uploads/probase/www/observ/surface/text/sl/{self._station_code}_latest.rss"
                    _LOGGER.debug("Fetching RSS data from: %s", rss_url)
                    feed_content = await self._fetch_rss_feed(rss_url)
                    if feed_content:
                        feed = await asyncio.to_thread(feedparser.parse, feed_content)
                        entry = feed.entries[0]
                        details = self._extract_weather_details(entry)
                        _LOGGER.debug("Extracted RSS details for %s: %s", self._location, details)
                        if "native_dew_point" in details:
                            self._attr_native_dew_point = float(details["native_dew_point"])
                        if "native_visibility" in details:
                            self._attr_native_visibility = float(details["native_visibility"])
                            self._attr_native_visibility_unit = UnitOfLength.KILOMETERS
                        _LOGGER.debug("RSS Data for %s - Dew Point: %s, Visibility: %s", self._location, self._attr_native_dew_point, self._attr_native_visibility)
                    else:
                        _LOGGER.info("No RSS feed available for location %s", self._location)
                except Exception as e:
                    _LOGGER.warning("Unable to fetch RSS feed for %s, skipping: %s", self._location, e)
            else:
                _LOGGER.info("No RSS feed available for location %s", self._location)

            try:
                from .air import normalize_location
                location_normalized = normalize_location(self._location)
                _LOGGER.debug("Fetching air quality data for %s (normalized: %s)", self._location, location_normalized)
                air_quality_data = await fetch_air_quality_data()
                _LOGGER.debug("Air quality data received for %s: %s", self._location, air_quality_data)
                if air_quality_data and location_normalized in air_quality_data:
                    ozone_value = air_quality_data[location_normalized].get("o3")
                    if ozone_value is not None:
                        try:
                            self._attr_ozone = float(ozone_value)
                            _LOGGER.info("Ozone value for %s: %s µg/m³", self._location, self._attr_ozone)
                        except (ValueError, TypeError) as e:
                            _LOGGER.warning("Invalid ozone value for %s: %s | Error: %s", self._location, ozone_value, e)
                            self._attr_ozone = None
                    else:
                        _LOGGER.warning("No ozone data available for %s", self._location)
                        self._attr_ozone = None
                    _LOGGER.debug("Final ozone value for %s: %s", self._location, self._attr_ozone)
                else:
                    _LOGGER.warning("No air quality data available for %s (normalized: %s)", self._location, location_normalized)
                    self._attr_ozone = None
            except Exception as e:
                _LOGGER.error("Error fetching ozone data for %s: %s", self._location, e)
                self._attr_ozone = None

    

    async def _fetch_forecasts(self):
        """Fetch daily, hourly, and twice daily forecast data."""
        _LOGGER.debug("Fetching forecast data for location: %s", self._location)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_URL}?location={self._location}") as response:
                    if response.status == 200:
                        forecast_data = await response.json()
                        _LOGGER.debug("Forecast API response for %s: %s", self._location, forecast_data)

                        # Pridobi tudi UTCI napovedne podatke
                        utci_forecast = await fetch_utci_forecast_data(self.hass, self._location)

                        # Posreduj utci_forecast v obdelavo 1h napovedi
                        self._hourly_forecast = self._process_hourly_forecast(forecast_data, utci_forecast)
                        _LOGGER.debug("Hourly forecast processed for %s: %s", self._location, self._hourly_forecast)

                        self._daily_forecast = await self._process_daily_forecast(forecast_data)
                        _LOGGER.debug("Daily forecast processed for %s: %s", self._location, self._daily_forecast)

                        self._daily_forecast = await self._async_add_uv_to_daily_forecast(self._daily_forecast)
                        _LOGGER.debug("Daily forecast with UV index for %s: %s", self._location, self._daily_forecast)

                        self._twice_daily_forecast = self._process_twice_daily_forecast(forecast_data)
                        _LOGGER.debug("Twice daily forecast processed for %s: %s", self._location, self._twice_daily_forecast)
                    else:
                        _LOGGER.warning("Failed to fetch forecast data for %s. HTTP Status: %s", self._location, response.status)
        except Exception as e:
            _LOGGER.error("Error fetching forecast data for location %s: %s", self._location, e, exc_info=True)

    def _process_hourly_forecast(self, forecast_data, utci_forecast):
        """Process the hourly forecast data and add apparent temperature if available."""
        hourly_forecasts = []
        forecast1h = forecast_data.get("forecast1h", {}).get("features", [])
        if forecast1h:
            for day in forecast1h[0].get("properties", {}).get("days", []):
                for entry in day.get("timeline", []):
                    # Izračunamo lokalni čas napovedi
                    forecast_time = as_local(datetime.fromisoformat(entry["valid"]).astimezone(pytz.UTC))
                    if (forecast_time - datetime.now(pytz.UTC)).total_seconds() <= 24 * 3600:
                        # Zaokrožimo čas na uro za primerjavo s CSV podatki
                        rounded_time = datetime.fromisoformat(entry["valid"]).astimezone(pytz.UTC).replace(minute=0, second=0, microsecond=0).isoformat()
                        apparent_temp = utci_forecast.get(rounded_time) if utci_forecast else None
                        _LOGGER.debug("1h Forecast for %s - UTC: %s, Local: %s, Temp: %s, Apparent Temp: %s", 
                                      self._location, entry["valid"], forecast_time, entry.get("t"), apparent_temp)
                        hourly_forecasts.append({
                            "datetime": forecast_time.isoformat(),
                            "temperature": float(entry.get("t", 0)),
                            "condition": CLOUD_CONDITION_MAP.get(entry.get("clouds_icon_wwsyn_icon", "").strip().lower(), "unknown"),
                            "native_wind_speed": float(entry.get("ff_val", 0)),
                            "native_wind_gust_speed": float(entry.get("ffmax_val", 0) or 0),
                            "wind_bearing": WIND_DIRECTION_MAP.get(entry.get("dd_shortText", ""), ""),
                            "precipitation": float(entry.get("tp_acc", 0)),
                            "snowfall": float(entry.get("sn_acc", 0)),
                            "cloud_coverage": CLOUD_COVERAGE_MAP.get(entry.get("clouds_shortText", "jasno").strip().lower(), 0),
                            "apparent_temperature": apparent_temp
                        })
        forecast3h = forecast_data.get("forecast3h", {}).get("features", [])
        if forecast3h:
            for day in forecast3h[0].get("properties", {}).get("days", []):
                for entry in day.get("timeline", []):
                    forecast_time = datetime.fromisoformat(entry["valid"]).astimezone(pytz.UTC)
                    if (forecast_time - datetime.now(pytz.UTC)).total_seconds() > 24 * 3600:
                        rounded_time = forecast_time.replace(minute=0, second=0, microsecond=0).isoformat()
                        apparent_temp = utci_forecast.get(rounded_time) if utci_forecast else None
                        _LOGGER.debug("3h Forecast for %s - UTC: %s, Temp: %s, Apparent Temp: %s", 
                                      self._location, entry["valid"], entry.get("t"), apparent_temp)
                        hourly_forecasts.append({
                            "datetime": forecast_time.isoformat(),
                            "temperature": float(entry.get("t", 0)),
                            "condition": CLOUD_CONDITION_MAP.get(entry.get("clouds_icon_wwsyn_icon", "").strip().lower(), "unknown"),
                            "native_wind_speed": float(entry.get("ff_val", 0)),
                            "native_wind_gust_speed": float(entry.get("ffmax_val", 0) or 0),
                            "wind_bearing": WIND_DIRECTION_MAP.get(entry.get("dd_shortText", ""), ""),
                            "precipitation": float(entry.get("tp_acc", 0)),
                            "snowfall": float(entry.get("sn_acc", 0)),
                            "cloud_coverage": CLOUD_COVERAGE_MAP.get(entry.get("clouds_shortText", "jasno").strip().lower(), 0),
                            "apparent_temperature": apparent_temp
                        })
        _LOGGER.debug("Processed Hourly Forecasts for %s: %s", self._location, hourly_forecasts)
        return hourly_forecasts

    async def _process_daily_forecast(self, forecast_data):
        """Process the daily forecast data and include UV index."""
        daily_forecasts = []
        from .uv_index import fetch_uv_index, fetch_location_coords
        coords = await fetch_location_coords(self._location, LOCATIONS_URL)
        if coords:
            lat, lon = coords
            uv_index = await fetch_uv_index(lat, lon)
            _LOGGER.debug("UV index for daily forecast for %s: %s", self._location, uv_index)
        else:
            uv_index = None
            _LOGGER.warning("Coordinates not found for %s; UV index will not be added", self._location)
        for day in forecast_data["forecast24h"]["features"][0]["properties"]["days"]:
            try:
                forecast_time = day["date"]
                precipitation = float(day["timeline"][0].get("tp_24h_acc", 0))
                snowfall = float(day["timeline"][0].get("sn_24h_acc", 0))
                min_temp = float(day["timeline"][0].get("tnsyn", 0))
                max_temp = float(day["timeline"][0].get("txsyn", 0))
                wind_speed = float(day["timeline"][0].get("ff_val", 0))
                wind_bearing = WIND_DIRECTION_MAP.get(day["timeline"][0].get("dd_shortText", ""), "")
                gust_speed_raw = day["timeline"][0].get("ffmax_val", 0)
                gust_speed = float(gust_speed_raw) if gust_speed_raw and gust_speed_raw.strip() != "" else 0
                condition = day["timeline"][0].get("clouds_icon_wwsyn_icon", "").strip().lower()
                condition_translated = CLOUD_CONDITION_MAP.get(condition, "unknown")
                daily_forecast = {
                    "datetime": forecast_time,
                    "temperature": max_temp,
                    "templow": min_temp,
                    "precipitation": precipitation,
                    "snowfall": snowfall,
                    "wind_speed": wind_speed,
                    "native_wind_gust_speed": gust_speed,
                    "wind_bearing": wind_bearing,
                    "condition": condition_translated,
                    "pressure": float(day["timeline"][0].get("msl", 0)),
                    "cloud_coverage": CLOUD_COVERAGE_MAP.get(day["timeline"][0].get("clouds_shortText", "jasno").strip().lower(), 0)
                }
                if uv_index is not None:
                    daily_forecast["uv_index"] = uv_index
                daily_forecasts.append(daily_forecast)
            except Exception as e:
                _LOGGER.error("Error processing daily forecast for day %s for %s: %s", day, self._location, e, exc_info=True)
        _LOGGER.debug("Processed Daily Forecasts with UV Index for %s: %s", self._location, daily_forecasts)
        return daily_forecasts[:11]

    def _process_twice_daily_forecast(self, forecast_data):
        """Extract twice daily forecast (morning and evening)."""
        _LOGGER.debug("Starting twice daily forecast processing for %s", self._location)
        twice_daily_forecasts = []
        now = datetime.now(tz=pytz.UTC)
        max_forecast_date = (now + timedelta(days=5)).date()
        forecast3h = forecast_data.get("forecast3h", {}).get("features", [])
        if forecast3h:
            _LOGGER.debug("Processing 3-hourly forecast data for %s", self._location)
            days = forecast3h[0].get("properties", {}).get("days", [])
            for day in days:
                day_date = datetime.strptime(day["date"], "%Y-%m-%d").date()
                if day_date > max_forecast_date:
                    continue
                timeline = day.get("timeline", [])
                # Morning forecast (6:00–12:00)
                morning_entries = [
                    entry for entry in timeline if datetime.fromisoformat(entry["valid"]).hour in range(6, 12)
                ]
                if morning_entries:
                    morning_templow = min(float(entry.get("t", 0)) for entry in morning_entries)
                    morning_temperature = max(float(entry.get("t", 0)) for entry in morning_entries)
                    morning_gust_speed = max(float(entry.get("ffmax_val", 0) or 0) for entry in morning_entries)
                    morning_wind_speed = max(float(entry.get("ff_val", 0)) for entry in morning_entries)
                    morning_wind_bearing = morning_entries[0].get("dd_shortText", "")
                    morning_precipitation = sum(float(entry.get("tp_acc", 0)) for entry in morning_entries)
                    morning_snow_accumulation = sum(float(entry.get("sn_acc", 0)) for entry in morning_entries)
                    morning_time = datetime.combine(day_date, datetime.min.time(), tzinfo=pytz.UTC).replace(hour=6)
                    twice_daily_forecasts.append({
                        "datetime": morning_time,
                        "templow": morning_templow,
                        "temperature": morning_temperature,
                        "native_wind_gust_speed": morning_gust_speed,
                        "wind_speed": morning_wind_speed,
                        "wind_bearing": WIND_DIRECTION_MAP.get(morning_wind_bearing, ""),
                        "precipitation": morning_precipitation,
                        "snow_accumulation": morning_snow_accumulation,
                        "condition": CLOUD_CONDITION_MAP.get(morning_entries[0].get("clouds_icon_wwsyn_icon", "").strip().lower(), "unknown"),
                        "is_daytime": True,
                        "cloud_coverage": CLOUD_COVERAGE_MAP.get(morning_entries[0].get("clouds_shortText", "jasno").strip().lower(), 0)
                    })
                # Evening forecast (12:00–18:00)
                evening_entries = [
                    entry for entry in timeline if datetime.fromisoformat(entry["valid"]).hour in range(12, 18)
                ]
                if evening_entries:
                    evening_templow = min(float(entry.get("t", 0)) for entry in evening_entries)
                    evening_temperature = max(float(entry.get("t", 0)) for entry in evening_entries)
                    evening_gust_speed = max(float(entry.get("ffmax_val", 0) or 0) for entry in evening_entries)
                    evening_wind_speed = max(float(entry.get("ff_val", 0)) for entry in evening_entries)
                    evening_wind_bearing = evening_entries[0].get("dd_shortText", "")
                    evening_precipitation = sum(float(entry.get("tp_acc", 0)) for entry in evening_entries)
                    evening_snow_accumulation = sum(float(entry.get("sn_acc", 0)) for entry in evening_entries)
                    evening_time = datetime.combine(day_date, datetime.min.time(), tzinfo=pytz.UTC).replace(hour=18)
                    twice_daily_forecasts.append({
                        "datetime": evening_time,
                        "templow": evening_templow,
                        "temperature": evening_temperature,
                        "native_wind_gust_speed": evening_gust_speed,
                        "wind_speed": evening_wind_speed,
                        "wind_bearing": WIND_DIRECTION_MAP.get(evening_wind_bearing, ""),
                        "precipitation": evening_precipitation,
                        "snow_accumulation": evening_snow_accumulation,
                        "condition": CLOUD_CONDITION_MAP.get(evening_entries[-1].get("clouds_icon_wwsyn_icon", "").strip().lower(), "unknown"),
                        "is_daytime": False,
                        "cloud_coverage": CLOUD_COVERAGE_MAP.get(evening_entries[-1].get("clouds_shortText", "jasno").strip().lower(), 0)
                    })
        _LOGGER.debug("Completed twice daily forecast processing for %s: %s", self._location, twice_daily_forecasts)
        return twice_daily_forecasts

    async def async_forecast_hourly(self):
        """Return the hourly forecast."""
        return self._hourly_forecast

    async def async_forecast_daily(self):
        """Return the daily forecast."""
        return self._daily_forecast if self._daily_forecast is not None else []

    async def async_forecast_twice_daily(self):
        """Return the twice daily forecast."""
        return self._twice_daily_forecast if self._twice_daily_forecast is not None else []

    def _extract_weather_details(self, entry):
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
        return details

    async def _fetch_rss_feed(self, url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 404:
                    _LOGGER.error(f"RSS feed not found for URL: {url}")
                    return None
                response.raise_for_status()
                return await response.text()

    async def _async_add_uv_to_daily_forecast(self, daily_forecasts: list) -> list:
        from .uv_index import fetch_daily_uv_forecast, fetch_location_coords
        coords = await fetch_location_coords(self._location, LOCATIONS_URL)
        if not coords:
            _LOGGER.warning("Coordinates not found for %s; UV forecast not added", self._location)
            return daily_forecasts
        lat, lon = coords
        uv_forecast = await fetch_daily_uv_forecast(lat, lon)
        if not uv_forecast:
            _LOGGER.warning("UV forecast not available for %s", self._location)
            return daily_forecasts
        _LOGGER.debug("UV forecast data for %s: %s", self._location, uv_forecast)
        for forecast in daily_forecasts:
            forecast_date = forecast.get("datetime")
            if isinstance(forecast_date, datetime):
                forecast_date = forecast_date.strftime("%Y-%m-%d")
            for uv_entry in uv_forecast:
                uv_date = uv_entry.get("date")
                if forecast_date == uv_date:
                    forecast["uv_index"] = uv_entry.get("uv_index")
                    break
        _LOGGER.debug("Daily forecasts after adding UV for %s: %s", self._location, daily_forecasts)
        return daily_forecasts
