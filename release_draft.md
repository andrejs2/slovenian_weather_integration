## What's new in v2.0.0-beta.1

> **This is a beta release.** Please report any issues on [GitHub Issues](https://github.com/andrejs2/slovenian_weather_integration/issues). Your feedback helps make the stable v2.0.0 release solid.
>
> To install via HACS, enable "Show beta versions" in the integration's HACS settings.

Complete rewrite of the integration — from a single weather entity to a full modular platform with 12 independent data modules.

### New modules

| Module | Description |
|--------|-------------|
| **Weather** | Weather entity with current conditions, hourly/daily/twice-daily forecasts |
| **Webcams** | Live webcam images from ARSO weather stations |
| **Text forecast** | Regional text forecast (today, tomorrow, outlook) + audio forecast MP3 |
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
- **Avalanche bulletin** — EAWS/CAAMLv6 data for 29 alpine regions across Slovenia (11), Carinthia/Koroška (12), and Styria/Štajerska (6), with elevation-based danger ratings, avalanche problems, and detailed text forecasts
- **Audio forecast** — ARSO prognostik voice forecast MP3 URL on text forecast sensors (`audio_url` attribute), playable via `media_player.play_media`
- **Precipitation fix** — no-rain correctly shows 0 mm instead of "unavailable"
- **Data source attribution** — "Vir podatkov: Agencija RS za okolje"

### Upgrading from v1.x

- **Minimum Home Assistant version: 2024.4.0** (uses `entry.runtime_data`)
- All existing entity IDs are preserved — **no breaking changes** for existing weather/sensor entities
- After updating, go to **Settings > Devices & Services > ARSO Weather > Configure** to enable new modules
- The core Weather module continues to work exactly as before

### Known limitations (beta)

- Avalanche bulletins are seasonal — outside winter season the sensor may show "Ni podatkov"
- AT-02 (Koroška) avalanche regions use German names (no Slovenian translation available from EAWS)
- Audio forecast URL is static — it always points to the latest recording, updated daily by ARSO

### Data sources

All data from [ARSO](https://www.arso.gov.si/) (Agencija Republike Slovenije za okolje) and [EAWS](https://www.avalanches.org/) (European Avalanche Warning Services):
- Official API (`vreme.arso.gov.si`)
- Station observations (`meteo.arso.gov.si`)
- Air quality (`www.arso.gov.si`)
- Avalanche bulletins (`static.lawinen-warnung.eu`, `static.avalanche.report`) — EAWS CAAMLv6

---

**Full Changelog**: https://github.com/andrejs2/slovenian_weather_integration/compare/v1.3.1...v2.0.0-beta.1
