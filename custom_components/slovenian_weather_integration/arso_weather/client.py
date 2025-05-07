import aiohttp
import logging
from typing import Optional, Literal, Type, Any, cast, Dict # Added Dict
from pydantic import BaseModel, ValidationError
from datetime import datetime, date, timezone, timedelta 
from bs4 import BeautifulSoup 

from .models import (
    ObservationDetails,
    ObservationTimelineEntry,
    Forecast1hTimelineEntry, 
    Forecast3hTimelineEntry, 
    Forecast24hTimelineEntry, 
    UVForecastDataPoint,      
    merge_observation_data,
    MODEL_MAPPING,
)
from .station_map import OBSERVATION_STATIONS

_LOGGER = logging.getLogger(__name__)

PRIMARY_STATION_BASE_URL = "https://meteo.arso.gov.si/uploads/probase/www/observ/surface/json/sl//recent/observationAms_METEO-{location_id}_history.json"
OFFICIAL_ARSO_API_URL = "https://vreme.arso.gov.si/api/1.0/location/?location={location_id}" # Used for forecasts and basic observation
LOCATIONS_URL = "https://vreme.arso.gov.si/uploads/probase/www/fproduct/json/sl/locations.json" # Source for location coordinates

BASE_UV_URL = "https://www.temis.nl/uvradiation/nrt/uvindex.php"
TEMIS_REQUEST_TIMEOUT = 30 

class ArsoWeather:
    """Client to fetch weather data from ARSO and UV index from Temis.nl."""

    def __init__(
        self,
        location_name: str,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        location_id = OBSERVATION_STATIONS.get(location_name)

        self.location_name = location_name
        self.location_id = location_id 
        self._current_arso_official_data: Optional[Dict[str, Any]] = None 
        self._coordinates: Optional[tuple[float, float]] = None 
        self._all_locations_data: Optional[Dict[str, Any]] = None # Cache for LOCATIONS_URL data

        if session is None:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        else:
            self._session = session
            self._owns_session = False

        _LOGGER.debug(f"Initialized ArsoWeather for location '{location_name}' (ID: {location_id})")

    async def _fetch_json_data(self, api_url: str, log_msg_on_fail: str) -> Dict[str, Any]: # Return type Dict
        _LOGGER.debug(f"Requesting data from {api_url}")
        try:
            # Uporaba obstoječe seje self._session
            async with self._session.get(api_url, timeout=20) as response: 
                response.raise_for_status() # Sproži napako za slabe HTTP statuse (4xx, 5xx)
                # ARSO včasih vrne JSON z content_type 'text/plain', zato content_type=None
                data: Dict[str, Any] = await response.json(content_type=None)
                _LOGGER.debug(f"Successfully received API response from {api_url}.")
                return data
        except aiohttp.ClientResponseError as e:
            _LOGGER.error(f"{log_msg_on_fail}: HTTP {e.status} {e.message} from {api_url}")
        except aiohttp.ClientError as e: # Vključuje TimeoutError in druge napake povezave
            _LOGGER.error(f"{log_msg_on_fail}: Client error for {api_url}: {e}")
        except Exception as e: # Ujame morebitne druge nepričakovane napake (npr. pri parsiranju JSON)
            _LOGGER.error(f"{log_msg_on_fail}: Unexpected error for {api_url}: {e}", exc_info=True)
        return {} # V primeru napake vrne prazen slovar

    async def get_all_locations(self) -> list[str]:
        """Fetches all available location names from ARSO LOCATIONS_URL."""
        # Zagotovi, da so podatki o vseh lokacijah pridobljeni, če še niso predpomnjeni
        if self._all_locations_data is None:
            self._all_locations_data = await self._fetch_json_data(LOCATIONS_URL, "Failed to fetch ARSO locations list for get_all_locations")

        if not self._all_locations_data or "features" not in self._all_locations_data:
            return [] # Vrne prazen seznam, če ni podatkov ali pričakovane strukture
        
        location_names = []
        for loc_feature in self._all_locations_data.get("features", []):
            # Robustno preverjanje strukture pred dostopom do elementov
            if isinstance(loc_feature, dict) and \
               isinstance(loc_feature.get("properties"), dict) and \
               isinstance(loc_feature["properties"].get("title"), str):
                location_names.append(loc_feature["properties"]["title"])
        return sorted(location_names) # Vrne sortiran seznam imen lokacij

    async def _get_and_store_location_coordinates(self) -> bool:
        """
        Tries to get coordinates for self.location_name.
        Priority:
        1. From cached self._coordinates.
        2. From self._all_locations_data (fetched from LOCATIONS_URL).
        3. Fallback: From self._current_arso_official_data (less reliable for coords).
        """
        if self._coordinates: 
            _LOGGER.debug(f"Using cached coordinates for {self.location_name}: {self._coordinates}")
            return True

        # Poskusi pridobiti iz podatkov LOCATIONS_URL (bolj zanesljivo za koordinate)
        if self._all_locations_data is None:
            _LOGGER.debug(f"Fetching all locations data to find coordinates for {self.location_name}")
            self._all_locations_data = await self._fetch_json_data(LOCATIONS_URL, f"Failed to fetch ARSO locations list for coordinates of {self.location_name}")

        if self._all_locations_data and "features" in self._all_locations_data:
            for feature in self._all_locations_data.get("features", []):
                try:
                    props = feature.get("properties", {})
                    title = props.get("title", "")
                    if title.lower() == self.location_name.lower(): # Primerjava neodvisna od velikosti črk
                        geometry = feature.get("geometry", {})
                        coords_raw = geometry.get("coordinates", []) # ARSO: [lon, lat]
                        if isinstance(coords_raw, list) and len(coords_raw) >= 2:
                            lon, lat = float(coords_raw[0]), float(coords_raw[1])
                            self._coordinates = (lat, lon) # Shranimo kot (lat, lon)
                            _LOGGER.info(f"Successfully extracted coordinates for {self.location_name} from LOCATIONS_URL: Lat={lat}, Lon={lon}")
                            return True
                except (ValueError, TypeError, KeyError) as e: # Ujame napake pri pretvorbi ali manjkajočih ključih
                    _LOGGER.warning(f"Error processing feature in LOCATIONS_URL for {self.location_name}: {feature}, Error: {e}")
            _LOGGER.warning(f"Location '{self.location_name}' not found or no coordinates in LOCATIONS_URL data.")
        else:
            _LOGGER.warning(f"Could not fetch or parse LOCATIONS_URL data to find coordinates for {self.location_name}.")


        # Fallback: Poskusi pridobiti iz _current_arso_official_data (OFFICIAL_ARSO_API_URL)
        _LOGGER.debug(f"Falling back to extract coordinates from OFFICIAL_ARSO_API_URL data for {self.location_name}.")
        if not self._current_arso_official_data: # Preveri, ali so ti podatki sploh na voljo
            _LOGGER.warning(f"Cannot get coordinates for {self.location_name} from OFFICIAL_ARSO_API_URL, data not fetched yet or empty.")
            return False
        
        _LOGGER.debug(f"Attempting to extract coordinates from OFFICIAL_ARSO_API_URL data for {self.location_name}. Data received (keys): {list(self._current_arso_official_data.keys())}")
        try:
            # Robustno preverjanje poti do koordinat
            meta_data = self._current_arso_official_data.get("meta")
            if not meta_data or not isinstance(meta_data, dict):
                _LOGGER.warning(f"'meta' key missing or not a dictionary in ARSO official data (fallback) for {self.location_name}.")
                return False

            location_info = meta_data.get("location")
            if not location_info or not isinstance(location_info, dict):
                _LOGGER.warning(f"'meta.location' key missing or not a dictionary (fallback) for {self.location_name}.")
                return False
            
            geometry_info = location_info.get("geometry")
            if not geometry_info or not isinstance(geometry_info, dict):
                _LOGGER.warning(f"'meta.location.geometry' key missing or not a dictionary (fallback) for {self.location_name}.")
                return False

            coords_raw = geometry_info.get("coordinates") # ARSO: [lon, lat]
            if not isinstance(coords_raw, list) or len(coords_raw) < 2:
                _LOGGER.warning(f"'meta.location.geometry.coordinates' missing or invalid (fallback) for {self.location_name}.")
                return False

            lon, lat = float(coords_raw[0]), float(coords_raw[1])
            self._coordinates = (lat, lon) # Shranimo kot (lat, lon)
            _LOGGER.info(f"Successfully extracted coordinates for {self.location_name} from OFFICIAL_ARSO_API_URL (fallback): Lat={lat}, Lon={lon}")
            return True
            
        except (ValueError, TypeError) as e:
            _LOGGER.error(f"Invalid data type in OFFICIAL_ARSO_API_URL (fallback) for {self.location_name}: {e}", exc_info=True)
        except Exception as e: # Ujame morebitne druge nepričakovane napake
            _LOGGER.error(f"Generic exception in OFFICIAL_ARSO_API_URL (fallback) for {self.location_name}: {e}", exc_info=True)
        
        _LOGGER.error(f"Failed to obtain coordinates for {self.location_name} from all available sources.")
        self._coordinates = None 
        return False

    async def _get_current_uv_index_from_temis(self) -> Optional[float]:
        """Fetches the current UV index from Temis.nl."""
        if not self._coordinates: # Če koordinate še niso pridobljene
            if not await self._get_and_store_location_coordinates(): # Poskusi jih pridobiti
                _LOGGER.error("Cannot fetch UV index without location coordinates for %s.", self.location_name)
                return None
        
        if not self._coordinates: # Še enkrat preveri, če so zdaj na voljo
             _LOGGER.error("Coordinates still not available after attempting to fetch for %s (UV current).", self.location_name)
             return None

        lat, lon = self._coordinates # Zdaj bi morale biti na voljo
        url = f"{BASE_UV_URL}?lon={lon}&lat={lat}"
        headers = {"User-Agent": "Mozilla/5.0 (HomeAssistant Custom Integration)"}

        _LOGGER.debug(f"Fetching current UV index from Temis: {url}")
        try:
            async with self._session.get(url, headers=headers, timeout=TEMIS_REQUEST_TIMEOUT) as response:
                response.raise_for_status()
                text = await response.text()
                soup = BeautifulSoup(text, "html.parser")
                
                tables = soup.find_all("table")
                if not tables:
                    _LOGGER.warning(f"No tables found in Temis.nl UV index page for {self.location_name}.")
                    return None
                for table in tables:
                    rows = table.find_all("tr")
                    for row in rows:
                        cols = row.find_all("td")
                        if len(cols) >= 2:
                            uv_str = cols[1].get_text(strip=True)
                            try:
                                uv_value = float(uv_str)
                                _LOGGER.debug(f"Found current UV index from Temis for {self.location_name}: {uv_value}")
                                return uv_value
                            except ValueError:
                                # To je lahko vrstica z opisom, nadaljuj z iskanjem
                                continue 
                _LOGGER.warning(f"No valid current UV index found in Temis.nl page for {self.location_name}.")
                return None
        except aiohttp.ClientError as e: 
            _LOGGER.error(f"Network error fetching current UV index from Temis for {self.location_name}: {e}")
        except Exception as e:
            _LOGGER.error(f"Exception parsing current UV index from Temis for {self.location_name}: {e}", exc_info=True)
        return None

    async def _get_daily_uv_forecast_raw_from_temis(self) -> list[Dict[str, Any]]:
        """
        Fetches the daily UV forecast from Temis.nl.
        Returns a list of dicts, e.g., [{'valid_time': datetime_obj, 'uv_index_forecast': float_val}, ...]
        """
        if not self._coordinates:
            if not await self._get_and_store_location_coordinates():
                _LOGGER.error("Cannot fetch UV forecast without location coordinates for %s.", self.location_name)
                return []
        
        if not self._coordinates: # Ponovno preverjanje
             _LOGGER.error("Coordinates still not available for UV forecast for %s.", self.location_name)
             return []

        lat, lon = self._coordinates
        url = f"{BASE_UV_URL}?lon={lon}&lat={lat}"
        headers = {"User-Agent": "Mozilla/5.0 (HomeAssistant Custom Integration)"}
        _LOGGER.debug(f"Fetching daily UV forecast from Temis: {url}")
        
        raw_forecast_entries: list[Dict[str, Any]] = []
        try:
            async with self._session.get(url, headers=headers, timeout=TEMIS_REQUEST_TIMEOUT) as response:
                response.raise_for_status()
                text = await response.text()
                soup = BeautifulSoup(text, "html.parser")
                tables = soup.find_all("table")
                if not tables:
                    _LOGGER.warning(f"No tables found in Temis.nl UV forecast page for {self.location_name}.")
                    return []

                parsed_forecast_points = []
                for table in tables:
                    rows = table.find_all("tr")
                    for row in rows:
                        cols = row.find_all("td")
                        if len(cols) < 2:
                            continue
                        
                        date_text = cols[0].get_text(strip=True)
                        uv_str = cols[1].get_text(strip=True)
                        
                        # Preskoči glave ali vrstice s trenutnim UV, ki vsebujejo "UTC"
                        if not date_text or "UTC" in date_text or not uv_str: 
                            continue

                        try:
                            # Poskusi parsirati "YYYY-MM-DD"
                            dt_object = datetime.strptime(date_text, "%Y-%m-%d")
                        except ValueError:
                            try:
                                # Poskusi parsirati "DD Mon YYYY" (npr., "11 Feb 2025")
                                dt_object = datetime.strptime(date_text, "%d %b %Y")
                            except ValueError:
                                _LOGGER.debug(f"Skipping Temis UV forecast row with unparseable date: {date_text}")
                                continue
                        
                        # Zagotovi, da je datetime objekt časovno ozaveščen (UTC)
                        dt_object = dt_object.replace(tzinfo=timezone.utc)

                        try:
                            uv_value = float(uv_str)
                            # Uporabi strukturo, ki jo pričakuje UVForecastDataPoint model
                            parsed_forecast_points.append({"valid_time": dt_object, "uv_index_forecast": uv_value})
                        except ValueError:
                            _LOGGER.debug(f"Skipping Temis UV forecast row with invalid UV index for date {date_text}: {uv_str}")
                            continue
                
                if not parsed_forecast_points:
                    _LOGGER.warning(f"No valid daily UV forecast entries found after parsing Temis page for {self.location_name}.")
                    return []

                # Deduplikacija in sortiranje
                seen_dates = set()
                deduplicated_and_sorted_forecast = []
                # Sortiraj pred deduplikacijo, da obdržiš prvega, če jih je več za isti dan
                parsed_forecast_points.sort(key=lambda x: x["valid_time"])

                for entry_dict in parsed_forecast_points:
                    forecast_date = entry_dict["valid_time"].date()
                    if forecast_date not in seen_dates:
                        seen_dates.add(forecast_date)
                        deduplicated_and_sorted_forecast.append(entry_dict)
                
                raw_forecast_entries = deduplicated_and_sorted_forecast
                _LOGGER.debug(f"Collected daily UV forecast from Temis for {self.location_name}: {len(raw_forecast_entries)} entries.")

        except aiohttp.ClientError as e:
            _LOGGER.error(f"Network error fetching daily UV forecast from Temis for {self.location_name}: {e}")
        except Exception as e:
            _LOGGER.error(f"Exception parsing daily UV forecast from Temis for {self.location_name}: {e}", exc_info=True)
        
        return raw_forecast_entries


    async def get_weather(self) -> Dict[str, list[Any]]: 
        """
        Fetches all weather data: ARSO observations, ARSO forecasts, and Temis.nl UV data.
        Merges them into Pydantic models.
        """
        _LOGGER.debug(f"Starting full weather update for {self.location_name}")
        
        # 1. Pridobi glavne ARSO podatke (napovedi in osnovna opazovanja)
        official_api_url = OFFICIAL_ARSO_API_URL.format(location_id=self.location_name)
        self._current_arso_official_data = await self._fetch_json_data(
            official_api_url, f"Failed to fetch official ARSO data for {self.location_name}"
        )
        # _current_arso_official_data je lahko {} če pridobivanje ni uspelo.

        # 2. Poskusi pridobiti in shraniti koordinate. 
        # Ta metoda bo poskusila najprej LOCATIONS_URL, nato fallback na _current_arso_official_data.
        await self._get_and_store_location_coordinates() 

        # Če osnovni ARSO podatki niso bili pridobljeni, ne moremo nadaljevati smiselno.
        if not self._current_arso_official_data:
            _LOGGER.error(f"Aborting weather update for {self.location_name} as main ARSO data is missing.")
            # Vrne prazno strukturo, da koordinator ne povzroči napake
            empty_data_keys = ["current", "forecast1h", "forecast3h", "forecast6h", "forecast24h"]
            return {key: [] for key in empty_data_keys}


        # 3. Razčleni uradne ARSO podatke v slovarje časovnih vrst
        parsed_official_data_dict: Dict[str, list[Dict[str, Any]]] = {}
        target_keys: list[Literal["observation", "forecast1h", "forecast3h", "forecast6h", "forecast24h"]] = [
            "observation", "forecast1h", "forecast3h", "forecast6h", "forecast24h"
        ]
        
        try:
            for data_type_key in target_keys:
                parsed_official_data_dict[data_type_key] = []
                # Robustno preverjanje strukture ARSO API odgovora
                data_type_content = self._current_arso_official_data.get(data_type_key)
                if isinstance(data_type_content, dict):
                    features = data_type_content.get("features")
                    if isinstance(features, list) and features: # Preveri, da seznam ni prazen
                        properties = features[0].get("properties")
                        if isinstance(properties, dict):
                            days_list = properties.get("days")
                            if isinstance(days_list, list):
                                for day_data in days_list:
                                    if isinstance(day_data, dict) and isinstance(day_data.get("timeline"), list):
                                        parsed_official_data_dict[data_type_key].extend(day_data["timeline"])
            _LOGGER.debug(f"Parsed official ARSO data keys for {self.location_name}: {list(parsed_official_data_dict.keys())}")
        except Exception as e:
            _LOGGER.error(f"Error parsing official ARSO data structure for {self.location_name}: {e}", exc_info=True)
            # Kljub napaki nadaljujemo, morda so nekateri deli podatkov še vedno OK.

        # 4. Pripravi trenutna opazovanja
        current_observation_dict: Optional[Dict[str, Any]] = None
        if parsed_official_data_dict.get("observation"):
            current_observation_dict = parsed_official_data_dict["observation"][0].copy() # Uporabi kopijo
            try:
                # Validiraj v ObservationTimelineEntry za zagotovitev osnovne strukture
                base_obs_model = ObservationTimelineEntry.model_validate(current_observation_dict)
                current_observation_dict = base_obs_model.model_dump(by_alias=False) # Nazaj v slovar za združevanje
            except ValidationError as e:
                _LOGGER.warning(f"Failed to validate base observation for {self.location_name}: {e}")
                current_observation_dict = {} # Fallback na prazen slovar
        else:
            _LOGGER.warning(f"No 'observation' data in parsed official ARSO data for {self.location_name}.")
            current_observation_dict = {} 

        # Če je to primarna postaja, pridobi podrobne podatke in jih združi
        if self.location_id: 
            primary_station_url = PRIMARY_STATION_BASE_URL.format(location_id=self.location_id)
            primary_station_raw_data = await self._fetch_json_data(
                primary_station_url, f"Failed to fetch primary station data for {self.location_name} (ID: {self.location_id})"
            )
            # Robustno preverjanje strukture podatkov primarne postaje
            if primary_station_raw_data:
                features = primary_station_raw_data.get("features")
                if isinstance(features, list) and features:
                    properties = features[0].get("properties")
                    if isinstance(properties, dict):
                        days = properties.get("days")
                        if isinstance(days, list) and days:
                            timeline = days[0].get("timeline")
                            if isinstance(timeline, list) and timeline:
                                detailed_obs_dict = timeline[0]
                                # Združi: začni z osnovnim slovarjem opazovanj, nato posodobi s podrobnim
                                temp_base_model = ObservationTimelineEntry.model_validate(current_observation_dict or {})
                                merged_obs_model = merge_observation_data(temp_base_model, detailed_obs_dict)
                                current_observation_dict = merged_obs_model.model_dump(by_alias=False)
                            else: _LOGGER.warning(f"Primary station data for {self.location_name} missing 'timeline'.")
                        else: _LOGGER.warning(f"Primary station data for {self.location_name} missing 'days' or not a list.")
                    else: _LOGGER.warning(f"Primary station data for {self.location_name} missing 'properties'.")
                else: _LOGGER.warning(f"Primary station data for {self.location_name} missing 'features'.")
            else: _LOGGER.warning(f"Could not fetch or parse detailed observation data for primary station {self.location_name}. Using basic observation only.")
        
        # 5. Pridobi in dodaj trenutni UV indeks v current_observation_dict
        current_uv = await self._get_current_uv_index_from_temis()
        if current_observation_dict is not None: # Zagotovi, da slovar obstaja
            current_observation_dict["current_uv_index"] = current_uv # To polje mora obstajati v ObservationDetails modelu
        elif current_uv is not None: # Če current_observation_dict ni obstajal, ga ustvari samo za UV
             current_observation_dict = {"current_uv_index": current_uv}


        # Validiraj končni current_observation_dict v ObservationDetails model
        final_current_observation_model: Optional[ObservationDetails] = None
        try:
            if current_observation_dict: # Zagotovi, da slovar ni prazen
                 final_current_observation_model = ObservationDetails.model_validate(current_observation_dict)
            else: 
                _LOGGER.warning(f"Current observation dictionary is empty for {self.location_name}, cannot create ObservationDetails model.")
        except ValidationError as e:
            _LOGGER.error(f"Validation failed for final ObservationDetails for {self.location_name}: {e}", exc_info=True)
            _LOGGER.debug(f"Data causing validation error for ObservationDetails: {current_observation_dict}")

        # 6. Obdelaj ARSO napovedi in jih združi z dnevno UV napovedjo iz Temis.nl
        final_forecasts_models: Dict[str, list[Any]] = {}

        # Pridobi surovo dnevno UV napoved iz Temis.nl (seznam slovarjev: {'valid_time': datetime, 'uv_index_forecast': float})
        temis_uv_daily_raw = await self._get_daily_uv_forecast_raw_from_temis()
        
        # Pretvori surove Temis podatke v UVForecastDataPoint modele za lažje iskanje
        temis_uv_forecast_map: Dict[date, UVForecastDataPoint] = {}
        if temis_uv_daily_raw:
            for uv_raw_item in temis_uv_daily_raw:
                try:
                    uv_dp_model = UVForecastDataPoint.model_validate(uv_raw_item)
                    temis_uv_forecast_map[uv_dp_model.valid_time.date()] = uv_dp_model # Uporabi .date() za ključ
                except ValidationError as e:
                    _LOGGER.warning(f"Failed to validate Temis UV data point {uv_raw_item}: {e}")

        for forecast_key, forecast_items_list_of_dicts in parsed_official_data_dict.items():
            if forecast_key == "observation": # Preskoči opazovanja, že obdelana
                continue

            model_class = MODEL_MAPPING.get(forecast_key)
            if not model_class or not forecast_items_list_of_dicts: # Če ni modela ali podatkov za ta tip napovedi
                _LOGGER.debug(f"No model or data for ARSO forecast type '{forecast_key}' for {self.location_name}.")
                final_forecasts_models[forecast_key] = []
                continue

            processed_forecast_list: list[Any] = [] # Seznam Pydantic modelov
            for item_dict in forecast_items_list_of_dicts:
                # Če je to 24-urna napoved, poskusi dodati UV indeks
                if forecast_key == "forecast24h":
                    item_dict["uv_index"] = None # Zagotovi, da ključ obstaja, tudi če ni vrednosti
                    try:
                        # ARSO 'valid' za 24h napoved je običajno samo datumski niz 'YYYY-MM-DD'
                        # ali poln datetime. Naš Pydantic model za Forecast24hTimelineEntry
                        # bi moral imeti validator za 'valid_time', ki to pravilno obdela.
                        # Tukaj potrebujemo samo datumski del za ujemanje z UV napovedjo.
                        valid_time_str = item_dict.get("valid")
                        if valid_time_str and isinstance(valid_time_str, str):
                            # Vzemi samo datumski del, če je prisoten čas
                            arso_forecast_date_str = valid_time_str.split('T')[0]
                            arso_forecast_date = datetime.strptime(arso_forecast_date_str, "%Y-%m-%d").date()
                            
                            matching_temis_uv_dp = temis_uv_forecast_map.get(arso_forecast_date)
                            if matching_temis_uv_dp and matching_temis_uv_dp.uv_index is not None: 
                                item_dict["uv_index"] = matching_temis_uv_dp.uv_index 
                        else:
                             _LOGGER.debug(f"Missing or invalid 'valid' time for ARSO 24h forecast item: {item_dict}")
                    except Exception as e: # Ujame napake pri parsiranju datuma ali druge težave
                        _LOGGER.warning(f"Error processing date for UV merge in forecast24h for {self.location_name}: {e}. Data: {item_dict.get('valid')}")
                try:
                    validated_model = model_class.model_validate(item_dict)
                    processed_forecast_list.append(validated_model)
                except ValidationError as e:
                    _LOGGER.warning(f"Validation failed for {model_class.__name__} with data {item_dict}: {e}")
            
            final_forecasts_models[forecast_key] = processed_forecast_list
            _LOGGER.debug(f"Processed {len(processed_forecast_list)} models for forecast type '{forecast_key}' for {self.location_name}.")

        # 7. Sestavi končni podatkovni paket
        result_data: Dict[str, list[Any]] = {}
        if final_current_observation_model:
            result_data["current"] = [final_current_observation_model]
        else:
            result_data["current"] = [] # Pomembno je, da ključ obstaja, tudi če je prazen

        result_data.update(final_forecasts_models) # Dodaj vse sezname napovedi

        _LOGGER.info(f"Weather update for {self.location_name} completed. Data keys: {list(result_data.keys())}")
        if not result_data.get("current"): # Preveri, če so trenutni podatki dejansko prisotni
             _LOGGER.warning(f"Current weather data is missing for {self.location_name} in the final package.")
        return result_data


    async def close(self):
        """Close the underlying aiohttp session if it was created internally."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
            _LOGGER.debug("Closed internally managed aiohttp session.")

    async def __aenter__(self):
        """Async context manager enter."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
