import aiohttp
import logging

_LOGGER = logging.getLogger(__name__)

# URL za pridobivanje podatkov o cvetnem prahu
ARSO_POLLEN_URL = "https://meteo.arso.gov.si/uploads/probase/www/agromet/json/sl/feno/objlist.json"

async def fetch_pollen_data():
    """Asinhrono pridobi podatke o cvetnem prahu iz ARSO JSON."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(ARSO_POLLEN_URL) as response:
                if response.status != 200:
                    _LOGGER.error("❌ Napaka pri pridobivanju ARSO API! HTTP status: %s", response.status)
                    return None

                data = await response.json()
                return parse_pollen_data(data)

        except Exception as e:
            _LOGGER.error("❌ Napaka pri obdelavi ARSO podatkov: %s", e, exc_info=True)
            return None

def parse_pollen_data(data):
    """Obdela in strukturira podatke o cvetnem prahu za Home Assistant."""
    if not data:
        return {"state": "Ni podatkov", "attributes": {}}

    pollen_info = {}
    state_values = []

    for rastlina in data:
        ime = rastlina["ime"].lower()
        ime_lat = rastlina["ime_lat"].capitalize()
        faze = ", ".join(f"{f['id_faze']}: {f['ime_faze']}" for f in rastlina["faze"])

        # Dodamo ime v stanje senzorja
        state_values.append(ime)

        # Formatiran izpis za atribute
        pollen_info[ime] = f"{ime} ({ime_lat})\n   Faza: {faze}\n"

    return {
        "state": ", ".join(state_values),
        "attributes": pollen_info,
    }

if __name__ == "__main__":
    import asyncio

    async def test_fetch_pollen():
        data = await fetch_pollen_data()
        print("📊 Pridobljeni podatki o cvetnem prahu:", data)

    asyncio.run(test_fetch_pollen())
