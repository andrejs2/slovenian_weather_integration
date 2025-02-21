"""Ta datoteka je namenjena pridobivanju in izračunu UTCI - Universal Thermal Climate Indexu -, 
ko ni podatkov iz biovremenske strani ARSO, ampak so na voljo podatki za izračun UTCI za posamezno lokacijo (veter, vlaga, pokritost oblakov, sončno obsevanje, temperatura, pritisk)"""

import aiohttp
import asyncio
from bs4 import BeautifulSoup
import math
from datetime import datetime, timezone

import logging

_LOGGER = logging.getLogger(__name__)

ARSO_SOLAR_URL = "https://meteo.arso.gov.si/uploads/probase/www/observ/surface/text/sl/observationAms_si_latest.html"
USER_AGENT = "HomeAssistant ARSO Weather Integration"

async def fetch_all_station_data():
    """Pridobi vse podatke s spletne strani ARSO in izračuna UTCI."""
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

                all_data = []
                for table in tables:
                    header = [th.text.strip() for th in table.find_all('th')]
                    
                    header.insert(1, "Ocenjena oblačnost") 
                    for row in table.find_all('tr'):
                        cells = row.find_all('td')
                        if cells:
                            station_data = {}
                            station_data['station'] = cells[0].text.strip() 
                            
                            if len(cells) == len(header) - 1:
                                
                                station_data["Ocenjena oblačnost"] = cells[1].text.strip()

                                for i, cell in enumerate(cells[1:], start=1):
                                    if i+1 < len(header):
                                        station_data[header[i+1]] = cell.text.strip()
                                try:
                                    temperature_str = station_data.get("Temperatura [°C]")
                                    humidity_str = station_data.get("Vlažnost [%]")
                                    wind_speed_kmh_str = station_data.get("Hitrost vetra [km/h]")
                                    radiation_str = station_data.get("Sončno obsevanje [W/m2]")
                                    
                                    if temperature_str and humidity_str and wind_speed_kmh_str:
                                        temperature = float(temperature_str)
                                        humidity = float(humidity_str)
                                        wind_speed_ms = float(wind_speed_kmh_str) / 3.6
                                        month = datetime.now(timezone.utc).month
                                        #Če nimamo podatka o sevanju, ga ocenimo
                                        if radiation_str is None or radiation_str == "":
                                            cloud_coverage_str = station_data.get("Ocenjena oblačnost")
                                            #Če nimamo podatka o oblačnosti se ne da oceniti
                                            if cloud_coverage_str is None or cloud_coverage_str == "":
                                                station_data["UTCI"] = None
                                                _LOGGER.debug("UTCI ni mogoče izračunati, ker manjkajo podatki o sončnem obsevanju in oblačnosti za %s", station_data['station'])
                                                continue

                                            cloud_coverage = float(cloud_coverage_str.replace("%", ""))

                                            if month in [12, 1, 2]: #Zima
                                                radiation = 100 * (1 - cloud_coverage/100)
                                            elif month in [3, 4, 5]: # Pomlad
                                                radiation = 400 * (1- cloud_coverage/100)
                                            elif month in [6, 7, 8]: # Poletje
                                                radiation = 800 * (1- cloud_coverage/100)
                                            else:  # Jesen
                                                radiation = 300 * (1- cloud_coverage/100)

                                            _LOGGER.debug(f"Uporabljeno ocenjeno sevanje za {station_data['station']}: {radiation} W/m2") #Dodano logiranje
                                        else:
                                            radiation = float(radiation_str)
                                        
                                        e = (humidity / 100) * 6.105 * math.exp((17.27 * temperature) / (237.7 + temperature))
                                        
                                        
                                        utci = temperature + (0.33 * e) - (0.7 * wind_speed_ms) - 4.0
                                        station_data["UTCI"] = round(utci, 1)
                                    else:
                                        station_data["UTCI"] = None
                                        _LOGGER.debug("UTCI ni mogoče izračunati, ker manjkajo podatki temperature, vlažnosti ali hitrosti vetra za %s", station_data['station'])
                                except ValueError:
                                    station_data["UTCI"] = None
                                    _LOGGER.warning(f"Napačni podatki za izračun UTCI za postajo {station_data['station']}")

                                all_data.append(station_data)
                            else:
                                _LOGGER.warning(f"Število celic ne ustreza številu stolpcev za postajo {station_data['station']}. Preskakujem vrstico.")

                return all_data

    except Exception as e:
        _LOGGER.error(f"Napaka pri pridobivanju podatkov: {e}")
        return None

    
