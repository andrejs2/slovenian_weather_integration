# Changelog

## [2.0.0] — 2026-03-13

### Added
- **12 data modules** — weather, webcams, text forecast, bio-weather, mountain forecast, ski resorts, radar, agrometeo, air quality, UTCI, warnings, avalanche
- **Modular config flow** — multi-step UI to enable/disable modules and select stations per module
- **247 locations** — all ARSO locations, not just primary weather stations
- **Real-time observation** — uses official API "observation" key for accurate current conditions
- **EAQI sensor** — European Air Quality Index (1–6) with per-pollutant breakdown (PM2.5, PM10, O3, NO2, SO2)
- **UTCI module** — Universal Thermal Climate Index for thermal comfort assessment
- **Weather warnings** — binary sensor + detailed sensor per region with severity levels
- **Avalanche bulletin** — EAWS/CAAMLv6 avalanche danger ratings for 29 alpine regions (11 SI + 12 Koroška + 6 Štajerska) with elevation-based danger levels and avalanche problems
- **Audio forecast** — MP3 URL of ARSO prognostik voice forecast, available as `audio_url` attribute on text forecast sensors (for `media_player.play_media`)
- **Agrometeo module** — soil temperature, ETP, water balance for 36 stations
- **Mountain forecast** — 8 regions with altitude-based temperature, wind, humidity
- **Ski resort conditions** — snow depth, lifts, slopes, webcams for all Slovenian resorts
- **Radar images** — precipitation and cloud radar as image entities
- **Webcam images** — live camera feeds from weather stations
- **Data source attribution** — "Vir podatkov: Agencija RS za okolje"
- **forecast1h** — hourly forecast data now extracted from official API

### Changed
- **Complete architectural rewrite** — separate `DataUpdateCoordinator` per module with independent update intervals
- **Runtime data pattern** — uses `entry.runtime_data` (HA 2024.4.0+) instead of `hass.data`
- **Weather condition detection** — icons checked before text for reliability; condition fields protected from stale observationAms data
- **Minimum Home Assistant version** — bumped to 2024.4.0

### Fixed
- **Weather condition showed "cloudy" instead of "rainy"** — was using forecast3h[0] (next 3h forecast window) instead of real-time observation from official API
- **observationAms read oldest entry** — `_parse_primary_station_data` now reads `days[-1]["timeline"][-1]` (most recent) instead of `days[0]["timeline"][0]` (oldest)
- **Precipitation sensors showed "unavailable"** — empty string from ARSO now converts to 0.0 mm instead of None
- **Air quality station codes** — updated all station codes after ARSO changed them (E21–E34 → E403–E804)

### Backwards compatibility
- All existing entity unique IDs preserved
- Weather entity ID format unchanged
- Sensor entity ID format unchanged
- Config flow VERSION = 1 (no migration needed)

## [1.3.1] — previous release

See [previous releases](https://github.com/andrejs2/slovenian_weather_integration/releases) for older changelog.
