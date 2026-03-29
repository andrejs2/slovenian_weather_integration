# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Home Assistant custom integration** for Slovenian weather data from ARSO (Agencija Republike Slovenije za okolje). It is distributed via HACS (Home Assistant Community Store). Domain: `slovenian_weather_integration`, display name: "ARSO Weather".

Current version: **2.0.7** (see `manifest.json`). Requires Home Assistant 2025.1.0+ (pydantic v2, `entry.runtime_data`).

## Validation & CI

There are no unit tests in this repository. CI consists of two GitHub Actions workflows:
- **hassfest** (`.github/workflows/hassfest.yaml`) — validates the integration against Home Assistant's integration requirements
- **HACS validation** (`.github/workflows/validate.yaml`) — validates HACS compatibility

There is no build step, linter configuration, or package manager. The integration is pure Python with no external dependencies beyond what Home Assistant provides (pydantic, aiohttp, astral are available via HA).

## Architecture

All code lives under `custom_components/slovenian_weather_integration/`.

### Modules

The integration is modular. Each module can be enabled/disabled in the config flow:

| Module | Coordinator | Interval | Device | Data Source |
|--------|-------------|----------|--------|-------------|
| `weather` | `ArsoDataUpdateCoordinator` | 15min | location_name | `vreme.arso.gov.si/api/1.0/` + `meteo.arso.gov.si/.../observationAms` |
| `webcams` | `WebcamCoordinator` | 15min | {location}_webcams | `vreme.arso.gov.si/.../observ/webcam/json/` (dedicated webcam JSON API) |
| `text_forecast` | `TextForecastCoordinator` | 60min | text_forecast | `vreme.arso.gov.si/.../fcast_*_text.json` |
| `bio_weather` | `BioWeatherCoordinator` | 60min | bio_weather | `vreme.arso.gov.si/.../fcast_bio_si_d1_text.json` |
| `mountain` | `MountainForecastCoordinator` | 60min | mountain | `meteo.arso.gov.si/.../fproduct/text/sl/` (HTML scraping) |
| `ski_resorts` | `SkiResortCoordinator` | 60min | ski_resorts | `meteo.arso.gov.si/.../observ/surf-snow/xml/` (XML) + snow GeoJSON |
| `radar` | (none, static URLs) | — | radar | `meteo.arso.gov.si/.../observ/radar/` + EU weather maps |
| `agrometeo` | `AgrometeoCoordinator` | 60min | agrometeo | `meteo.arso.gov.si/.../agromet/json/sl/` (GeoJSON) |
| `air_quality` | `AirQualityCoordinator` | 45min | air_quality | `www.arso.gov.si/xml/zrak/` (XML, separate server) |
| `utci` | `UtciCoordinator` | 60min | utci | `meteo.arso.gov.si/.../utci/` (CSV) |
| `warnings` | `WarningsCoordinator` | 5min | {location}_warnings | `meteo.arso.gov.si/.../warning/` (ATOM + CAP XML) |
| `avalanche` | `AvalancheCoordinator` | 60min | avalanche | `static.lawinen-warnung.eu` + `static.avalanche.report` (EAWS CAAMLv6 JSON) |

Global modules (`text_forecast`, `bio_weather`, `mountain`, `ski_resorts`, `radar`, `agrometeo`, `air_quality`, `utci`, `avalanche`) provide national data — only one config entry should enable each. `warnings` is per-location (auto-detects region from coordinates).

### Data flow

1. **`arso_weather/client.py` (`ArsoWeather`)** — async HTTP client that fetches data from two ARSO API endpoints:
   - *Official API* (`vreme.arso.gov.si/api/1.0/location/`) — available for all 174 locations; returns: observation (real-time current conditions), forecast1h, forecast3h, forecast6h, forecast24h. The "observation" key provides real-time current weather conditions (phenomenon, cloud cover, temperature, wind).
   - *Primary station API* (`meteo.arso.gov.si/.../observationAms_METEO-{id}_history.json`) — only for primary stations listed in `station_map.py`; provides detailed measurement data (dew point, visibility, ground temps, solar radiation, etc.). **IMPORTANT**: this endpoint returns data in REVERSE chronological order — `days[0]` is the newest day, `timeline[0]` is the newest entry. The parser reads `days[0]["timeline"][0]` to get the latest observation.
   - For current conditions, the integration uses the official API "observation" key first, falls back to forecast3h[0] if observation is unavailable. The "observation" key is available for ALL 174 locations (not just primary stations), updates ~1x/hour with integer-rounded temperatures.
   - **Observation vs Forecast data integrity** (verified 2026-03-24): All 174 locations always return the `observation` key — the forecast3h[0] fallback in `_build_observation_proxy()` is only a safety net for ARSO outages and does NOT trigger under normal conditions. This means: observation sensors always show real observation data, never silently substituted forecast data. The `ArsoForecastSensor` class (for cloud_base_text, accumulated_snow_mm, accumulated_precipitation_mm) explicitly reads from forecast1h/3h and is clearly labeled as forecast ("Napovedan sneg", etc.) with a `forecast_time` attribute instead of `last_updated`.
   - For primary stations, observationAms detailed measurements are merged into the observation via `merge_observation_data()`. Condition fields (cloud cover, weather phenomenon, icons — defined in `_CONDITION_FIELDS`) are protected from overwrite during merge because observationAms condition data is often stale. The observation_proxy (from official API "observation") provides authoritative condition fields, while observationAms provides authoritative measurement fields.
   - Raises `ArsoApiError` on failure (never silently swallows errors)
   - Extracts location coordinates (lat/lon) from GeoJSON response

2. **`arso_weather/models.py`** — Pydantic v2 models for all data types:
   - `BaseTimelineEntry` — shared fields (temp, humidity, pressure, wind, cloud/weather conditions)
   - `ObservationTimelineEntry` — basic observation
   - `ObservationDetails` — detailed observation (from primary station API), includes dew point, visibility, ground temps, solar radiation, etc.
   - `Forecast3hTimelineEntry`, `Forecast6hTimelineEntry`, `Forecast24hTimelineEntry` — forecast models
   - ARSO API field names are Slovenian abbreviations mapped via Pydantic `alias` (e.g., `t` → temperature, `rh` → humidity, `msl` → pressure)
   - `home_assistant_weather_condition` computed field maps Slovenian weather text/icons to HA condition strings via `weather_map.py`

3. **`arso_weather/text_forecast_client.py`** — JSON client for ARSO regional text forecasts. Parses sections by title (NAPOVED ZA SLOVENIJO, SOSEDNJE POKRAJINE, OBETI, OPOZORILO, VREMENSKA SLIKA, POVZETEK) with continuation-paragraph grouping. Returns: `forecast` (full Slovenia forecast, today+tomorrow), `summary` (short povzetek), `outlook`, `weather_image`, `audio_url` (MP3).

4. **`arso_weather/webcam_client.py`** — Fetches latest webcam image URLs from the dedicated ARSO webcam JSON API (`webcam_METEO-{station_id}_{direction}_data.json`). Returns full image URLs for each location/direction. Only fetches directions known to exist (from `webcam_stations.py`).

5. **`arso_weather/webcam_stations.py`** — Static mapping of 51 ARSO stations that have webcams, with available compass directions per station. Used by config flow (to show only webcam-capable stations) and by `webcam_client.py` (to avoid 404 requests for non-existent directions).

6. **`arso_weather/agrometeo_client.py`** — GeoJSON client for agrometeo data (soil temp, ETP, water balance). Fetches from two national endpoints (observation + forecast). 36 known stations in `AGRO_STATIONS` dict.

7. **`arso_weather/mountain_client.py`** — HTML scraping for mountain forecasts + elevation data. 8 regions in `MOUNTAIN_REGIONS` dict. Parses temperature/wind/humidity at various altitudes.

8. **`arso_weather/ski_client.py`** — XML parsing for ski resort data. `SKI_RESORTS` dict maps display names to XML keys.

9. **`arso_weather/snow_client.py`** — GeoJSON client for snow depth data. Uses haversine distance to match snow stations to ski resorts.

10. **`arso_weather/air_quality_client.py`** — XML parser for ARSO air quality data. Two XML endpoints (hourly + daily). 23 stations in `AQ_STATIONS` dict. Includes EAQI (European Air Quality Index) computation with 6-level scale. Pollutants: PM10, PM2.5, O3, NO2, SO2, CO, benzen, NOx.

11. **`arso_weather/utci_client.py`** — CSV parser for UTCI (Universal Thermal Climate Index) data. 13 stations in `UTCI_STATIONS` dict. 3-day hourly forecast with thermal stress categories.

12. **`arso_weather/warnings_client.py`** — ATOM feed + CAP XML parser for weather warnings. 5 regions auto-detected from coordinates. 10 warning types, 4 severity levels.

13. **`arso_weather/avalanche_client.py`** — CAAMLv6 JSON parser for EAWS avalanche bulletins. 3 bulletin sources (SI from lawinen-warnung.eu, AT-06/Štajerska from lawinen-warnung.eu in Slovenian, AT-02/Koroška from avalanche.report in German). 29 regions total (11 SI + 12 Koroška + 6 Štajerska) in `AVALANCHE_REGIONS` dict. Smart fetching: only downloads bulletins for sources that contain selected regions.

14. **`coordinator.py`** — All `DataUpdateCoordinator` subclasses. Each has its own update interval and timeout. `SkiResortCoordinator` merges snow data into ski data.

15. **`weather.py` (`ArsoWeatherEntity`)** — HA `WeatherEntity` providing current conditions + hourly/daily/twice-daily forecasts. Exposes: temperature, humidity, pressure, wind speed/gust/bearing, dew point, visibility, UV index (from bio-weather), ozone (from air quality). Uses `astral` library for day/night detection.

16. **`sensor.py`** — Creates sensor entities per module:
    - 39 `ArsoWeatherSensor` per location (FROZEN keys)
    - Up to 3 `ArsoForecastSensor` per location (cloud_base_text, accumulated_snow_mm, accumulated_precipitation_mm)
    - 4 `ArsoTextSensor` for text forecast (forecast, summary, outlook, weather_image)
    - 3 `ArsoTextSensor` for bio-weather
    - 2 `ArsoTextSensor` + N elevation sensors for mountain
    - N `ArsoSkiResortSensor` for ski resorts
    - N `ArsoAgrometeoOverviewSensor` + N×6 `ArsoAgrometeoValueSensor` for agrometeo
    - N `ArsoAirQualityOverviewSensor` (EAQI) + N×6 `ArsoAirQualityValueSensor` for air quality
    - N `ArsoUtciSensor` for UTCI
    - 1 `ArsoWarningsOverviewSensor` for warnings
    - N `ArsoAvalancheSensor` for avalanche

17. **`binary_sensor.py`** — Warning binary sensors:
    - 1 `ArsoWarningsActiveBinarySensor` (ON when any warning level >= 2)
    - 10 `ArsoWarningTypeBinarySensor` per warning type (disabled by default)

18. **`config_flow.py`** — Multi-step UI config flow:
    - Step 1: Location (with fallback to `OBSERVATION_STATIONS` when API is down)
    - Step 2: Module selection
    - Conditional steps: webcam_locations → mountain_regions → ski_resorts → agro_stations → aq_stations → utci_stations → avalanche_regions
    - Options flow mirrors config flow for reconfiguration

### Runtime data pattern

The integration uses modern HA `entry.runtime_data` (not `hass.data[DOMAIN]`):
```python
@dataclass
class ArsoRuntimeData:
    coordinator: ArsoDataUpdateCoordinator
    text_forecast_coordinator: DataUpdateCoordinator | None = None
    bio_weather_coordinator: DataUpdateCoordinator | None = None
    mountain_coordinator: DataUpdateCoordinator | None = None
    ski_coordinator: DataUpdateCoordinator | None = None
    webcam_coordinator: DataUpdateCoordinator | None = None
    agrometeo_coordinator: DataUpdateCoordinator | None = None
    air_quality_coordinator: DataUpdateCoordinator | None = None
    utci_coordinator: DataUpdateCoordinator | None = None
    warnings_coordinator: DataUpdateCoordinator | None = None
    avalanche_coordinator: DataUpdateCoordinator | None = None
    loaded_platforms: list[Platform] = field(default_factory=list)
```

### Key mapping files

- **`arso_weather/station_map.py`** — `ALL_LOCATIONS` tuple (all 174 ARSO locations, used as config flow fallback when locations API is down) + `OBSERVATION_STATIONS` dict (location names → station IDs for ~105 primary stations). If a location is NOT in `OBSERVATION_STATIONS`, only forecast-based data is available.
- **`arso_weather/weather_map.py`** — `CLOUD_CONDITION_MAP` (Slovenian weather text/icon → HA condition) and `WIND_DIRECTION_MAP` (Slovenian cardinal → English cardinal, e.g., `"SZ"` → `"NW"`). All keys are lowercase (lookup uses `.lower()`).
- **`arso_weather/webcam_stations.py`** — dict mapping station names → list of available webcam compass directions (51 stations). Config flow uses this to show only stations with webcams.

### Two types of weather stations

- **Primary stations** (in `station_map.py`, ~107) — provide full observation data (ObservationDetails) with ~50 fields including ground temps, solar radiation, visibility
- **Secondary stations** — only forecast-proxy data from official API (temperature, wind, pressure, humidity, conditions). Detailed sensors (dew point, ground temps, etc.) show as unavailable.

### Two types of weather sensors

- **`ArsoWeatherSensor`** (39 keys) — reads from `current[0]` (merged observation data). For primary stations this is observation + observationAms; for secondary it's the official API observation. **Always real observation data** (forecast3h fallback exists but never triggers under normal conditions).
- **`ArsoForecastSensor`** (3 keys: cloud_base_text, accumulated_snow_mm, accumulated_precipitation_mm) — reads from `forecast1h[0]` or `forecast3h[0]`. Explicitly labeled as forecast data with `forecast_time` attribute. Available for ALL 174 stations. Critical for secondary stations which lack observationAms precipitation data.

## CRITICAL: Backwards Compatibility

See `docs/backwards_compatibility.md` for full details. These identifiers are FROZEN and must NEVER change:

- `DOMAIN = "slovenian_weather_integration"`
- Config entry data key: `"location"` (CONF_LOCATION)
- Weather entity unique_id: `"{entry.entry_id}_weather"` (NO domain prefix)
- Sensor entity unique_id: `"slovenian_weather_integration_{entry.entry_id}_{description.key}"` (WITH domain prefix)
- Device identifier: `("slovenian_weather_integration", "{location_name}")`
- All 39 observation sensor description `key` values + 3 forecast sensor keys
- Config flow VERSION = 1

## ARSO API Domains

**IMPORTANT**: ARSO uses multiple server domains. Rate limiting applies per domain:
- `vreme.arso.gov.si` — official API (`/api/1.0/`), static files (`/uploads/probase/`), and webcam JSON API (`/uploads/probase/www/observ/webcam/json/`)
- `meteo.arso.gov.si` — static files (`/uploads/probase/`) — same content, different domain
- `www.arso.gov.si` — air quality XML data (`/xml/zrak/`) — SEPARATE server, no rate limiting from weather requests
- `static.lawinen-warnung.eu` — EAWS avalanche bulletins (SI, AT-06/Štajerska)
- `static.avalanche.report` — EAWS avalanche bulletins (AT-02/Koroška, AT-07/Tirolska)

The `/uploads/probase/` paths are subject to rate limiting. Keep coordinator intervals reasonable (≥15min) to avoid IP bans.

## Conventions

- All HA platforms (`weather`, `sensor`, `image`, `binary_sensor`) are set up via config entries, not YAML
- Entity unique IDs have an intentional asymmetry: weather has no DOMAIN prefix, sensors have it
- Both weather and sensor entities share the same device per location
- Global modules have dedicated devices (e.g., "ARSO Gorski svet", "ARSO Smučišča", "ARSO Agrometeo")
- Device names in Slovenian where applicable
- `docs/` directory is gitignored (local development documentation)
- `ImageEntity.__init__()` requires `hass` as positional argument — always pass it via `super().__init__(hass)`
- Minimum HA version is set in `hacs.json` (NOT `manifest.json` — hassfest rejects `homeassistant` key in manifest for custom integrations)

## Session Log

### 2026-03-29 — v2.0.7: Hardcode all ARSO locations as config flow fallback
- **Trigger:** GitHub discussion #34 — user reported `ARSO locations API unavailable, using station list fallback`
- **Root cause:** ARSO's `locations.json` had a brief outage on 2026-03-28 (2 occurrences in 3 min). Also discovered that ARSO's Django endpoint `/api/1.0/locations/` (without params) now returns HTTP 500, though the integration doesn't use it.
- **Finding:** ARSO reduced total location count from 247 to 174. The Angular frontend never called bare `/locations/` — it always uses `?loc=` (autocomplete) or `?lat=&lon=` (geolocation).
- **Fix:** Added `ALL_LOCATIONS` tuple (174 locations) to `station_map.py`. Config flow fallback now offers complete location list instead of only 105 primary stations. Primary behavior unchanged (API called first, fallback only on failure).
- **Branch:** `fix/hardcode-all-locations-fallback`, merged to main, released as v2.0.7
