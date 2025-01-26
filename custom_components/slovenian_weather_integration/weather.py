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
from homeassistant.util.dt import as_local

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
    "overcast_modtssn_night": "lightning",
    "overcast_modtssn_day": "lightning",

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
            "native_wind_gust_speed": self._attr_native_wind_gust_speed,  # Dodano
        }
        if self._attr_native_dew_point is not None:
            attrs["dew_point"] = self._attr_native_dew_point
        if self._attr_native_visibility is not None:
            attrs["visibility"] = self._attr_native_visibility
        return attrs

    @property
    def device_info(self):
        """Return device information to group all related entities under one device."""
        return {
            "identifiers": {(DOMAIN, self._location)},
            "name": f"ARSO Weather Station - {self._location.capitalize()}",
            "manufacturer": "ARSO",
            "model": "Weather Station",
            "entry_type": "service",
        }



    async def async_update(self):
        """Fetch new state data for the sensor and update the forecast."""
        _LOGGER.debug("Starting update for ARSO Weather: %s", self._location)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://vreme.arso.gov.si/api/1.0/location/?location={self._location}") as response:
                    if response.status == 200:
                        data = await response.json()
                        _LOGGER.debug("Data: %s", data)

                        # Pridobi prvo napoved iz forecast1h
                        forecast1h = data.get("forecast1h", {}).get("features", [])
                        if forecast1h:
                            first_entry = forecast1h[0].get("properties", {}).get("days", [])[0]["timeline"][0]

                            self._attr_native_temperature = float(first_entry.get("t", 0))
                            self._attr_humidity = float(first_entry.get("rh", 0))
                            self._attr_native_pressure = float(first_entry.get("msl", 0))
                            self._attr_native_wind_speed = float(first_entry.get("ff_val", 0))
                            self._attr_native_wind_gust_speed = float(first_entry.get("ffmax_val", 0) or 0)
                            self._attr_wind_bearing = WIND_DIRECTION_MAP.get(first_entry.get("dd_shortText", ""), "")

                            condition = first_entry.get("clouds_icon_wwsyn_icon", "").lower()
                            self._attr_condition = CLOUD_CONDITION_MAP.get(condition, "unknown")

                            _LOGGER.debug(
                                "Updated current state from forecast1h - Temperature: %s, Condition: %s, Wind Gust Speed: %s",
                                self._attr_native_temperature,
                                self._attr_condition,
                                self._attr_native_wind_gust_speed,
                            )
                        else:
                            _LOGGER.warning("No forecast1h data available.")

                        await self._fetch_forecasts()
                    else:
                        _LOGGER.warning("Failed to fetch weather data. HTTP Status: %s", response.status)
        except Exception as e:
            _LOGGER.error("Unhandled error during update for %s: %s", self._location, e, exc_info=True)


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

        # Pridobi 1-urno napoved
        forecast1h = forecast_data.get("forecast1h", {}).get("features", [])
        if forecast1h:
            for day in forecast1h[0].get("properties", {}).get("days", []):
                for entry in day.get("timeline", []):
                    forecast_time = as_local(datetime.fromisoformat(entry["valid"]).astimezone(pytz.UTC))
                    if (forecast_time - datetime.now(pytz.UTC)).total_seconds() <= 24 * 3600:
                        # Dodano logiranje za 1-urno napoved
                        _LOGGER.debug("1h Forecast - UTC time: %s, Local time: %s, Temperature: %s", 
                                    entry["valid"], forecast_time, entry.get("t"))

                        hourly_forecasts.append({
                            "datetime": forecast_time.isoformat(),
                            "temperature": float(entry.get("t", 0)),
                            "condition": CLOUD_CONDITION_MAP.get(entry.get("clouds_icon_wwsyn_icon", "").lower(), "unknown"),
                            "native_wind_speed": float(entry.get("ff_val", 0)),
                            "native_wind_gust_speed": float(entry.get("ffmax_val", 0) or 0),
                            "wind_bearing": WIND_DIRECTION_MAP.get(entry.get("dd_shortText", ""), ""),
                        })

        # Pridobi 3-urno napoved za preostale ure
        forecast3h = forecast_data.get("forecast3h", {}).get("features", [])
        if forecast3h:
            for day in forecast3h[0].get("properties", {}).get("days", []):
                for entry in day.get("timeline", []):
                    forecast_time = datetime.fromisoformat(entry["valid"]).astimezone(pytz.UTC)
                    if (forecast_time - datetime.now(pytz.UTC)).total_seconds() > 24 * 3600:
                        # Dodano logiranje za 3-urno napoved
                        _LOGGER.debug("3h Forecast - UTC time: %s, Temperature: %s", 
                                    entry["valid"], entry.get("t"))

                        hourly_forecasts.append({
                            "datetime": forecast_time.isoformat(),
                            "temperature": float(entry.get("t", 0)),
                            "condition": CLOUD_CONDITION_MAP.get(entry.get("clouds_icon_wwsyn_icon", "").lower(), "unknown"),
                            "native_wind_speed": float(entry.get("ff_val", 0)),
                            "native_wind_gust_speed": float(entry.get("ffmax_val", 0) or 0),
                            "wind_bearing": WIND_DIRECTION_MAP.get(entry.get("dd_shortText", ""), ""),
                        })

        _LOGGER.debug("Processed Hourly Forecasts (1h + 3h): %s", hourly_forecasts)
        return hourly_forecasts



    def _process_daily_forecast(self, forecast_data):
        """Process the daily forecast data."""
        daily_forecasts = []

        for day in forecast_data["forecast24h"]["features"][0]["properties"]["days"]:
            try:
                # Datum napovedi
                forecast_time = day["date"]

                # Padavine
                precipitation = float(day["timeline"][0].get("tp_24h_acc", 0))

                # Temperature
                min_temp = float(day["timeline"][0].get("tnsyn", 0))
                max_temp = float(day["timeline"][0].get("txsyn", 0))

                # Veter
                wind_speed = float(day["timeline"][0].get("ff_val", 0))
                wind_bearing = WIND_DIRECTION_MAP.get(day["timeline"][0].get("dd_shortText", ""), "")

                # Sunki vetra
                gust_speed_raw = day["timeline"][0].get("ffmax_val", 0)
                gust_speed = float(gust_speed_raw) if gust_speed_raw and gust_speed_raw.strip() != "" else 0

                # Stanje vremena
                condition = day["timeline"][0].get("clouds_icon_wwsyn_icon", "").lower()
                condition_translated = CLOUD_CONDITION_MAP.get(condition, "unknown")

                # Dodaj v napoved
                daily_forecasts.append({
                    "datetime": forecast_time,
                    "temperature": max_temp,
                    "templow": min_temp,
                    "precipitation": precipitation,
                    "wind_speed": wind_speed,
                    "native_wind_gust_speed": gust_speed,
                    "wind_bearing": wind_bearing,
                    "condition": condition_translated,
                    "pressure": float(day["timeline"][0].get("msl", 0)),
                })

            except Exception as e:
                _LOGGER.error("Error processing daily forecast for day %s: %s", day, e, exc_info=True)

        _LOGGER.debug("Processed Daily Forecasts: %s", daily_forecasts)
        return daily_forecasts[:11]  # Vrni največ 11 dni


        
    def _process_twice_daily_forecast(self, forecast_data):
        """Extract twice daily forecast with templow, temperature, and wind gust speed."""
        _LOGGER.debug("Starting twice daily forecast processing...")
        twice_daily_forecasts = []

        now = datetime.now(tz=pytz.UTC)
        max_forecast_date = (now + timedelta(days=5)).date()

        forecast3h = forecast_data.get("forecast3h", {}).get("features", [])
        if forecast3h:
            _LOGGER.debug("Processing 3-hourly forecast data.")
            days = forecast3h[0].get("properties", {}).get("days", [])
            for day in days:
                day_date = datetime.strptime(day["date"], "%Y-%m-%d").date()
                if day_date > max_forecast_date:
                    continue

                timeline = day.get("timeline", [])

                # Jutranja napoved (6:00–12:00)
                morning_entries = [
                    entry for entry in timeline
                    if datetime.fromisoformat(entry["valid"]).hour in range(6, 12)
                ]
                if morning_entries:
                    morning_templow = min(float(entry.get("t", 0)) for entry in morning_entries)
                    morning_temperature = max(float(entry.get("t", 0)) for entry in morning_entries)
                    morning_gust_speed = max(float(entry.get("ffmax_val", 0) or 0) for entry in morning_entries)
                    morning_time = datetime.combine(day_date, datetime.min.time(), tzinfo=pytz.UTC).replace(hour=6)
                    twice_daily_forecasts.append({
                        "datetime": morning_time,
                        "templow": morning_templow,
                        "temperature": morning_temperature,
                        "native_wind_gust_speed": morning_gust_speed,
                        "condition": CLOUD_CONDITION_MAP.get(morning_entries[0].get("clouds_icon_wwsyn_icon", "").lower(), "unknown"),
                        "is_daytime": True,  # Zjutraj je vedno dnevno obdobje
                    })

                # Večerna napoved (12:00–18:00)
                evening_entries = [
                    entry for entry in timeline
                    if datetime.fromisoformat(entry["valid"]).hour in range(12, 18)
                ]
                if evening_entries:
                    evening_templow = min(float(entry.get("t", 0)) for entry in evening_entries)
                    evening_temperature = max(float(entry.get("t", 0)) for entry in evening_entries)
                    evening_gust_speed = max(float(entry.get("ffmax_val", 0) or 0) for entry in evening_entries)
                    evening_time = datetime.combine(day_date, datetime.min.time(), tzinfo=pytz.UTC).replace(hour=18)
                    twice_daily_forecasts.append({
                        "datetime": evening_time,
                        "templow": evening_templow,
                        "temperature": evening_temperature,
                        "native_wind_gust_speed": evening_gust_speed,
                        "condition": CLOUD_CONDITION_MAP.get(evening_entries[-1].get("clouds_icon_wwsyn_icon", "").lower(), "unknown"),
                        "is_daytime": False,  # Zvečer je vedno nočno obdobje
                    })

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
