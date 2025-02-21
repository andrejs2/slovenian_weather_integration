import aiohttp
import logging
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# URL-ji za pridobivanje podatkov
ARSO_POLLEN_URL = "https://meteo.arso.gov.si/uploads/probase/www/agromet/json/sl/feno/objlist.json"
ARSO_POLLEN_FORECAST_URL = "https://meteo.arso.gov.si/uploads/probase/www/fproduct/json/sl/fcast_bio_si_d1_text.json"

async def fetch_pollen_data():
    """Fetch current pollen data from ARSO."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(ARSO_POLLEN_URL) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to fetch ARSO pollen data. HTTP status: %s", response.status)
                    return None
                data = await response.json()

                if not isinstance(data, list):
                    _LOGGER.warning("Pollen data format is incorrect!")
                    return None

                return data
        except Exception as e:
            _LOGGER.error("Error processing ARSO pollen data: %s", e)
            return None

async def fetch_pollen_forecast():
    """Fetch pollen forecast from ARSO."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(ARSO_POLLEN_FORECAST_URL) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to fetch ARSO pollen forecast. HTTP status: %s", response.status)
                    return None
                data = await response.json()

                if "articleinfo" not in data or "section" not in data:
                    _LOGGER.warning("Pollen forecast data format is incorrect!")
                    return None

                return data
        except Exception as e:
            _LOGGER.error("Error processing ARSO pollen forecast data: %s", e)
            return None
