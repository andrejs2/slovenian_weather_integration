      
"""Ta datoteka je namenjena pridobivanju podatkov o sončnem obsevanju in snežni odeji."""

import aiohttp
import asyncio
from bs4 import BeautifulSoup
import logging

_LOGGER = logging.getLogger(__name__)

ARSO_SOLAR_URL = "https://meteo.arso.gov.si/uploads/probase/www/observ/surface/text/sl/observationAms_si_latest.html"
USER_AGENT = "HomeAssistant ARSO Weather Integration"

async def fetch_sun_snow_data():
    """Pridobi podatke o sončnem obsevanju in snežni odeji s spletne strani ARSO."""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {'User-Agent': USER_AGENT}
            async with session.get(ARSO_SOLAR_URL, headers=headers) as response:
                if response.status != 200:
                    _LOGGER.error(f"Napaka pri pridobivanju podatkov: {response.status}")
                    return None
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                tables = soup.find_all('table', {'class': 'meteoSI-table'})  # Poišče vse tabele

                if not tables:
                    _LOGGER.error("Nobena tabela s podatki ni najdena.")
                    return None

                all_data = {}
                for table in tables: # Iteriramo po vseh tabelah
                    header = [th.text.strip() for th in table.find_all('th')]
                    # Ročno dodamo "Ocenjena oblačnost" v header, ker nima th elementa
                    header.insert(1, "Ocenjena oblačnost") #Dodamo na drugo mesto (indeks 1)
                    from custom_components.slovenian_weather_integration.helpers import normalize_location #dodajamo lokalni import
                    for row in table.find_all('tr')[1:]: # preskočimo header row
                        cells = row.find_all('td')
                        if cells:
                            station_name = cells[0].text.strip() #Ime postaje
                            station_name_normalized = normalize_location(station_name) #normaliziramo ime postaje
                            station_data = {}
                            # Preveri, ali je število celic enako številu stolpcev
                            if len(cells) >= len(header) - 1:
                                # Ročno dodamo "Ocenjena oblačnost", ker nima ustreznega th elementa
                                station_data["Ocenjena oblačnost"] = cells[1].text.strip()

                                sun_radiation = None
                                snow_height = None

                                for i, cell in enumerate(cells[1:], start=1): #Začnemo z indeksom 1, ker smo že obdelali ime postaje
                                    header_text = header[i+1].strip()
                                    if header_text == "Sončno obsevanje [W/m2]":
                                        sun_radiation = cell.text.strip()
                                    elif header_text == "Višina snežne odeje [cm]":
                                        snow_height = cell.text.strip()

                                # Create station data dictionary
                                station_data_dict = {}
                                if sun_radiation is not None:
                                    station_data_dict["sun_radiation"] = sun_radiation if sun_radiation != "" else None
                                if snow_height is not None:
                                    station_data_dict["snow_height"] = snow_height if snow_height != "" else None

                                # Only add data if either sun_radiation or snow_height is available
                                if station_data_dict:
                                    all_data[station_name_normalized] = station_data_dict #uporabimo normalizirano ime
                            else:
                                _LOGGER.warning(f"Število celic ne ustreza številu stolpcev za postajo {station_name}. Preskakujem vrstico.")

                    return all_data
    except: # Dodan prazen except blok
        pass

    
