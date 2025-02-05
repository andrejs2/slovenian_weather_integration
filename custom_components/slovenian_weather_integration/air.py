import aiohttp
from datetime import datetime, timezone
import logging
import xml.etree.ElementTree as ET
from .helpers import normalize_location

_LOGGER = logging.getLogger(__name__)

# ARSO XML URL za zadnje urne podatke
ARSO_AIR_QUALITY_URL = "http://www.arso.gov.si/xml/zrak/ones_zrak_urni_podatki_zadnji.xml"

# Preslikava merilnih postaj na obstoječe Home Assistant lokacije
STATION_MAPPING = {
    "Ljubljana": ["LJ Bežigrad", "LJ Celovška", "LJ Vič"],
    "Maribor": ["MB Titova", "MB Vrbanski"],
    "Celje": ["CE bolnica", "CE Ljubljanska"],
    "Bilje pri Novi Gorici": ["NG Grčna"],
    "Koper": ["Koper"],
    "Kranj": ["Kranj"],
    "Novo mesto": ["Novo mesto"],
    "Murska Sobota": ["MS Cankarjeva", "MS Rakičan"],
    "Ptuj": ["Ptuj"],
    "Trbovlje": ["Trbovlje"],
    "Zagorje": ["Zagorje"],
    "Hrastnik": ["Hrastnik"],
    "Črnomelj": ["Črnomelj"],
}

POLLUTANTS = ["pm10", "pm2.5", "so2", "co", "o3", "no2", "benzen"]


async def fetch_air_quality_data():
    """Asinhrono pridobi podatke o kakovosti zraka iz ARSO XML."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(ARSO_AIR_QUALITY_URL) as response:
                if response.status != 200:
                    _LOGGER.error("❌ Napaka pri pridobivanju ARSO API! HTTP status: %s", response.status)
                    return None

                content = await response.text()
                root = ET.fromstring(content)
                air_quality_data = {}

                # Skladiščimo podatke za več postaj na isti lokaciji
                temp_values = {normalize_location(loc): {poll: [] for poll in POLLUTANTS} for loc in STATION_MAPPING.keys()}

                for postaja in root.findall("postaja"):
                    ime = postaja.find("merilno_mesto").text.strip()

                    for ha_location, arso_locations in STATION_MAPPING.items():
                        if ime in arso_locations:
                            ha_location_normalized = normalize_location(ha_location)

                            for pollutant in POLLUTANTS:
                                value = postaja.find(pollutant).text if postaja.find(pollutant) is not None else None
                                if value is not None:
                                    try:
                                        value = float(value)
                                        temp_values[ha_location_normalized][pollutant].append(value)
                                    except ValueError:
                                        _LOGGER.warning("⚠️ Neveljavna vrednost %s za %s: %s", pollutant, ime, value)

                # Izračunamo povprečje za kraje z več postajami
                for location, pollutants in temp_values.items():
                    air_quality_data[location] = {}
                    for pollutant, values in pollutants.items():
                        if values:
                            air_quality_data[location][pollutant] = round(sum(values) / len(values), 1)
                            _LOGGER.info("✅ Povprečna vrednost %s za %s: %s", pollutant, location, air_quality_data[location][pollutant])
                        else:
                            air_quality_data[location][pollutant] = None
                            _LOGGER.warning("⚠️ Ni podatkov o %s za %s", pollutant, location)

                _LOGGER.debug("📊 Final air quality data: %s", air_quality_data)
                return air_quality_data

        except Exception as e:
            _LOGGER.error("❌ Napaka pri obdelavi ARSO podatkov: %s", e, exc_info=True)
            return None


if __name__ == "__main__":
    import asyncio

    async def test_fetch_air_quality():
        data = await fetch_air_quality_data()
        print("📊 Pridobljeni podatki o kakovosti zraka:", data)

    asyncio.run(test_fetch_air_quality())
