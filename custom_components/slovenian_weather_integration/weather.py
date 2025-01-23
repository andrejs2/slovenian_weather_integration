import aiohttp
import logging
from datetime import datetime
from homeassistant.components.weather import WeatherEntity
from homeassistant.const import UnitOfTemperature, UnitOfPressure, UnitOfSpeed
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN
from homeassistant.components.weather import WeatherEntityFeature
from astral.sun import sun
from astral import LocationInfo
import pytz
import feedparser
import re
from .const import DOMAIN, RSS_STATION_CODES  
from homeassistant.const import UnitOfLength
import asyncio
from datetime import datetime, timedelta

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

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up ARSO Weather platform from a config entry."""
    location = config_entry.data.get('location', 'Ljubljana')  
    async_add_entities([ArsoWeather(location, config_entry.entry_id)], True)

class ArsoWeather(WeatherEntity):
    """Representation of ARSO Weather entity."""

    _attr_supported_features = WeatherEntityFeature.FORECAST_HOURLY | WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_TWICE_DAILY

    def __init__(self, location, entry_id):
        self._location = location
        self._station_code = RSS_STATION_CODES.get(location)
        self._attr_native_temperature = None
        self._attr_native_pressure = None
        self._attr_humidity = None
        self._attr_native_wind_speed = None
        self._attr_wind_bearing = None
        self._attr_native_wind_gust_speed = None
        self._attr_native_precipitation = None
        self._attr_condition = None
        self._daily_forecast = None
        self._hourly_forecast = None
        self._twice_daily_forecast = None
        self._entry_id = entry_id  
        self._attr_native_dew_point = None
        self._attr_native_visibility = None
        self._attr_native_visibility_unit = None

    def is_daytime(self):
        """Check if it is currently daytime based on the sun position."""
        loc_info = LocationInfo(self._location)
        s = sun(loc_info.observer, date=datetime.now(self.hass.config.time_zone))
        now = pytz.UTC.localize(datetime.utcnow())
        return s['sunrise'] <= now <= s['sunset']

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"{self._entry_id}_{self._location.lower()}"

    @property
    def name(self):
        """Return the name of the entity."""
        return f"ARSO VREME - {self._location}"

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
        """Return the current wind gust speed."""
        return self._attr_native_wind_gust_speed

    @property
    def wind_bearing(self):
        return self._attr_wind_bearing

    @property
    def condition(self):
        return self._attr_condition

    @property
    def forecast(self):
        """Return the forecast data based on the supported features."""
        if self._attr_supported_features & WeatherEntityFeature.FORECAST_TWICE_DAILY:
            return self._twice_daily_forecast
        elif self._attr_supported_features & WeatherEntityFeature.FORECAST_DAILY:
            return self._daily_forecast
        elif self._attr_supported_features & WeatherEntityFeature.FORECAST_HOURLY:
            return self._hourly_forecast
        return None


    @property
    def twice_daily_forecast(self):
        """Return twice daily forecast."""
        return self._twice_daily_forecast

    @property
    def native_precipitation(self):
        return self._attr_native_precipitation

    @property
    def precipitation_unit(self):
        return 'mm'

    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        return {
            "location": self._location,
            "attribution": "Vir: Agencija RS za okolje",
        }

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
        return attrs

    async def async_update(self):
        """Fetch new state data for the sensor and update the forecast."""
        _LOGGER.debug("Starting update for ARSO Weather: %s", self._location)
        try:
            await self._fetch_forecasts()
            _LOGGER.debug("Forecast update completed successfully for: %s", self._location)
        except Exception as e:
            _LOGGER.error("Unhandled error during forecast update for %s: %s", self._location, e, exc_info=True)


    async def _fetch_forecasts(self):
        """Fetch daily, hourly, and simulated twice-daily forecast data."""
        _LOGGER.debug("Fetching forecast data for location: %s", self._location)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://vreme.arso.gov.si/api/1.0/location/?location={self._location}") as response:
                    if response.status == 200:
                        forecast_data = await response.json()
                        _LOGGER.debug("API Response: %s", forecast_data)

                        self._hourly_forecast = self._process_hourly_forecast(forecast_data)
                        _LOGGER.debug("Hourly forecast processed: %s", self._hourly_forecast)

                        self._daily_forecast = self._process_daily_forecast(forecast_data)
                        _LOGGER.debug("Daily forecast processed: %s", self._daily_forecast)

                        self._twice_daily_forecast = self._process_twice_daily_forecast(forecast_data)
                        _LOGGER.debug("Twice daily forecast processed: %s", self._twice_daily_forecast)
                    else:
                        _LOGGER.warning("Failed to fetch forecast data. HTTP Status: %s", response.status)
        except Exception as e:
            _LOGGER.error("Error fetching forecast data for location %s: %s", self._location, e, exc_info=True)


    def _process_hourly_forecast(self, forecast_data):
        """Process the hourly forecast data."""
        hourly_forecasts = []

        
        for day in forecast_data["forecast3h"]["features"][0]["properties"]["days"]:
            
            for entry in day["timeline"]:
                forecast_time = datetime.strptime(entry["valid"], "%Y-%m-%dT%H:%M:%S%z")

                
                precipitation = float(entry.get("tp_acc", 0))
                temperature = float(entry.get("t", 0))
                wind_speed = float(entry.get("ff_val", 0))
                wind_bearing = WIND_DIRECTION_MAP.get(entry.get("dd_shortText", ""), "")

                
                clouds_icon = entry.get("clouds_icon_wwsyn_icon", "").lower()
                condition = CLOUD_CONDITION_MAP.get(clouds_icon, "unknown")

                
                hourly_forecasts.append({
                    "datetime": forecast_time,
                    "temperature": temperature,
                    "precipitation": precipitation,
                    "wind_speed": wind_speed,
                    "wind_bearing": wind_bearing,
                    "condition": condition,
                    "pressure": float(entry.get("msl", 0)),
                })

        _LOGGER.debug("Processed Hourly Forecasts: %s", hourly_forecasts)
        return hourly_forecasts


    def _process_daily_forecast(self, forecast_data):
        """Process the daily forecast data."""
        daily_forecasts = []

        
        for day in forecast_data["forecast24h"]["features"][0]["properties"]["days"]:
            #
            forecast_time = day["date"]

            
            precipitation = float(day["timeline"][0].get("tp_24h_acc", 0))

            
            min_temp = float(day["timeline"][0].get("tnsyn", None))
            max_temp = float(day["timeline"][0].get("txsyn", None))

            
            wind_speed = float(day["timeline"][0].get("ff_val", 0))
            wind_bearing = WIND_DIRECTION_MAP.get(day["timeline"][0].get("dd_shortText", ""), "")
            condition = day["timeline"][0].get("clouds_icon_wwsyn_icon", "").lower()
            condition_translated = CLOUD_CONDITION_MAP.get(condition, "unknown")

            
            daily_forecasts.append({
                "datetime": forecast_time,
                "temperature": max_temp,
                "templow": min_temp,
                "precipitation": precipitation,
                "wind_speed": wind_speed,
                "wind_bearing": wind_bearing,
                "condition": condition_translated,
                "pressure": float(day["timeline"][0].get("msl", 0)),
            })

        _LOGGER.debug("Processed Daily Forecasts: %s", daily_forecasts)
        return daily_forecasts[:11]  # Return 11 days
        
    def _process_twice_daily_forecast(self, forecast_data):
        """Extract twice daily forecast using 3-hourly and 24-hourly data."""
        _LOGGER.debug("Starting twice daily forecast processing...")
        twice_daily_forecasts = []

        try:
            now = datetime.now(tz=pytz.UTC)
            max_forecast_date = (now + timedelta(days=5)).date()
            _LOGGER.debug("Maximum forecast date calculated: %s", max_forecast_date)

            # Process 3-hourly forecasts
            forecast3h = forecast_data.get("forecast3h", {}).get("features", [])
            if forecast3h:
                _LOGGER.debug("Processing 3-hourly forecast data.")
                days = forecast3h[0].get("properties", {}).get("days", [])
                for day in days:
                    _LOGGER.debug("Processing day: %s", day)
                    day_date = datetime.strptime(day["date"], "%Y-%m-%d").date()

                    if day_date > max_forecast_date:
                        _LOGGER.debug("Skipping day %s as it is beyond the maximum forecast range.", day_date)
                        continue

                    timeline = day.get("timeline", [])
                    _LOGGER.debug("Timeline for day %s: %s", day_date, timeline)

                    morning_entry = next((entry for entry in timeline if "T06:00:00" in entry["valid"]), None)
                    if morning_entry:
                        _LOGGER.debug("Morning entry found: %s", morning_entry)
                        twice_daily_forecasts.append({
                            "datetime": datetime.strptime(morning_entry["valid"], "%Y-%m-%dT%H:%M:%S%z"),
                            "temperature": float(morning_entry.get("t", 0)),
                            "condition": CLOUD_CONDITION_MAP.get(morning_entry.get("clouds_icon_wwsyn_icon", "").lower(), "unknown"),
                        })

                    evening_entry = next((entry for entry in timeline if "T18:00:00" in entry["valid"]), None)
                    if evening_entry:
                        _LOGGER.debug("Evening entry found: %s", evening_entry)
                        twice_daily_forecasts.append({
                            "datetime": datetime.strptime(evening_entry["valid"], "%Y-%m-%dT%H:%M:%S%z"),
                            "temperature": float(evening_entry.get("t", 0)),
                            "condition": CLOUD_CONDITION_MAP.get(evening_entry.get("clouds_icon_wwsyn_icon", "").lower(), "unknown"),
                        })

            # Process 24-hourly forecasts
            forecast24h = forecast_data.get("forecast24h", {}).get("features", [])
            if forecast24h:
                _LOGGER.debug("Processing 24-hourly forecast data.")
                days = forecast24h[0].get("properties", {}).get("days", [])
                for day in days:
                    _LOGGER.debug("Processing day: %s", day)
                    day_date = datetime.strptime(day["date"], "%Y-%m-%d").date()

                    if day_date > max_forecast_date:
                        _LOGGER.debug("Skipping day %s as it is beyond the maximum forecast range.", day_date)
                        continue

                    morning_temp = day["timeline"][0].get("tnsyn")
                    evening_temp = day["timeline"][0].get("txsyn")

                    if morning_temp is not None:
                        twice_daily_forecasts.append({
                            "datetime": datetime.combine(day_date, datetime.min.time(), tzinfo=pytz.UTC).replace(hour=6),
                            "temperature": float(morning_temp),
                            "condition": CLOUD_CONDITION_MAP.get(day["timeline"][0].get("clouds_icon_wwsyn_icon", "").lower(), "unknown"),
                        })

                    if evening_temp is not None:
                        twice_daily_forecasts.append({
                            "datetime": datetime.combine(day_date, datetime.min.time(), tzinfo=pytz.UTC).replace(hour=18),
                            "temperature": float(evening_temp),
                            "condition": CLOUD_CONDITION_MAP.get(day["timeline"][0].get("clouds_icon_wwsyn_icon", "").lower(), "unknown"),
                        })

        except Exception as e:
            _LOGGER.error("Error processing twice daily forecast: %s", e, exc_info=True)

        _LOGGER.debug("Completed twice daily forecast processing: %s", twice_daily_forecasts)
        return twice_daily_forecasts



    async def async_forecast_hourly(self):
        """Return the hourly forecast."""
        return self._hourly_forecast

    async def async_forecast_daily(self):
        """Return the daily forecast."""
        return self._daily_forecast
        
    async def async_forecast_twice_daily(self):
        """Return the twice daily forecast."""
        _LOGGER.debug("Returning twice daily forecast: %s", self._twice_daily_forecast)
        return self._twice_daily_forecast


    def _map_condition(self, clouds_short_text):
        """Map ARSO cloud conditions to Home Assistant weather conditions."""
        return CLOUD_CONDITION_MAP.get(clouds_short_text.lower(), "unknown")

    async def _fetch_rss_feed(self, url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 404:
                    _LOGGER.error(f"RSS feed not found for URL: {url}")
                    return None
                response.raise_for_status()
                return await response.text()

    def _extract_weather_details(self, entry):
        details = {}

        patterns = {
            'native_dew_point': r'Temperatura rosišča:\s*(-?\d+\.?\d*)\s*°C',
            'native_visibility': r'Vidnost:\s*(\d+\.?\d*)\s*km',
        }

        combined_text = f"{entry.title} {entry.summary}"

        for key, pattern in patterns.items():
            match = re.search(pattern, combined_text)
            if match:
                details[key] = match.group(1)

        return details