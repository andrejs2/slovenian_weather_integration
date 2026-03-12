
[![Python][python-shield]][python]
[![License][license-shield]][license]
[![Maintainer][maintainer-shield]][maintainer]
[![Home Assistant][homeassistant-shield]][homeassistant]
[![HACS][hacs-shield]][hacs]

![Hassfest](https://img.shields.io/github/actions/workflow/status/andrejs2/slovenian_weather_integration/hassfest.yaml?branch=main&label=Hassfest&style=for-the-badge&logo=home-assistant)
![HACS Validation](https://img.shields.io/github/actions/workflow/status/andrejs2/slovenian_weather_integration/validate.yaml?branch=main&label=HACS%20Validation&style=for-the-badge&logo=home-assistant)
[![GitHub Release](https://img.shields.io/github/v/release/andrejs2/slovenian_weather_integration?style=for-the-badge)](https://github.com/andrejs2/slovenian_weather_integration/releases)

![Made in Slovenia](https://img.shields.io/badge/Made_in-Slovenia-005DA4?style=for-the-badge&logo=flag&logoColor=white)

[![BuyMeCoffee][buymecoffee-shield]][buymecoffee]
[![GitHub Sponsors][github-shield]][github]

<div align="center">
  <img src="https://github.com/andrejs2/slovenian_weather_integration/blob/main/images/arso_vreme.PNG?raw=true" alt="Icon Preview" width="300">
</div>

[<img src="https://em-content.zobj.net/thumbs/240/microsoft/319/rocket_1f680.png" alt="Install" width="30"/> ![Install via HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=andrejs2&repository=slovenian_weather_integration&category=integration)

# ARSO Weather -- Slovenian Weather Integration for Home Assistant

## Overview

**ARSO Weather** is a comprehensive Home Assistant custom integration for Slovenian weather data from [ARSO (Agencija Republike Slovenije za okolje)](https://vreme.arso.gov.si/napoved). Version **2.0.0** introduces a fully modular architecture with **11 independent modules**, covering 247 locations across Slovenia and neighboring regions.

Each module can be individually enabled or disabled through the integration's configuration UI. Data is sourced directly from official ARSO APIs, XML feeds, CSV endpoints, and HTML pages -- no third-party services involved.

---

## Disclaimer

This integration is **not** an official integration of the Slovenian Environmental Agency (Agencija RS za okolje). The source of the weather data is the national meteorological service of the Republic of Slovenia (Drzavna meteoroloska sluzba, ki jo izvaja Agencija RS za okolje).

---

## Breaking Changes in v2.0.0

- **Requires Home Assistant 2024.4.0 or newer** (uses `entry.runtime_data`).
- The integration is now fully modular. Only the core **Weather** module is enabled by default.
- All additional modules (Webcams, Text Forecast, Bio-Weather, Mountain, Ski Resorts, Radar, Agrometeo, Air Quality, UTCI, Weather Warnings) must be explicitly enabled via **Settings > Devices & Services > ARSO Weather > Configure**.
- Existing installations upgrading from v1.x will continue to work with weather-only functionality. To access new modules, reconfigure the integration entry and select the desired modules.

---

## Features

ARSO Weather v2.0.0 provides 11 modules:

| # | Module | Description |
|---|--------|-------------|
| 1 | **Weather** (core) | Current conditions + hourly/daily/twice-daily forecasts, 35 sensor entities per location |
| 2 | **Webcams** | Live webcam images from ARSO stations, up to 8 compass directions per location |
| 3 | **Text Forecast** | National text forecast (Besedilna napoved), outlook, and weather map image |
| 4 | **Bio-Weather** | Bio-weather index, UV index, and pollen information |
| 5 | **Mountain Forecast** | Mountain weather for 8 regions, temperature and wind at multiple elevations |
| 6 | **Ski Resorts** | Ski resort conditions, snow depth, temperature, and multi-day forecasts |
| 7 | **Radar** | Current radar image, animated radar, and European weather maps (today + tomorrow) |
| 8 | **Agrometeo** | Agricultural meteorology for 36 stations: soil temperature, evapotranspiration, water balance |
| 9 | **Air Quality** | 23 monitoring stations: PM10, PM2.5, O3, NO2, SO2, CO with European Air Quality Index (EAQI) |
| 10 | **UTCI** | Thermal comfort index (Universal Thermal Climate Index) for 13 stations, 3-day hourly forecast |
| 11 | **Weather Warnings** | 10 warning types across 5 regions, 4 severity levels, binary sensors for automations |

---

## Installation

### HACS Installation (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=andrejs2&repository=slovenian_weather_integration&category=integration)

1. Open HACS in your Home Assistant instance.
2. Search for **ARSO Weather** or click the badge above.
3. Click **Download**.
4. Restart Home Assistant.

### Manual Installation

1. Download or clone this repository.
2. Copy the `custom_components/slovenian_weather_integration` folder to your Home Assistant `custom_components` directory.
3. Restart Home Assistant.

---

## Setup

1. Go to **Settings** > **Devices & Services**.
2. Click **Add Integration** and search for **ARSO Weather**.
3. **Step 1 -- Location**: Select a weather station from the list of 247 available locations.
4. **Step 2 -- Modules**: Choose which modules to enable. The Weather module is always active.
5. **Conditional steps** (shown only for selected modules):
   - **Webcam locations** -- select stations with webcam images
   - **Mountain regions** -- choose from 8 mountain forecast regions
   - **Ski resorts** -- select ski resorts to monitor
   - **Agrometeo stations** -- choose from 36 agricultural weather stations
   - **Air quality stations** -- select from 23 air quality monitoring stations
   - **UTCI stations** -- choose from 13 thermal comfort stations
6. Weather Warnings are automatically configured based on your location's coordinates (region auto-detection).

You can reconfigure modules at any time via **Configure** on the integration entry. Multiple locations can be added as separate entries.

**Important**: Global modules (Text Forecast, Bio-Weather, Mountain, Ski Resorts, Radar, Agrometeo, Air Quality, UTCI) provide national data. Only one config entry should enable each global module.

---

## Modules in Detail

### 1. Weather (Core Module)

Always enabled. Provides a `weather` entity and up to 35 sensor entities per location.

**Weather entity properties:**
- Temperature, humidity, pressure
- Wind speed, wind gust speed, wind bearing
- Dew point, visibility
- UV index (from Bio-Weather module, if enabled)
- Ozone level (from Air Quality module, if enabled)
- Home Assistant weather condition mapping

**Forecast types:**
- **Hourly** -- 3-hour intervals, up to 6 days ahead
- **Daily** -- up to 10 days, with min/max temperature and 24h precipitation
- **Twice-daily** -- morning and evening aggregation

**Sensor entities (up to 35 per location):**

| Sensor Name (SI) | Key | Unit | Availability |
|------------------|-----|------|-------------|
| Temperatura | `temperature` | C | All stations |
| Relativna vlažnost | `relative_humidity_percent` | % | All stations |
| Zračni tlak | `mean_sea_level_pressure_hpa` | hPa | All stations |
| Hitrost vetra | `wind_speed_kmh` | km/h | All stations |
| Smer vetra | `wind_direction_text` | -- | All stations |
| Sunki vetra | `max_wind_gust_kmh` | km/h | All stations |
| Rosišče | `dew_point` | C | Primary only |
| Smer vetra (stopinje) | `wind_direction_degrees` | deg | Primary only |
| Smer sunkov (stopinje) | `wind_direction_max_gust_degrees` | deg | Primary only |
| Povprečna hitrost vetra | `wind_speed_average_kmh` | km/h | Primary only |
| Tlak na postaji | `station_pressure_hpa` | hPa | Primary only |
| Padavine 10 min | `precipitation_accumulated_mm` | mm | Primary only |
| Intenzivnost padavin | `precipitation_rate` | mm/h | Primary only |
| Višina snega | `snow_depth_cm` | cm | Primary only |
| Padavine 1h | `precipitation_1h_accumulated_mm` | mm | Primary only |
| Padavine 12h | `precipitation_12h_accumulated_mm` | mm | Primary only |
| Padavine 24h | `precipitation_24h_accumulated_mm` | mm | Primary only |
| Temperatura vode | `water_temperature` | C | Primary only |
| Globalno sončno sevanje | `global_solar_radiation_wm2` | W/m2 | Primary only |
| Povpr. globalno sončno sevanje | `global_solar_radiation_average_wm2` | W/m2 | Primary only |
| Difuzno sončno sevanje | `diffuse_solar_radiation_wm2` | W/m2 | Primary only |
| Povpr. difuzno sončno sevanje | `diffuse_solar_radiation_average_wm2` | W/m2 | Primary only |
| Vidljivost | `visibility_km` | km | Primary only |
| Temperatura na 5 cm | `temperature_at_5cm` | C | Primary only |
| Povpr. temperatura na 5 cm | `temperature_average_at_5cm` | C | Primary only |
| Temperatura tal 5 cm | `ground_temperature_at_5cm` | C | Primary only |
| Povpr. temperatura tal 5 cm | `ground_temperature_average_at_5cm` | C | Primary only |
| Temperatura tal 10 cm | `ground_temperature_at_10cm` | C | Primary only |
| Povpr. temperatura tal 10 cm | `ground_temperature_average_at_10cm` | C | Primary only |
| Temperatura tal 20 cm | `ground_temperature_at_20cm` | C | Primary only |
| Povpr. temperatura tal 20 cm | `ground_temperature_average_at_20cm` | C | Primary only |
| Temperatura tal 30 cm | `ground_temperature_at_30cm` | C | Primary only |
| Povpr. temperatura tal 30 cm | `ground_temperature_average_at_30cm` | C | Primary only |
| Temperatura tal 50 cm | `ground_temperature_at_50cm` | C | Primary only |
| Povpr. temperatura tal 50 cm | `ground_temperature_average_at_50cm` | C | Primary only |

**Note on entity IDs:** HA auto-generates entity IDs from the device name and sensor name. For example, with device "ARSO Weather Ljubljana" and sensor "Temperatura", the entity ID becomes `sensor.arso_weather_ljubljana_temperatura`. Sensor names are in Slovenian, so entity IDs contain Slovenian words.

Sensors only appear when the station provides data for the field. Primary stations provide all ~35 sensors; secondary stations provide ~6.

### 2. Webcams

Provides `image` entities with live webcam snapshots. Each location may have up to 8 directional cameras (N, NE, E, SE, S, SW, W, NW). Updated every 15 minutes.

### 3. Text Forecast (Besedilna napoved)

National text forecast with 3 sensor entities:

| Sensor | Description |
|--------|-------------|
| Besedilna napoved | Current weather situation and short-term forecast |
| Obeti | Weather outlook for the coming days |
| Vremenska slika | Weather map image URL |

Sensor state is truncated to 255 characters (HA limit). The `full_text` attribute always contains the complete text, suitable for TTS and automations.

### 4. Bio-Weather (Biovreme)

3 sensor entities providing bio-meteorological information:

| Sensor | Description |
|--------|-------------|
| Biovreme | Bio-weather index and health impact description |
| UV indeks | UV index information |
| Cvetni prah | Pollen information and forecast |

### 5. Mountain Forecast (Gorski svet)

8 available mountain forecast regions:

| Region ID | Name |
|-----------|------|
| julian_alps_w | Julijske Alpe - zahod |
| julian_alps_e | Julijske Alpe - vzhod |
| kamnik_savinja_alps | Kamnisko-Savinjske Alpe |
| karavanke | Karavanke |
| pohorje | Pohorje |
| cerkljansko_skofjelosko | Cerkljansko in Skofjelosko hribovje |
| notranjska | Notranjske gore |
| sneznik_javorniki | Sneznik in Javorniki |

Each region provides:
- Text forecast sensors (today, tomorrow, overview, recommendations)
- Overview sensor with temperature/wind data at multiple elevations
- Individual temperature sensors per elevation (disabled by default)
- Individual wind speed sensors per elevation (disabled by default)

### 6. Ski Resorts (Smucisca)

Per-resort sensor entities showing:
- Current conditions and temperature (state)
- Snow depth (from nearest snow measurement station)
- Multi-day forecast time slots
- Full weather details as attributes

### 7. Radar

4 image entities (no coordinator, static URLs):

| Entity | Description |
|--------|-------------|
| Radar (trenutni) | Current radar image for Slovenia |
| Radar (animacija) | Animated radar loop |
| Evropska karta (danes) | European weather map - today |
| Evropska karta (jutri) | European weather map - tomorrow |

### 8. Agrometeo

36 agricultural weather stations providing per-station:

- **Overview sensor** (always enabled) -- summary state with key metrics as attributes
- **6 value sensors** (disabled by default):

| Sensor | Key | Unit | Description |
|--------|-----|------|-------------|
| Temperatura tal 5 cm | `tg_5_cm` | C | Soil temperature at 5 cm depth |
| Temperatura tal 10 cm | `tg_10_cm` | C | Soil temperature at 10 cm depth |
| Temperatura tal 30 cm | `tg_30_cm` | C | Soil temperature at 30 cm depth |
| Min temperatura 5 cm | `tn_5_cm` | C | Minimum temperature at 5 cm |
| Evapotranspiracija | `etp` | mm | Evapotranspiration |
| Vodna bilanca | `wBal` | mm | Water balance |

### 9. Air Quality (Kakovost zraka)

23 monitoring stations across Slovenia. Per-station entities:

- **EAQI Overview sensor** (always enabled) -- European Air Quality Index as state, per-pollutant breakdown in attributes
- **6 pollutant sensors** (disabled by default):

| Sensor | Key | Unit |
|--------|-----|------|
| PM10 | `pm10` | ug/m3 |
| PM2.5 | `pm2.5` | ug/m3 |
| Ozon (O3) | `o3` | ug/m3 |
| Dusikov dioksid (NO2) | `no2` | ug/m3 |
| Zveplov dioksid (SO2) | `so2` | ug/m3 |
| Ogljikov monoksid (CO) | `co` | mg/m3 |

#### EAQI -- European Air Quality Index

The EAQI index is computed according to European Environment Agency methodology. The overall index equals the worst (highest) sub-index across all available pollutants.

**EAQI levels:**

| Level | Slovenian Label | English Translation | Color |
|-------|----------------|---------------------|-------|
| 1 | Dobra | Good | Green |
| 2 | Zadovoljiva | Fair | Yellow-green |
| 3 | Zmerna | Moderate | Yellow |
| 4 | Slaba | Poor | Orange |
| 5 | Zelo slaba | Very poor | Red |
| 6 | Izjemno slaba | Extremely poor | Dark red |

**EAQI pollutant thresholds (ug/m3):**

| Pollutant | Averaging | 1 (Good) | 2 (Fair) | 3 (Moderate) | 4 (Poor) | 5 (Very poor) | 6 (Extremely poor) |
|-----------|-----------|----------|----------|--------------|----------|----------------|---------------------|
| PM2.5 | 24h avg | 0-10 | 10-20 | 20-25 | 25-50 | 50-75 | >75 |
| PM10 | 24h avg | 0-20 | 20-40 | 40-50 | 50-100 | 100-150 | >150 |
| O3 | 1h | 0-50 | 50-100 | 100-130 | 130-240 | 240-380 | >380 |
| NO2 | 1h | 0-40 | 40-90 | 90-120 | 120-230 | 230-340 | >340 |
| SO2 | 1h | 0-100 | 100-200 | 200-350 | 350-500 | 500-750 | >750 |

**Available air quality stations (23):**

Celje - bolnica, Celje - Ljubljanska, Crna na Koroskem, Crnomelj - Loka, Hrastnik, Ilirska Bistrica, Iskrba, Koper, Kranj, Krvavec, Ljubljana - Bezigrad, Ljubljana - Celovska, Ljubljana - Vic, Maribor - Titova, Maribor - Vrbanski plato, Murska Sobota - Cankarjeva, Murska Sobota - Rakican, Nova Gorica, Novo mesto, Otlica, Ptuj, Trbovlje, Zagorje

### 10. UTCI -- Thermal Comfort (Toplotni obcutek)

The Universal Thermal Climate Index (UTCI) measures perceived thermal comfort combining air temperature, humidity, wind, and radiation. 13 stations provide a 3-day hourly forecast.

**UTCI stress categories:**

| UTCI Range (C) | Slovenian Category | English Translation |
|----------------|--------------------|---------------------|
| > 46 | Izredno mocen toplotni stres | Extreme heat stress |
| 38 to 46 | Zelo mocen toplotni stres | Very strong heat stress |
| 32 to 38 | Mocen toplotni stres | Strong heat stress |
| 26 to 32 | Zmeren toplotni stres | Moderate heat stress |
| 9 to 26 | Brez toplotnega stresa | No thermal stress |
| 0 to 9 | Rahel mrazni stres | Slight cold stress |
| -13 to 0 | Zmeren mrazni stres | Moderate cold stress |
| -27 to -13 | Mocen mrazni stres | Strong cold stress |
| -40 to -27 | Zelo mocen mrazni stres | Very strong cold stress |
| < -40 | Izredno mocen mrazni stres | Extreme cold stress |

**Available UTCI stations (13):**

Bilje, Bovec, Celje, Crnomelj, Kocevje, Kranj, Ljubljana, Maribor, Murska Sobota, Novo mesto, Portoroz, Ratece, Slovenj Gradec

### 11. Weather Warnings (Vremenska opozorila)

Per-location warning module. The region is auto-detected from station coordinates across 5 ARSO warning regions. Updated every 5 minutes.

**Entities per location:**
- 1 **overview sensor** -- state shows count of active warnings, attributes include region, highest severity, and list of warning types
- 1 **overview binary sensor** -- ON when any warning has level >= 2 (Moderate or higher)
- 10 **per-type binary sensors** (disabled by default) -- one for each warning type

**Warning types (10):**

| Code | Slovenian Name | English Translation |
|------|---------------|---------------------|
| wind | Veter | Wind |
| rain | Dez | Rain |
| TS | Nevihte | Thunderstorms |
| snow | Sneg | Snow |
| ice | Poledica/zled | Ice/Glazed frost |
| Tx | Visoka temperatura | High temperature |
| Tn | Nizka temperatura | Low temperature |
| forestFire | Pozarna ogrozenost | Forest fire danger |
| avalanche | Snezni plazovi | Avalanches |
| coastal | Obalno opozorilo | Coastal warning |

**Severity levels (4):**

| Level | Color | Slovenian | English |
|-------|-------|-----------|---------|
| 1 | Zelena (Green) | Neznatna ogrozenost | Minor |
| 2 | Rumena (Yellow) | Zmerna ogrozenost | Moderate |
| 3 | Oranzna (Orange) | Velika ogrozenost | Severe |
| 4 | Rdeca (Red) | Zelo velika ogrozenost | Extreme |

Only warnings with level >= 2 include detailed CAP XML data (description, instructions, onset/expiry times).

**Warning regions (5):**

| Region ID | Slovenian Name |
|-----------|---------------|
| SLOVENIA_NORTH-WEST | Severozahodna Slovenija |
| SLOVENIA_NORTH-EAST | Severovzhodna Slovenija |
| SLOVENIA_MIDDLE | Osrednja Slovenija |
| SLOVENIA_SOUTH-WEST | Jugozahodna Slovenija |
| SLOVENIA_SOUTH-EAST | Jugovzhodna Slovenija |

---

## Weather Entity

The `weather.arso_vreme_{location}` entity exposes the following properties:

| Property | Description | Source |
|----------|-------------|--------|
| `native_temperature` | Current temperature (C) | Weather module |
| `humidity` | Relative humidity (%) | Weather module |
| `native_pressure` | Mean sea level pressure (hPa) | Weather module |
| `native_wind_speed` | Wind speed (km/h) | Weather module |
| `wind_bearing` | Wind direction | Weather module |
| `native_wind_gust_speed` | Wind gust speed (km/h) | Weather module |
| `native_dew_point` | Dew point (C) | Weather module (primary stations) |
| `native_visibility` | Visibility (km) | Weather module (primary stations) |
| `uv_index` | UV index | Bio-Weather module (if enabled) |
| `ozone` | Ozone concentration | Air Quality module (if enabled) |
| `condition` | HA weather condition string | Mapped from ARSO Slovenian text/icons |

**Forecast types:**

| Type | Interval | Range | Key Data |
|------|----------|-------|----------|
| Hourly | 3 hours | ~6 days | Temperature, condition, wind, precipitation, `is_daytime` |
| Daily | 24 hours | ~10 days | Max/min temperature, precipitation 24h, wind, gust |
| Twice-daily | Morning/evening | ~5 days | Max/min temperature, condition, `is_daytime` |

Weather forecasts are accessed via the `weather.get_forecasts` action. See [Home Assistant Weather documentation](https://www.home-assistant.io/integrations/weather/#action-weatherget_forecasts).

---

## Locations

There are **two types** of weather stations:

- **Primary stations (~107)** -- listed in the [ARSO observation map](https://meteo.arso.gov.si/uploads/meteo/app/amsview/?params=t,rh,ffavg_val,ffmax_val,msl,tp_acc,snow,tp_12h_acc,tw,gSunRadavg,diffSunRadavg,vis_val&lon=15.11848012616623&lat=45.97045629929457&zoom=8.126735333141523&sliderHours=6). These provide full observation data with up to 35 sensor entities (ground temperatures, solar radiation, visibility, dew point, etc.).

- **Secondary stations (~140)** -- provide forecast-proxy data only (temperature, wind, pressure, humidity, conditions). Detailed sensors will show as unavailable.

The integration covers 247 locations total, including stations in Slovenia, Austria, Italy, Croatia, Hungary, and Bosnia and Herzegovina. You can configure multiple locations as separate integration entries.

---

## Lovelace Card Examples

### Weather Card

```yaml
type: weather-forecast
entity: weather.arso_vreme_ljubljana
forecast_type: daily
```

### Key Sensors -- Entities Card

```yaml
type: entities
title: ARSO Ljubljana
entities:
  - entity: sensor.arso_weather_ljubljana_temperatura
  - entity: sensor.arso_weather_ljubljana_relativna_vlaznost
  - entity: sensor.arso_weather_ljubljana_zracni_tlak
  - entity: sensor.arso_weather_ljubljana_hitrost_vetra
  - entity: sensor.arso_weather_ljubljana_sunki_vetra
  - entity: sensor.arso_weather_ljubljana_rosisce
  - entity: sensor.arso_weather_ljubljana_vidljivost
```

### Weather Warnings Card

```yaml
type: entities
title: Vremenska opozorila
entities:
  - entity: binary_sensor.arso_opozorila_ljubljana_aktivno_opozorilo
  - entity: sensor.arso_opozorila_ljubljana_vremenska_opozorila
  - type: attribute
    entity: sensor.arso_opozorila_ljubljana_vremenska_opozorila
    attribute: regija
    name: Regija
  - type: attribute
    entity: sensor.arso_opozorila_ljubljana_vremenska_opozorila
    attribute: stevilo_opozoril
    name: Število opozoril
```

### Air Quality -- Entities Card

```yaml
type: entities
title: Kakovost zraka - Ljubljana
entities:
  - entity: sensor.arso_kakovost_zraka_eaqi_ljubljana_bezigrad
    name: EAQI
  - type: attribute
    entity: sensor.arso_kakovost_zraka_eaqi_ljubljana_bezigrad
    attribute: eaqi_index
    name: EAQI indeks (1-6)
  - type: attribute
    entity: sensor.arso_kakovost_zraka_eaqi_ljubljana_bezigrad
    attribute: pm10
    name: PM10
    suffix: " ug/m3"
  - type: attribute
    entity: sensor.arso_kakovost_zraka_eaqi_ljubljana_bezigrad
    attribute: pm2.5
    name: PM2.5
    suffix: " ug/m3"
  - type: attribute
    entity: sensor.arso_kakovost_zraka_eaqi_ljubljana_bezigrad
    attribute: o3
    name: O3
    suffix: " ug/m3"
```

### Air Quality -- Color-Coded Tile Card (requires card-mod)

```yaml
type: tile
entity: sensor.arso_kakovost_zraka_eaqi_ljubljana_bezigrad
name: Kakovost zraka
icon: mdi:air-filter
tap_action:
  action: more-info
card_mod:
  style: |
    ha-card {
      {% set eaqi = state_attr('sensor.arso_kakovost_zraka_eaqi_ljubljana_bezigrad', 'eaqi_index') | int(0) %}
      {% if eaqi == 1 %}
        --tile-color: #2ecc71 !important;
      {% elif eaqi == 2 %}
        --tile-color: #a3d977 !important;
      {% elif eaqi == 3 %}
        --tile-color: #f1c40f !important;
      {% elif eaqi == 4 %}
        --tile-color: #f39c12 !important;
      {% elif eaqi == 5 %}
        --tile-color: #e74c3c !important;
      {% elif eaqi == 6 %}
        --tile-color: #8b0000 !important;
      {% else %}
        --tile-color: #9e9e9e !important;
      {% endif %}
    }
```

**EAQI color reference:**

| EAQI Level | Color Code | Description |
|------------|-----------|-------------|
| 1 | `#2ecc71` | Green -- Good |
| 2 | `#a3d977` | Yellow-green -- Fair |
| 3 | `#f1c40f` | Yellow -- Moderate |
| 4 | `#f39c12` | Orange -- Poor |
| 5 | `#e74c3c` | Red -- Very poor |
| 6 | `#8b0000` | Dark red -- Extremely poor |
| N/A | `#9e9e9e` | Grey -- No data |

---

## Automation Examples

### EAQI Notification When Air Quality Is Bad

```yaml
automation:
  - alias: "Obvestilo o slabi kakovosti zraka"
    trigger:
      - platform: template
        value_template: >
          {{ state_attr('sensor.arso_kakovost_zraka_eaqi_ljubljana_bezigrad', 'eaqi_index') | int(0) > 3 }}
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Kakovost zraka"
          message: >
            Kakovost zraka v Ljubljani je
            {{ states('sensor.arso_kakovost_zraka_eaqi_ljubljana_bezigrad') }}
            (EAQI {{ state_attr('sensor.arso_kakovost_zraka_eaqi_ljubljana_bezigrad', 'eaqi_index') }}).
            PM10: {{ state_attr('sensor.arso_kakovost_zraka_eaqi_ljubljana_bezigrad', 'pm10') }} ug/m3,
            PM2.5: {{ state_attr('sensor.arso_kakovost_zraka_eaqi_ljubljana_bezigrad', 'pm2.5') }} ug/m3.
```

### Close Windows Automation Based on Air Quality

```yaml
automation:
  - alias: "Zapri okna ob slabem zraku"
    trigger:
      - platform: template
        value_template: >
          {{ state_attr('sensor.arso_kakovost_zraka_eaqi_ljubljana_bezigrad', 'eaqi_index') | int(0) > 4 }}
    condition:
      - condition: state
        entity_id: cover.living_room_window
        state: "open"
    action:
      - service: cover.close_cover
        target:
          entity_id: cover.living_room_window
      - service: notify.mobile_app_your_phone
        data:
          title: "Okna zaprta"
          message: >
            Okna so bila zaprta zaradi slabe kakovosti zraka
            ({{ states('sensor.arso_kakovost_zraka_eaqi_ljubljana_bezigrad') }}).
```

### Weather Warning Notification

```yaml
automation:
  - alias: "Obvestilo o vremenskem opozorilu"
    trigger:
      - platform: state
        entity_id: binary_sensor.arso_opozorila_ljubljana_aktivno_opozorilo
        to: "on"
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Vremensko opozorilo"
          message: >
            Aktivna opozorila ({{ state_attr('binary_sensor.arso_opozorila_ljubljana_aktivno_opozorilo', 'stevilo_opozoril') }}):
            {{ state_attr('binary_sensor.arso_opozorila_ljubljana_aktivno_opozorilo', 'tipi') | join(', ') }}.
            Najvišja stopnja: {{ state_attr('binary_sensor.arso_opozorila_ljubljana_aktivno_opozorilo', 'najvisja_stopnja') }}/4.
```

---

## Data Sources

All data is sourced from the Slovenian Environmental Agency (ARSO) using three server domains:

| Domain | Purpose |
|--------|---------|
| `vreme.arso.gov.si` | Official API (`/api/1.0/`) and static files (`/uploads/probase/`) |
| `meteo.arso.gov.si` | Static files (`/uploads/probase/`) -- weather, agrometeo, UTCI, radar, warnings |
| `www.arso.gov.si` | Air quality XML data (`/xml/zrak/`) -- separate server |

Data update intervals:
- Weather and Webcams: every 15 minutes
- Warnings: every 5 minutes
- Air Quality: every 45 minutes
- All other modules: every 60 minutes

---

## Debugging

If you encounter issues, enable debug logging by adding the following to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.slovenian_weather_integration: debug
```

---

## Contributing

If you find any bugs or have feature requests, feel free to open an issue or submit a pull request on [GitHub](https://github.com/andrejs2/slovenian_weather_integration).

## Star This Repository

Help other Home Assistant users find this integration by starring this repository. Click the Star button at the top right of the GitHub page.

## Support My Work

Do you enjoy using this Home Assistant integration? Then consider supporting my work using one of the following platforms, your donation is greatly appreciated and keeps me motivated:

<a href="https://www.buymeacoffee.com/andrejs2" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>

Vse svoje projekte razvijam v prostem času, saj programiranje ni moj poklic, a mi je to v veselje. Vsaka pozornost, bodisi kavica ali evro, mi omogoča nadaljevanje tega dela in sem zanjo zelo hvaležen.

## About me
DIY enthusiast, passionate lawyer, proud dad, and fervent advocate for open source and privacy. Combining legal expertise with a love for hands-on projects🛠️⚖️

Kljub temu, da me je poklicna pot prinesla v čisto drug svet, ki nima nobene zveze s programiranjem in razvijanjem integracij, sem predan razvijalec odprtokodnih projektov, ki zagotavljajo visoko stopnjo zasebnosti in omogočajo lokalizacijo v slovenski jezik.

### Motivation
This is my first integration for [Home Assistant](https://www.home-assistant.io/), and actually my first personal and solo project on the platform. In addition to this project, I serve as the [language leader](https://developers.home-assistant.io/docs/voice/language-leaders/) for the [Slovenian version of Home Assistant Assist](https://github.com/home-assistant/intents/tree/main/sentences/sl).

When I first started volunteering to translate sentences for the [Assist](https://www.home-assistant.io/voice_control/), I had little knowledge about the project itself, and even less about submitting PRs on GitHub—a complete beginner. The learning curve was steep, but today, [Slovenian](https://home-assistant.github.io/intents/) is one of the four languages with fully translated sentences for the voice assistant.

If you come across any bugs or mistakes in the **voice assistant**, please report them on [GitHub issues](https://github.com/home-assistant/intents/issues). Thank you!

[python-shield]: https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54
[python]: https://www.python.org/
[releases-shield]: https://img.shields.io/github/v/release/andrejs2/slovenian_weather_integration?style=for-the-badge
[releases]: https://github.com/andrejs2/slovenian_weather_integration/releases
[license-shield]: https://img.shields.io/github/license/andrejs2/slovenian_weather_integration?style=for-the-badge
[license]: ./LICENSE
[maintainer-shield]: https://img.shields.io/badge/MAINTAINER-%40andrejs2-41BDF5?style=for-the-badge
[maintainer]: https://github.com/andrejs2
[homeassistant-shield]: https://img.shields.io/badge/home%20assistant-%2341BDF5.svg?style=for-the-badge&logo=home-assistant&logoColor=white
[homeassistant]: https://www.home-assistant.io/
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge
[hacs]: https://hacs.xyz/
[buymecoffee-shield]: https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black
[buymecoffee]: https://www.buymeacoffee.com/andrejs2
[github-shield]: https://img.shields.io/badge/sponsor-30363D?style=for-the-badge&logo=GitHub-Sponsors&logoColor=#EA4AAA
[github]: https://github.com/sponsors/andrejs2
