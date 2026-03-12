# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Home Assistant custom integration** for Slovenian weather data from ARSO (Agencija Republike Slovenije za okolje). It is distributed via HACS (Home Assistant Community Store). Domain: `slovenian_weather_integration`, display name: "ARSO Weather".

Current version: **2.0.0** (see `manifest.json`). Requires Home Assistant 2024.4.0+ (uses `entry.runtime_data`).

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
| `webcams` | `WebcamCoordinator` | 15min | {location}_webcams | `meteo.arso.gov.si/.../observationAms` |
| `text_forecast` | `TextForecastCoordinator` | 60min | text_forecast | `vreme.arso.gov.si/.../fcast_*_text.json` |
| `bio_weather` | `BioWeatherCoordinator` | 60min | bio_weather | `vreme.arso.gov.si/.../fcast_bio_si_d1_text.json` |
| `mountain` | `MountainForecastCoordinator` | 60min | mountain | `meteo.arso.gov.si/.../fproduct/text/sl/` (HTML scraping) |
| `ski_resorts` | `SkiResortCoordinator` | 60min | ski_resorts | `meteo.arso.gov.si/.../observ/surf-snow/xml/` (XML) + snow GeoJSON |
| `radar` | (none, static URLs) | — | radar | `meteo.arso.gov.si/.../observ/radar/` + EU weather maps |
| `agrometeo` | `AgrometeoCoordinator` | 60min | agrometeo | `meteo.arso.gov.si/.../agromet/json/sl/` (GeoJSON) |
| `air_quality` | `AirQualityCoordinator` | 45min | air_quality | `www.arso.gov.si/xml/zrak/` (XML, separate server) |
| `utci` | `UtciCoordinator` | 60min | utci | `meteo.arso.gov.si/.../utci/` (CSV) |
| `warnings` | `WarningsCoordinator` | 5min | {location}_warnings | `meteo.arso.gov.si/.../warning/` (ATOM + CAP XML) |

Global modules (`text_forecast`, `bio_weather`, `mountain`, `ski_resorts`, `radar`, `agrometeo`, `air_quality`, `utci`) provide national data — only one config entry should enable each. `warnings` is per-location (auto-detects region from coordinates).

### Data flow

1. **`arso_weather/client.py` (`ArsoWeather`)** — async HTTP client that fetches data from two ARSO API endpoints:
   - *Official API* (`vreme.arso.gov.si/api/1.0/location/`) — available for all 247 locations; provides forecasts (3h, 6h, 24h). Does NOT return "observation" or "forecast1h" keys.
   - *Primary station API* (`meteo.arso.gov.si/.../observationAms_METEO-{id}_history.json`) — only for primary stations listed in `station_map.py`; provides detailed current observations
   - For primary stations, detailed observation data comes from observationAms
   - For non-primary stations, the first forecast3h entry is used as a proxy for current conditions
   - Raises `ArsoApiError` on failure (never silently swallows errors)
   - Extracts location coordinates (lat/lon) from GeoJSON response

2. **`arso_weather/models.py`** — Pydantic v2 models for all data types:
   - `BaseTimelineEntry` — shared fields (temp, humidity, pressure, wind, cloud/weather conditions)
   - `ObservationTimelineEntry` — basic observation
   - `ObservationDetails` — detailed observation (from primary station API), includes dew point, visibility, ground temps, solar radiation, etc.
   - `Forecast3hTimelineEntry`, `Forecast6hTimelineEntry`, `Forecast24hTimelineEntry` — forecast models
   - ARSO API field names are Slovenian abbreviations mapped via Pydantic `alias` (e.g., `t` → temperature, `rh` → humidity, `msl` → pressure)
   - `home_assistant_weather_condition` computed field maps Slovenian weather text/icons to HA condition strings via `weather_map.py`

3. **`arso_weather/agrometeo_client.py`** — GeoJSON client for agrometeo data (soil temp, ETP, water balance). Fetches from two national endpoints (observation + forecast). 36 known stations in `AGRO_STATIONS` dict.

4. **`arso_weather/mountain_client.py`** — HTML scraping for mountain forecasts + elevation data. 8 regions in `MOUNTAIN_REGIONS` dict. Parses temperature/wind/humidity at various altitudes.

5. **`arso_weather/ski_client.py`** — XML parsing for ski resort data. `SKI_RESORTS` dict maps display names to XML keys.

6. **`arso_weather/snow_client.py`** — GeoJSON client for snow depth data. Uses haversine distance to match snow stations to ski resorts.

7. **`arso_weather/air_quality_client.py`** — XML parser for ARSO air quality data. Two XML endpoints (hourly + daily). 23 stations in `AQ_STATIONS` dict. Includes EAQI (European Air Quality Index) computation with 6-level scale. Pollutants: PM10, PM2.5, O3, NO2, SO2, CO, benzen, NOx.

8. **`arso_weather/utci_client.py`** — CSV parser for UTCI (Universal Thermal Climate Index) data. 13 stations in `UTCI_STATIONS` dict. 3-day hourly forecast with thermal stress categories.

9. **`arso_weather/warnings_client.py`** — ATOM feed + CAP XML parser for weather warnings. 5 regions auto-detected from coordinates. 10 warning types, 4 severity levels.

10. **`coordinator.py`** — All `DataUpdateCoordinator` subclasses. Each has its own update interval and timeout. `SkiResortCoordinator` merges snow data into ski data.

11. **`weather.py` (`ArsoWeatherEntity`)** — HA `WeatherEntity` providing current conditions + hourly/daily/twice-daily forecasts. Exposes: temperature, humidity, pressure, wind speed/gust/bearing, dew point, visibility, UV index (from bio-weather), ozone (from air quality). Uses `astral` library for day/night detection.

12. **`sensor.py`** — Creates sensor entities per module:
    - 35 `ArsoWeatherSensor` per location (FROZEN keys)
    - 3 `ArsoTextSensor` for text forecast
    - 3 `ArsoTextSensor` for bio-weather
    - 2 `ArsoTextSensor` + N elevation sensors for mountain
    - N `ArsoSkiResortSensor` for ski resorts
    - N `ArsoAgrometeoOverviewSensor` + N×6 `ArsoAgrometeoValueSensor` for agrometeo
    - N `ArsoAirQualityOverviewSensor` (EAQI) + N×6 `ArsoAirQualityValueSensor` for air quality
    - N `ArsoUtciSensor` for UTCI
    - 1 `ArsoWarningsOverviewSensor` for warnings

13. **`binary_sensor.py`** — Warning binary sensors:
    - 1 `ArsoWarningsActiveBinarySensor` (ON when any warning level >= 2)
    - 10 `ArsoWarningTypeBinarySensor` per warning type (disabled by default)

14. **`config_flow.py`** — Multi-step UI config flow:
    - Step 1: Location (with fallback to `OBSERVATION_STATIONS` when API is down)
    - Step 2: Module selection
    - Conditional steps: webcam_locations → mountain_regions → ski_resorts → agro_stations → aq_stations → utci_stations
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
    loaded_platforms: list[Platform] = field(default_factory=list)
```

### Key mapping files

- **`arso_weather/station_map.py`** — dict mapping location names → station IDs for primary ARSO stations (~105 stations). If a location is NOT in this map, only forecast-based data is available. Also used as config flow fallback when locations API is down.
- **`arso_weather/weather_map.py`** — `CLOUD_CONDITION_MAP` (Slovenian weather text/icon → HA condition) and `WIND_DIRECTION_MAP` (Slovenian cardinal → English cardinal, e.g., `"SZ"` → `"NW"`). All keys are lowercase (lookup uses `.lower()`).

### Two types of weather stations

- **Primary stations** (in `station_map.py`, ~107) — provide full observation data (ObservationDetails) with ~50 fields including ground temps, solar radiation, visibility
- **Secondary stations** — only forecast-proxy data from official API (temperature, wind, pressure, humidity, conditions). Detailed sensors (dew point, ground temps, etc.) show as unavailable.

## CRITICAL: Backwards Compatibility

See `docs/backwards_compatibility.md` for full details. These identifiers are FROZEN and must NEVER change:

- `DOMAIN = "slovenian_weather_integration"`
- Config entry data key: `"location"` (CONF_LOCATION)
- Weather entity unique_id: `"{entry.entry_id}_weather"` (NO domain prefix)
- Sensor entity unique_id: `"slovenian_weather_integration_{entry.entry_id}_{description.key}"` (WITH domain prefix)
- Device identifier: `("slovenian_weather_integration", "{location_name}")`
- All 35 sensor description `key` values
- Config flow VERSION = 1

## ARSO API Domains

**IMPORTANT**: ARSO uses multiple server domains. Rate limiting applies per domain:
- `vreme.arso.gov.si` — official API (`/api/1.0/`) and static files (`/uploads/probase/`)
- `meteo.arso.gov.si` — static files (`/uploads/probase/`) — same content, different domain
- `www.arso.gov.si` — air quality XML data (`/xml/zrak/`) — SEPARATE server, no rate limiting from weather requests

The `/uploads/probase/` paths are subject to rate limiting. Keep coordinator intervals reasonable (≥15min) to avoid IP bans.

## Conventions

- All HA platforms (`weather`, `sensor`, `image`, `binary_sensor`) are set up via config entries, not YAML
- Entity unique IDs have an intentional asymmetry: weather has no DOMAIN prefix, sensors have it
- Both weather and sensor entities share the same device per location
- Global modules have dedicated devices (e.g., "ARSO Gorski svet", "ARSO Smučišča", "ARSO Agrometeo")
- Device names in Slovenian where applicable
- `docs/` directory is gitignored (local development documentation)
- `ImageEntity.__init__()` requires `hass` as positional argument — always pass it via `super().__init__(hass)`
