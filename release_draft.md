## What's new in v2.0.0

Complete rewrite of the integration — from a single weather entity to a full modular platform with 12 independent data modules.

### New modules

| Module | Description |
|--------|-------------|
| **Weather** | Weather entity with current conditions, hourly/daily/twice-daily forecasts |
| **Webcams** | Live webcam images from ARSO weather stations |
| **Text forecast** | Regional text forecast (today, tomorrow, outlook) |
| **Bio-weather** | Biometeorology forecast (UV index, pollen, health effects) |
| **Mountain forecast** | Mountain weather by region with altitude-based data |
| **Ski resorts** | Ski resort conditions (snow depth, lifts, slopes, webcams) |
| **Radar** | Precipitation and cloud radar images |
| **Agrometeo** | Agricultural meteorology (soil temp, ETP, water balance) |
| **Air quality** | Air quality stations with EAQI index (EU standard) |
| **UTCI** | Universal Thermal Climate Index (thermal comfort) |
| **Warnings** | Weather warnings by region with severity levels |
| **Avalanche** | EAWS avalanche danger bulletin for 29 alpine regions (SI + AT border) |

### Key improvements

- **Modular config flow** — enable only the modules you need; each module has its own coordinator and update interval
- **Real-time weather conditions** — now uses the official API observation data instead of forecast proxy, ensuring accurate current weather state (e.g. correctly shows rain when ARSO reports rain)
- **247 locations** — all ARSO locations available, not just primary weather stations
- **~105 primary stations** — detailed observations with 50+ fields (dew point, visibility, ground temps, solar radiation, etc.)
- **EAQI sensor** — European Air Quality Index with per-pollutant breakdown (PM2.5, PM10, O3, NO2, SO2)
- **Precipitation fix** — no-rain correctly shows 0 mm instead of "unavailable"
- **Audio forecast** — ARSO prognostik voice forecast MP3 URL on text forecast sensors (`audio_url` attribute)
- **Data source attribution** — "Vir podatkov: Agencija RS za okolje"

### Breaking changes

- **Minimum Home Assistant version: 2024.4.0** (uses `entry.runtime_data`)
- Existing entity IDs are preserved — no breaking changes for existing weather/sensor entities from v1.x
- New modules must be enabled via integration options (reconfigure)

### Data sources

All data from [ARSO](https://www.arso.gov.si/) (Agencija Republike Slovenije za okolje) and [EAWS](https://www.avalanches.org/) (European Avalanche Warning Services):
- Official API (`vreme.arso.gov.si`)
- Station observations (`meteo.arso.gov.si`)
- Air quality (`www.arso.gov.si`)
- Avalanche bulletins (`static.lawinen-warnung.eu`, `static.avalanche.report`) — EAWS CAAMLv6

---

**Full Changelog**: https://github.com/andrejs2/slovenian_weather_integration/compare/v1.3.1...v2.0.0
