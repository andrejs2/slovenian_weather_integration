# Dokumentacija senzorjev — ARSO Weather

Ta dokument podrobno opisuje vsak senzor integracije: **kaj predstavlja**, ali gre za
**izmerjeni podatek ali napoved** ter **na kakšen časovni interval** se nanaša. Namenjen je
uporabnikom, ki želijo vedeti, kateri senzor uporabiti (npr. za avtomatizacije).

> Imena senzorjev so v slovenščini (kot v ARSO virih), ključi (`key`) pa v angleščini.
> Entitetni ID-ji se v Home Assistantu samodejno tvorijo iz imena naprave in senzorja,
> npr. `sensor.arso_weather_ljubljana_temperatura`.

## Legenda tipa podatka

| Oznaka           | Pomen                                                             |
| ---------------- | ----------------------------------------------------------------- |
| 🟢 **Meritev**   | Izmerjena vrednost s postaje (trenutno stanje ob zadnji meritvi). |
| 🔵 **Napoved**   | Napovedana vrednost iz ARSO modela (ni izmerjeno).                |
| 🟡 **Izpeljano** | Izračunano iz izmerjene vrednosti (ni neposredna meritev).        |

## Razpoložljivost glede na tip postaje

ARSO loči dva tipa lokacij:

* **Primarne postaje (\~107)** — imajo merilno opremo in vračajo vse meritve
  (temperature tal, sončno sevanje, vidljivost, rosišče, padavine ...). Skupaj do \~42 senzorjev.

* **Sekundarne postaje (\~140)** — vračajo le osnovne podatke iz uradnega API-ja
  (temperatura, veter, tlak, vlažnost, vremenski pojav, oblačnost). Podrobni merilni
  senzorji se prikažejo kot *nedosegljivi* (`unavailable`).

Senzor se ustvari samo, če postaja ob prvem osveževanju vrača podatek za to polje.

***

## 1. Vremenski modul — osnovni senzorji (vedno omogočen)

Posodobitev na **15 min**. Vir trenutnih razmer je uradni API ARSO (ključ `observation`,
osvežuje se \~1×/uro), za primarne postaje pa se dodatno združijo podrobne meritve iz
postajnega API-ja (`observationAms`).

### 1.1 Izmerjeni senzorji (do 39 na lokacijo)

| Senzor                         | Key                                   | Tip          | Enota | Razpoložljivost | Opis / interval                                                                                                                                          |
| ------------------------------ | ------------------------------------- | ------------ | ----- | --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Temperatura                    | `temperature`                         | 🟢 Meritev   | °C    | Vse             | Temperatura zraka ob zadnji meritvi. Pri sekundarnih postajah zaokrožena na celo stopinjo.                                                               |
| Relativna vlažnost             | `relative_humidity_percent`           | 🟢 Meritev   | %     | Vse             | Relativna vlažnost zraka.                                                                                                                                |
| Zračni tlak                    | `mean_sea_level_pressure_hpa`         | 🟢 Meritev   | hPa   | Vse             | Zračni tlak, reduciran na morsko gladino.                                                                                                                |
| Hitrost vetra                  | `wind_speed_kmh`                      | 🟢 Meritev   | km/h  | Vse             | Trenutna hitrost vetra.                                                                                                                                  |
| Smer vetra                     | `wind_direction_text`                 | 🟢 Meritev   | —     | Vse             | Smer vetra (S, SV, V, JV ...).                                                                                                                           |
| Sunki vetra                    | `max_wind_gust_kmh`                   | 🟢 Meritev   | km/h  | Vse             | Najmočnejši sunek vetra v merilnem intervalu.                                                                                                            |
| Tendenca tlaka                 | `pressure_tendency`                   | 🟢 Meritev   | —     | Vse             | Opis spreminjanja tlaka (raste / pada / stalen).                                                                                                         |
| Vremenski pojav                | `weather_phenomenon`                  | 🟢 Meritev   | —     | Vse             | Opazovani vremenski pojav (dež, megla, sneg ...).                                                                                                        |
| Oblačnost                      | `cloud_coverage`                      | 🟡 Izpeljano | %     | Vse             | Stopnja oblačnosti, izpeljana iz besedilnega opisa/ikone.                                                                                                |
| Oblačnost (opis)               | `cloud_cover_text`                    | 🟢 Meritev   | —     | Vse             | Besedilni opis oblačnosti (jasno, delno oblačno ...).                                                                                                    |
| Rosišče                        | `dew_point`                           | 🟢 Meritev   | °C    | Primarne        | Temperatura rosišča.                                                                                                                                     |
| Smer vetra (stopinje)          | `wind_direction_degrees`              | 🟢 Meritev   | °     | Primarne        | Smer vetra v stopinjah (0–360).                                                                                                                          |
| Smer sunkov (stopinje)         | `wind_direction_max_gust_degrees`     | 🟢 Meritev   | °     | Primarne        | Smer najmočnejšega sunka v intervalu.                                                                                                                    |
| Povprečna hitrost vetra        | `wind_speed_average_kmh`              | 🟢 Meritev   | km/h  | Primarne        | Povprečna hitrost vetra v merilnem intervalu.                                                                                                            |
| Tlak na postaji                | `station_pressure_hpa`                | 🟢 Meritev   | hPa   | Primarne        | Dejanski tlak na nadmorski višini postaje (ni reduciran).                                                                                                |
| Padavine 10 min                | `precipitation_accumulated_mm`        | 🟢 Meritev   | mm    | Primarne        | Skupna količina padavin v zadnjem **10-minutnem** intervalu.                                                                                             |
| **Intenzivnost padavin**       | `precipitation_rate`                  | 🟡 Izpeljano | mm/h  | Primarne        | **10-minutne padavine, preračunane na urno intenzivnost** (`padavine_10min / 10 × 60`). Ni dejansko izmerjena urna vsota, ampak trenutna jakost padanja. |
| Višina snega                   | `snow_depth_cm`                       | 🟢 Meritev   | cm    | Primarne        | Višina snežne odeje.                                                                                                                                     |
| Padavine 1h                    | `precipitation_1h_accumulated_mm`     | 🟢 Meritev   | mm    | Primarne        | Vsota padavin v zadnji **1 uri**.                                                                                                                        |
| Padavine 12h                   | `precipitation_12h_accumulated_mm`    | 🟢 Meritev   | mm    | Primarne        | Vsota padavin v zadnjih **12 urah**.                                                                                                                     |
| Padavine 24h                   | `precipitation_24h_accumulated_mm`    | 🟢 Meritev   | mm    | Primarne        | Vsota padavin v zadnjih **24 urah**.                                                                                                                     |
| Temperatura vode               | `water_temperature`                   | 🟢 Meritev   | °C    | Primarne        | Temperatura vode (le postaje ob vodotokih/morju).                                                                                                        |
| Globalno sončno sevanje        | `global_solar_radiation_wm2`          | 🟢 Meritev   | W/m²  | Primarne        | Trenutno globalno sončno obsevanje.                                                                                                                      |
| Povpr. globalno sončno sevanje | `global_solar_radiation_average_wm2`  | 🟢 Meritev   | W/m²  | Primarne        | Povprečno globalno obsevanje v merilnem intervalu.                                                                                                       |
| Difuzno sončno sevanje         | `diffuse_solar_radiation_wm2`         | 🟢 Meritev   | W/m²  | Primarne        | Trenutno difuzno (razpršeno) sončno obsevanje.                                                                                                           |
| Povpr. difuzno sončno sevanje  | `diffuse_solar_radiation_average_wm2` | 🟢 Meritev   | W/m²  | Primarne        | Povprečno difuzno obsevanje v intervalu.                                                                                                                 |
| Vidljivost                     | `visibility_km`                       | 🟢 Meritev   | km    | Primarne        | Vodoravna vidljivost.                                                                                                                                    |
| Temperatura na 5 cm            | `temperature_at_5cm`                  | 🟢 Meritev   | °C    | Primarne        | Temperatura **zraka** 5 cm nad tlemi (prizemna minimalna).                                                                                               |
| Povpr. temperatura na 5 cm     | `temperature_average_at_5cm`          | 🟢 Meritev   | °C    | Primarne        | Povprečje temperature zraka na 5 cm v intervalu.                                                                                                         |
| Temperatura tal 5 cm           | `ground_temperature_at_5cm`           | 🟢 Meritev   | °C    | Primarne        | Temperatura **tal** v globini 5 cm.                                                                                                                      |
| Povpr. temperatura tal 5 cm    | `ground_temperature_average_at_5cm`   | 🟢 Meritev   | °C    | Primarne        | Povprečje temperature tal na 5 cm v intervalu.                                                                                                           |
| Temperatura tal 10 cm          | `ground_temperature_at_10cm`          | 🟢 Meritev   | °C    | Primarne        | Temperatura tal v globini 10 cm.                                                                                                                         |
| Povpr. temperatura tal 10 cm   | `ground_temperature_average_at_10cm`  | 🟢 Meritev   | °C    | Primarne        | Povprečje v intervalu.                                                                                                                                   |
| Temperatura tal 20 cm          | `ground_temperature_at_20cm`          | 🟢 Meritev   | °C    | Primarne        | Temperatura tal v globini 20 cm.                                                                                                                         |
| Povpr. temperatura tal 20 cm   | `ground_temperature_average_at_20cm`  | 🟢 Meritev   | °C    | Primarne        | Povprečje v intervalu.                                                                                                                                   |
| Temperatura tal 30 cm          | `ground_temperature_at_30cm`          | 🟢 Meritev   | °C    | Primarne        | Temperatura tal v globini 30 cm.                                                                                                                         |
| Povpr. temperatura tal 30 cm   | `ground_temperature_average_at_30cm`  | 🟢 Meritev   | °C    | Primarne        | Povprečje v intervalu.                                                                                                                                   |
| Temperatura tal 50 cm          | `ground_temperature_at_50cm`          | 🟢 Meritev   | °C    | Primarne        | Temperatura tal v globini 50 cm.                                                                                                                         |
| Povpr. temperatura tal 50 cm   | `ground_temperature_average_at_50cm`  | 🟢 Meritev   | °C    | Primarne        | Povprečje v intervalu.                                                                                                                                   |

> **Opomba o "Povpr." senzorjih:** vrednosti z "Povpr." so povprečja, ki jih ARSO izračuna
> za zadnji merilni interval postaje. Senzorji brez "Povpr." so trenutne (točkovne) meritve
> ob času zadnjega odčitka.

### 1.2 Napovedni senzorji (do 3 na lokacijo)

Ti senzorji **niso meritve** — berejo se iz napovedi uradnega API-ja (`forecast1h` / `forecast3h`)
in so na voljo za **vse lokacije** (tudi sekundarne). Vsebujejo atribut `forecast_time`
(čas, na katerega se napoved nanaša) namesto `last_updated`.

| Senzor             | Key                            | Tip        | Enota | Opis / interval                                                                     |
| ------------------ | ------------------------------ | ---------- | ----- | ----------------------------------------------------------------------------------- |
| **Višina oblakov** | `cloud_base_text`              | 🔵 Napoved | —     | **Napovedana** spodnja meja oblakov (besedilno). Kljub imenu ni izmerjena vrednost. |
| Napovedan sneg     | `accumulated_snow_mm`          | 🔵 Napoved | mm    | Napovedana količina novozapadlega snega za prihajajoči napovedni interval.          |
| Napovedan dež      | `accumulated_precipitation_mm` | 🔵 Napoved | mm    | Napovedana količina padavin za prihajajoči napovedni interval.                      |

> Za sekundarne postaje so ti napovedni senzorji edini vir podatka o padavinah,
> saj te postaje nimajo merilnih senzorjev za padavine.

### 1.3 Diagnostični senzorji (2 na lokacijo, vedno)

Kategorija `diagnostic`. Ne gre za vremenske podatke, temveč za nadzor prometa do API-ja.

| Senzor               | Key                     | Opis                                                                                                        |
| -------------------- | ----------------------- | ----------------------------------------------------------------------------------------------------------- |
| API zahtevkov na uro | `api_requests_per_hour` | Drseče 1-urno število HTTP zahtevkov; atributi: `total_requests`, razčlenitev `per_domain`, `uptime_hours`. |
| API napak na uro     | `api_errors_per_hour`   | Drseče 1-urno število napak; atributi: `total_errors`, razčlenitev `per_domain`.                            |

### 1.4 Napoved vremena (weather entiteta, ne senzor)

Celotna **vremenska napoved** ni na voljo kot senzor, ampak prek **weather entitete**
(`weather.arso_weather_<lokacija>`) in akcije **`weather.get_forecasts`**. To je standardni
HA način in je opisan tudi v [README](README.md#weather-entity).

Klic akcije:

```yaml
action: weather.get_forecasts
target:
  entity_id: weather.arso_weather_ljubljana   # ali device_id
data:
  type: hourly        # hourly | daily | twice_daily
```

Vsaka točka napovedi (🔵 **napoved**) vsebuje:

| Polje             | Pomen                                                            | Enota      |
| ----------------- | ---------------------------------------------------------------- | ---------- |
| `datetime`        | Čas, na katerega se napoved nanaša                               | ISO 8601   |
| `temperature`     | Napovedana temperatura                                           | °C         |
| `precipitation`   | Napovedana količina padavin v intervalu                          | mm         |
| `condition`       | Vremensko stanje (`sunny`, `rainy`, `cloudy`, `clear-night` ...) | —          |
| `cloud_coverage`  | Napovedana oblačnost                                             | %          |
| `humidity`        | Napovedana relativna vlažnost                                    | %          |
| `pressure`        | Napovedani zračni tlak                                           | hPa        |
| `wind_speed`      | Napovedana hitrost vetra                                         | km/h       |
| `wind_gust_speed` | Napovedani sunki vetra (le kjer ARSO poda podatek)               | km/h       |
| `wind_bearing`    | Napovedana smer vetra                                            | S/SV/V ... |

* `type: hourly` — urna napoved (vir `forecast1h`, ob odsotnosti `forecast3h`).

* `type: daily` — dnevna napoved.

* `type: twice_daily` — napoved dvakrat dnevno (dan/noč).

> Napovedni **senzorji** iz [poglavja 1.2](#12-napovedni-senzorji-do-3-na-lokacijo)
> (Višina oblakov, Napovedan sneg, Napovedan dež) so namenjeni neposredni uporabi v
> Lovelace/avtomatizacijah brez klica akcije; za celotno časovno vrsto napovedi pa
> uporabite `weather.get_forecasts`.

***

## 2. Senzorji ostalih modulov

Spodnji moduli so neobvezni (omogočijo se v konfiguraciji). Podrobnejši opisi modulov so v
glavnem [README](README.md); spodaj je tip podatka.

| Modul                   | Senzorji                                                                     | Tip podatka             |
| ----------------------- | ---------------------------------------------------------------------------- | ----------------------- |
| Besedilna napoved       | Besedilna napoved, Povzetek, Obeti, Vremenska slika                          | 🔵 Napoved (besedilo)   |
| Biovreme                | Biovreme, UV indeks, Cvetni prah                                             | 🔵 Napoved              |
| Gorski svet             | Gorska napoved (danes/jutri/pregled/priporočila) + senzorji po nadm. višinah | 🔵 Napoved              |
| Smučišča                | Stanje snega, temperatura, žičnice ... po smučišču                           | 🟢 Meritev / opazovanje |
| Agrometeo               | Temperatura tal (5/10/30 cm), min temp., evapotranspiracija, vodna bilanca   | 🟢 Meritev + 🔵 napoved |
| Kakovost zraka          | EAQI + PM10, PM2.5, O₃, NO₂, SO₂, CO                                         | 🟢 Meritev              |
| UTCI (toplotni občutek) | Univerzalni toplotni indeks po urah                                          | 🔵 Napoved              |
| Vremenska opozorila     | Trenutno veljavna opozorila (atribut `napovedana_opozorila` za prihodnja) + binarni senzorji po tipu | 🔵 Napoved/opozorilo    |
| Snežni plazovi          | EAWS bilten po regijah (stopnja nevarnosti ...)                              | 🔵 Napoved/opozorilo    |

***

## Pogosta vprašanja

**Kateri senzor za dež naj uporabim?**

* Za **trenutno jakost padanja** → `precipitation_rate` (Intenzivnost padavin, mm/h, izpeljano iz 10-min meritve).

* Za **dejanske padle količine** → `precipitation_1h_accumulated_mm`, `precipitation_12h_accumulated_mm` ali `precipitation_24h_accumulated_mm` (izmerjene vsote).

* Za **napoved dežja** → `accumulated_precipitation_mm` (Napovedan dež) — na voljo tudi na sekundarnih postajah.

**Zakaj je "Višina oblakov" napoved in ne meritev?**
ARSO za to polje ne objavlja izmerjene vrednosti prek tega API-ja — vrača le napovedano spodnjo
mejo oblakov, zato je senzor v skupini napovednih senzorjev.

**Zakaj nekateri senzorji niso na voljo (`unavailable`)?**
Vaša lokacija je verjetno sekundarna postaja brez merilne opreme za to polje. Seznam primarnih
postaj je v [README](README.md#locations).
