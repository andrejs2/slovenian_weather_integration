
[![Python][python-shield]][python]
[![License][license-shield]][license]
[![Maintainer][maintainer-shield]][maintainer]
[![Home Assistant][homeassistant-shield]][homeassistant]
[![HACS][hacs-shield]][hacs]
[![BuyMeCoffee][buymecoffee-shield]][buymecoffee]
[![GitHub Sponsors][github-shield]][github]

[![GitHub Release](https://img.shields.io/github/v/release/andrejs2/slovenian_weather_integration?style=for-the-badge)](https://github.com/andrejs2/slovenian_weather_integration/releases/tag/v1.0.0)

<div align="center">
  <img src="https://github.com/andrejs2/slovenian_weather_integration/blob/main/images/arso_vreme.PNG?raw=true" alt="Icon Preview" width="300">

</div>

# 🌦️ 🇸🇮 Slovenian Weather Integration 🇸🇮 - Home Assistant Custom Component
## 🌍 Overview



**Slovenian Weather Integration** 🇸🇮 is a custom component for [Home Assistant](https://www.home-assistant.io/), leveraging real-time weather data from [ARSO (Agencija Republike Slovenije za okolje)](https://vreme.arso.gov.si/napoved). It provides detailed weather information and forecasts tailored to users in Slovenia and neighboring regions.

---

## ✨ Features

- **🌎 Real-Time Weather Conditions**: Temperature, humidity, wind speed, gusts, pressure, visibility, dew point, and weather conditions.
- **⏱️ 3-Hour & Daily Forecasts**: Up to 6 days of detailed forecasts, including precipitation and wind data.
- **🎨 Cascading Logic for Weather Conditions**: Ensures accurate interpretation of ARSO's comprehensive weather data.
- **🎯 Unique IDs**: Customize and edit entities directly in the Home Assistant UI.
- **🎮 English Translations**: Slovenian cloud condition terms are translated into English for compatibility.

![Weather Preview](https://github.com/andrejs2/slovenian_weather_integration/blob/main/images/lju1.JPG?raw=true)
![Weather Preview](https://github.com/andrejs2/slovenian_weather_integration/blob/main/images/lju2.JPG?raw=true)
![Weather Preview](https://github.com/andrejs2/slovenian_weather_integration/blob/main/images/lju3.JPG?raw=true)
![Weather Preview](https://github.com/andrejs2/slovenian_weather_integration/blob/main/images/lju4.JPG?raw=true)

---

## ⚙️ Installation

### 🟠 HACS Installation 


[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=andrejs2&repository=slovenian_weather_integration&category=integration)

![Installation Preview](https://github.com/andrejs2/slovenian_weather_integration/blob/main/images/Zajetaslika_1.PNG?raw=true)

![Installation Preview](https://github.com/andrejs2/slovenian_weather_integration/blob/main/images/Zajetaslika_2.PNG?raw=true)

![Installation Preview](https://github.com/andrejs2/slovenian_weather_integration/blob/main/images/Zajetaslika_3.PNG?raw=true)

![Installation Preview](https://github.com/andrejs2/slovenian_weather_integration/blob/main/images/Zajetaslika_4.PNG?raw=true)

![Installation Preview](https://github.com/andrejs2/slovenian_weather_integration/blob/main/images/Zajetaslika_5.PNG?raw=true)


### ⚡ Manual Installation

1. Download or clone this repository.
2. Copy the `custom_components/slovenian_weather_integration` folder to your Home Assistant `custom_components` directory:
3. Restart Home Assistant to recognize the new integration.

---

## 🛠️ Setup

1. Go to **Configuration** → **Devices & Services** in Home Assistant.
2. Click **Add Integration**.
3. Search for **ARSO Weather Integration**.
4. Follow the prompts to select your desired location(s).

---

## 🌟 Supported Features

- **Temperature (°C)**
- **Humidity (%)**
- **Pressure (hPa)**
- **Wind Speed (km/h)**
- **Dew Point** (current weather only)
- **Visibility (km)** (current weather only)
- **Precipitation (mm)** (forecasts only)

---

## 📜 Configuration Example

Below is an example automation using hourly forecast data:

```yaml
- trigger:
 - platform: time_pattern
   hours: /1  # Trigger every hour
action:
 - service: weather.get_forecasts
   data:
     type: hourly
   target:
     entity_id: weather.arso_vreme_ljubljana
   response_variable: hourly
sensor:
 - name: Temperature forecast next hour
   unique_id: temperature_forecast_next_hour
   state: "{{ hourly['weather.arso_vreme_ljubljana'].forecast[0].temperature }}"
   unit_of_measurement: °C
```

## Locations - manned and unmanned meteorological stations

This integration requires selecting a location (`Title` column) from table below (Notice: locations can change unannounced!).

****You can configure multiple locations.****

- **Location**: Choose a location in Slovenia or a neighboring country including BIH to display weather data from.

|ID          |Parent ID             |Country|Title                             |Latitude|Longitude|
|------------|----------------------|-------|----------------------------------|--------|---------|
|METEO-16036_|IT_PORDENONE_         |IT     |Aviano                            |46.03   |12.6     |
|METEO-1401_ |SI_NOTRANJSKO-KRASKA_ |SI     |Babno Polje                       |45.6452 |14.5449  |
|METEO-11213_|AT_GAILTAL_           |AT     |Beljak                            |46.61   |13.88    |
|METEO-16105_|IT_VENEZIA_           |IT     |Benetke                           |45.5    |12.33    |
|METEO-14520_|BIH_                  |BIH    |Bihač                             |44.81   |15.88    |
|METEO-1402_ |SI_GORISKA_           |SI     |Bilje pri Novi Gorici             |45.8954 |13.6243  |
|METEO-0038_ |SI_GORENJSKA_         |SI     |Bled                              |46.3684 |14.1101  |
|METEO-1403_ |SI_GORENJSKA_         |SI     |Blegoš                            |46.1675 |14.0816  |
|METEO-1404_ |SI_ZGORNJESAVSKA_     |SI     |Bohinjska Češnjica                |46.2942 |13.9422  |
|METEO-1496_ |SI_GORENJSKA_         |SI     |Boršt Gorenja vas                 |46.0869 |14.1806  |
|METEO-1030_ |SI_BOVSKA_            |SI     |Bovec                             |46.3308 |13.5543  |
|METEO-1405_ |SI_BOVSKA_            |SI     |Breginj                           |46.2628 |13.4272  |
|METEO-0026_ |SI_SPODNJEPOSAVSKA_   |SI     |Brežice                           |45.9051 |15.5947  |
|METEO-1406_ |SI_BOVSKA_            |SI     |Bukovski vrh                      |46.1401 |13.8885  |
|METEO-1025_ |SI_SAVINJSKA_         |SI     |Celje                             |46.2365 |15.2257  |
|METEO-11231_|AT_KAERNTEN_          |AT     |Celovec                           |46.65   |14.33    |
|METEO-0048_ |SI_NOTRANJSKO-KRASKA_ |SI     |Cerknica                          |45.796  |14.3604  |
|METEO-1407_ |SI_NOTRANJSKO-KRASKA_ |SI     |Cerkniško jezero                  |45.723  |14.3989  |
|METEO-1033_ |SI_BELOKRANJSKA_      |SI     |Črnomelj                          |45.56   |15.1461  |
|METEO-1409_ |SI_GORENJSKA_         |SI     |Davča                             |46.1976 |14.0684  |
|METEO-2002_ |SI_GORISKA_           |SI     |Dolenje pri Ajdovščini            |45.8663 |13.9013  |
|METEO-0013_ |SI_OSREDNJESLOVENSKA_ |SI     |Domžale                           |46.1394 |14.5945  |
|METEO-1411_ |SI_PODRAVSKA_         |SI     |Gačnik                            |46.6178 |15.6838  |
|METEO-1412_ |SI_GORISKA_           |SI     |Godnje                            |45.7549 |13.8436  |
|METEO-1414_ |SI_KOROSKA_           |SI     |Gornji Grad                       |46.2987 |14.8063  |
|METEO-11240_|AT_STEIERMARK_        |AT     |Gradec                            |47.0    |15.43    |
|METEO-16002_|IT_TRIESTE_           |IT     |Gradež                            |45.6778 |13.3947  |
|METEO-0023_ |SI_OSREDNJESLOVENSKA_ |SI     |Grosuplje                         |45.9569 |14.6552  |
|METEO-1415_ |SI_PODRAVSKA_         |SI     |Hočko Pohorje                     |46.492  |15.5875  |
|METEO-3414_ |SI_OSREDNJESLOVENSKA_ |SI     |Hrastnik                          |46.1439 |15.0833  |
|METEO-1416_ |SI_BOVSKA_            |SI     |Idrija                            |46.0109 |14.0289  |
|METEO-1037_ |SI_NOTRANJSKO-KRASKA_ |SI     |Ilirska Bistrica                  |45.5533 |14.2358  |
|METEO-1417_ |SI_KOCEVSKA_          |SI     |Iskrba                            |45.5612 |14.858   |
|METEO-0016_ |SI_OBALNO-KRASKA_     |SI     |Izola                             |45.5399 |13.6594  |
|METEO-1418_ |SI_GORENJSKA_         |SI     |Jelendol                          |46.398  |14.3445  |
|METEO-1419_ |SI_SAVINJSKA_         |SI     |Jeronim                           |46.2668 |14.9481  |
|METEO-1420_ |SI_POMURSKA_          |SI     |Jeruzalem                         |46.4759 |16.188   |
|METEO-0011_ |SI_ZGORNJESAVSKA_     |SI     |Jesenice                          |46.4344 |14.057   |
|METEO-1489_ |SI_GORENJSKA_         |SI     |Jezersko                          |46.4049 |14.5144  |
|METEO-1421_ |SI_NOTRANJSKO-KRASKA_ |SI     |Juršče                            |45.6656 |14.2973  |
|METEO-1422_ |SI_PODRAVSKA_         |SI     |Kadrenci                          |46.5682 |15.9503  |
|METEO-0010_ |SI_GORENJSKA_         |SI     |Kamnik                            |46.2257 |14.6119  |
|METEO-1423_ |SI_GORENJSKA_         |SI     |Kamniška Bistrica                 |46.3087 |14.6033  |
|METEO-1424_ |SI_BOVSKA_            |SI     |Kanin                             |46.3581 |13.4744  |
|METEO-14232_|HR_LICKO-SENJSKA_     |HR     |Karlovec                          |45.494  |15.565   |
|METEO-1425_ |SI_BOVSKA_            |SI     |Kneške Ravne                      |46.2153 |13.8247  |
|METEO-1426_ |SI_KOCEVSKA_          |SI     |Kočevje                           |45.6458 |14.8496  |
|METEO-1427_ |SI_DOLENJSKA_         |SI     |Kočevske Poljane                  |45.7224 |15.0569  |
|METEO-1038_ |SI_OBALNO-KRASKA_     |SI     |Koper                             |45.5481 |13.7245  |
|METEO-1428_ |SI_ZGORNJESAVSKA_     |SI     |Korensko sedlo                    |46.5167 |13.7517  |
|METEO-1469_ |SI_NOTRANJSKO-KRASKA_ |SI     |Korošče                           |45.8483 |14.4449  |
|METEO-1027_ |SI_POMURSKA_          |SI     |Krajinski park Goričko            |46.8359 |16.0306  |
|METEO-1429_ |SI_GORENJSKA_         |SI     |Kranj                             |46.2478 |14.3647  |
|METEO-14234_|HR_ZAGREBACKA_        |HR     |Krapina                           |46.138  |15.888   |
|METEO-1430_ |SI_ZGORNJESAVSKA_     |SI     |Kredarica                         |46.3788 |13.8489  |
|METEO-0052_ |HR_PRIMORSKO-GORANSKA_|HR     |Krk                               |45.0286 |14.575   |
|METEO-1431_ |SI_BOVSKA_            |SI     |Krn                               |46.238  |13.658   |
|METEO-3098_ |SI_SPODNJEPOSAVSKA_   |SI     |Krško                             |45.94   |15.4965  |
|METEO-1432_ |SI_GORENJSKA_         |SI     |Krvavec                           |46.2973 |14.5333  |
|METEO-1433_ |SI_OBALNO-KRASKA_     |SI     |Kubed                             |45.52   |13.8689  |
|METEO-1434_ |SI_OSREDNJESLOVENSKA_ |SI     |Kum                               |46.0879 |15.0732  |
|METEO-1028_ |SI_POMURSKA_          |SI     |Lendava                           |46.5526 |16.458   |
|METEO-1035_ |SI_SPODNJEPOSAVSKA_   |SI     |Letališče Cerklje ob Krki         |45.9009 |15.5161  |
|METEO-1023_ |SI_PODRAVSKA_         |SI     |Letališče Edvarda Rusjana Maribor |46.4797 |15.6821  |
|METEO-1493_ |SI_GORENJSKA_         |SI     |Letališče Jožeta Pučnika Ljubljana|46.2175 |14.4728  |
|METEO-1034_ |SI_GORENJSKA_         |SI     |Letališče Lesce                   |46.362  |14.1718  |
|METEO-1008_ |SI_OBALNO-KRASKA_     |SI     |Letališče Portorož                |45.4753 |13.6161  |
|METEO-11204_|AT_GAILTAL_           |AT     |Lienz                             |46.83   |12.81    |
|METEO-1435_ |SI_SPODNJEPOSAVSKA_   |SI     |Lisca                             |46.0678 |15.2849  |
|METEO-1436_ |SI_OSREDNJESLOVENSKA_ |SI     |Litija                            |46.0652 |14.8186  |
|METEO-1495_ |SI_OSREDNJESLOVENSKA_ |SI     |Ljubljana                         |46.0655 |14.5124  |
|METEO-0051_ |SI_SAVINJSKA_         |SI     |Ljubno ob Savinji                 |46.3497 |14.8343  |
|METEO-1437_ |SI_KOROSKA_           |SI     |Logarska dolina                   |46.3936 |14.6311  |
|METEO-1438_ |SI_NOTRANJSKO-KRASKA_ |SI     |Logatec                           |45.9077 |14.2032  |
|METEO-0031_ |SI_OBALNO-KRASKA_     |SI     |Lucija                            |45.5071 |13.6046  |
|METEO-1439_ |SI_KOROSKA_           |SI     |Luče                              |46.3549 |14.7489  |
|METEO-2001_ |SI_OBALNO-KRASKA_     |SI     |Luka Koper                        |45.5645 |13.7448  |
|METEO-1440_ |SI_POMURSKA_          |SI     |Mačkovci                          |46.7845 |16.162   |
|METEO-1029_ |SI_SPODNJEPOSAVSKA_   |SI     |Malkovec                          |45.9533 |15.2049  |
|METEO-1491_ |SI_PODRAVSKA_         |SI     |Maribor                           |46.5678 |15.6261  |
|METEO-1410_ |SI_DOLENJSKA_         |SI     |Marinča vas                       |45.8719 |14.8178  |
|METEO-0037_ |SI_OSREDNJESLOVENSKA_ |SI     |Medvode                           |46.1402 |14.4137  |
|METEO-0029_ |SI_OSREDNJESLOVENSKA_ |SI     |Mengeš                            |46.163  |14.5722  |
|METEO-1441_ |SI_BELOKRANJSKA_      |SI     |Metlika                           |45.6442 |15.3201  |
|METEO-1442_ |SI_KOROSKA_           |SI     |Mežica                            |46.5296 |14.8597  |
|METEO-0047_ |SI_PODRAVSKA_         |SI     |Miklavž na Dravskem polju         |46.5074 |15.6974  |
|METEO-1443_ |SI_SPODNJEPOSAVSKA_   |SI     |Miklavž na Gorjancih              |45.7759 |15.3225  |
|METEO-1444_ |SI_POMURSKA_          |SI     |Murska Sobota                     |46.6521 |16.1913  |
|METEO-1445_ |SI_NOTRANJSKO-KRASKA_ |SI     |Nanos                             |45.7711 |14.0538  |
|METEO-3421_ |SI_GORISKA_           |SI     |Nova Gorica                       |45.9556 |13.6524  |
|METEO-1446_ |SI_NOTRANJSKO-KRASKA_ |SI     |Nova vas - Bloke                  |45.7689 |14.5088  |
|METEO-1447_ |SI_DOLENJSKA_         |SI     |Novo mesto                        |45.8018 |15.1773  |
|METEO-14328_|HR_LICKO-SENJSKA_     |HR     |Ogulin                            |45.263  |15.222   |
|METEO-1448_ |SI_KOCEVSKA_          |SI     |Osilnica                          |45.5314 |14.6915  |
|METEO-3424_ |SI_GORISKA_           |SI     |Otlica                            |45.9381 |13.9161  |
|METEO-3029_ |SI_GORISKA_           |SI     |Park Škocjanske jame              |45.6642 |13.9931  |
|METEO-1449_ |SI_GORENJSKA_         |SI     |Pasja ravan                       |46.0977 |14.2282  |
|METEO-1450_ |SI_KOROSKA_           |SI     |Pavličevo sedlo                   |46.4251 |14.5853  |
|METEO-14308_|HR_ISTARSKA_          |HR     |Pazin                             |45.241  |13.945   |
|METEO-0049_ |SI_OBALNO-KRASKA_     |SI     |Piran                             |45.529  |13.5672  |
|METEO-0053_ |SI_ZGORNJESAVSKA_     |SI     |Planica                           |46.48   |13.7236  |
|METEO-1451_ |SI_ZGORNJESAVSKA_     |SI     |Planina pod Golico                |46.4672 |14.0525  |
|METEO-1452_ |SI_SPODNJEPOSAVSKA_   |SI     |Planina v Podbočju                |45.829  |15.5066  |
|METEO-1019_ |SI_SAVINJSKA_         |SI     |Podčetrtek                        |46.1547 |15.6083  |
|METEO-1454_ |SI_GORISKA_           |SI     |Podnanos                          |45.8045 |13.9659  |
|METEO-1455_ |SI_NOTRANJSKO-KRASKA_ |SI     |Postojna                          |45.7722 |14.1973  |
|METEO-1456_ |SI_BOVSKA_            |SI     |Predel                            |46.4182 |13.5784  |
|METEO-0043_ |SI_KOROSKA_           |SI     |Prevalje                          |46.5448 |14.9031  |
|METEO-1457_ |SI_PODRAVSKA_         |SI     |Ptuj                              |46.4197 |15.8492  |
|METEO-14307_|HR_ISTARSKA_          |HR     |Pulj                              |44.896  |13.932   |
|METEO-14321_|HR_PRIMORSKO-GORANSKA_|HR     |Rab                               |44.756  |14.769   |
|METEO-1413_ |SI_SAVINJSKA_         |SI     |Radegunda                         |46.3661 |14.933   |
|METEO-1032_ |SI_POMURSKA_          |SI     |Radenci                           |46.6419 |16.0487  |
|METEO-0032_ |SI_GORENJSKA_         |SI     |Radovljica                        |46.3446 |14.1685  |
|METEO-1031_ |SI_ZGORNJESAVSKA_     |SI     |Rateče                            |46.4971 |13.7129  |
|METEO-1458_ |SI_GORENJSKA_         |SI     |Ratitovec                         |46.2361 |14.0901  |
|METEO-1026_ |SI_KOROSKA_           |SI     |Ravne na Koroškem                 |46.5477 |14.94    |
|METEO-14216_|HR_PRIMORSKO-GORANSKA_|HR     |Reka                              |45.337  |14.443   |
|METEO-1460_ |SI_KOCEVSKA_          |SI     |Ribnica - Dolenji Lazi            |45.7604 |14.7134  |
|METEO-1461_ |SI_SAVINJSKA_         |SI     |Rogaška Slatina                   |46.2409 |15.6439  |
|METEO-1462_ |SI_PODRAVSKA_         |SI     |Rogla                             |46.453  |15.3315  |
|METEO-14303_|HR_ISTARSKA_          |HR     |Rovinj                            |45.043  |13.614   |
|METEO-1463_ |SI_ZGORNJESAVSKA_     |SI     |Rudno polje                       |46.3463 |13.9235  |
|METEO-0046_ |SI_PODRAVSKA_         |SI     |Ruše                              |46.5386 |15.5154  |
|METEO-14323_|HR_LICKO-SENJSKA_     |HR     |Senj                              |44.993  |14.903   |
|METEO-0044_ |SI_SPODNJEPOSAVSKA_   |SI     |Sevnica                           |46.0091 |15.3005  |
|METEO-1465_ |SI_OSREDNJESLOVENSKA_ |SI     |Sevno                             |45.9821 |14.9236  |
|METEO-0035_ |SI_GORISKA_           |SI     |Sežana                            |45.7073 |13.8685  |
|METEO-14244_|HR_ZAGREBACKA_        |HR     |Sisak                             |45.5    |16.367   |
|METEO-1466_ |SI_OBALNO-KRASKA_     |SI     |Slavnik                           |45.5336 |13.976   |
|METEO-0021_ |SI_PODRAVSKA_         |SI     |Slovenska Bistrica                |46.3898 |15.5704  |
|METEO-1467_ |SI_PODRAVSKA_         |SI     |Slovenske Konjice                 |46.3432 |15.4368  |
|METEO-1470_ |SI_NOTRANJSKO-KRASKA_ |SI     |Sviščaki                          |45.5756 |14.3988  |
|METEO-1482_ |SI_BOVSKA_            |SI     |Šebreljski vrh                    |46.0629 |13.9113  |
|METEO-0041_ |SI_SAVINJSKA_         |SI     |Šentjur                           |46.2184 |15.3927  |
|METEO-0014_ |SI_GORENJSKA_         |SI     |Škofja Loka                       |46.1667 |14.3065  |
|METEO-1464_ |SI_SAVINJSKA_         |SI     |Šmarje pri Jelšah                 |46.2329 |15.5166  |
|METEO-1471_ |SI_KOROSKA_           |SI     |Šmartno pri Slovenj Gradcu        |46.4896 |15.1112  |
|METEO-11272_|AT_GAILTAL_           |AT     |Špital                            |46.78   |13.48    |
|METEO-16000_|IT_PORDENONE_         |IT     |Tablja                            |46.5    |13.3167  |
|METEO-1472_ |SI_GORISKA_           |SI     |Tatre                             |45.599  |14.0876  |
|METEO-16001_|IT_PORDENONE_         |IT     |Tolmeč                            |46.4    |13.0167  |
|METEO-1473_ |SI_BOVSKA_            |SI     |Tolmin - Volče                    |46.1777 |13.718   |
|METEO-1474_ |SI_OSREDNJESLOVENSKA_ |SI     |Topol                             |46.0941 |14.3713  |
|METEO-3413_ |SI_OSREDNJESLOVENSKA_ |SI     |Trbovlje                          |46.1575 |15.054   |
|METEO-1475_ |SI_DOLENJSKA_         |SI     |Trebnje                           |45.911  |15.0072  |
|METEO-1468_ |SI_PODRAVSKA_         |SI     |Trije Kralji na Pohorju           |46.4399 |15.4567  |
|METEO-1476_ |SI_SAVINJSKA_         |SI     |Trojane - Limovce                 |46.1986 |14.9109  |
|METEO-16110_|IT_TRIESTE_           |IT     |Trst                              |45.65   |13.75    |
|METEO-0050_ |SI_OSREDNJESLOVENSKA_ |SI     |Trzin                             |46.1303 |14.5562  |
|METEO-1477_ |SI_KOROSKA_           |SI     |Uršlja gora                       |46.4849 |14.9634  |
|METEO-14246_|HR_ZAGREBACKA_        |HR     |Varaždin                          |46.283  |16.364   |
|METEO-1478_ |SI_GORISKA_           |SI     |Vedrijan                          |46.0131 |13.541   |
|METEO-1479_ |SI_SAVINJSKA_         |SI     |Velenje                           |46.3603 |15.1119  |
|METEO-1480_ |SI_KOCEVSKA_          |SI     |Velike Lašče                      |45.831  |14.6427  |
|METEO-16046_|IT_UDINE_             |IT     |Videm                             |46.0614 |13.2311  |
|METEO-1481_ |SI_ZGORNJESAVSKA_     |SI     |Vogel                             |46.2594 |13.8396  |
|METEO-11000_|AT_KAERNTEN_          |AT     |Volšperk                          |46.85   |14.833   |
|METEO-0054_ |SI_SAVINJSKA_         |SI     |Vransko                           |46.2456 |14.9518  |
|METEO-1483_ |SI_OSREDNJESLOVENSKA_ |SI     |Vrhnika                           |45.9737 |14.2973  |
|METEO-1484_ |SI_ZGORNJESAVSKA_     |SI     |Vršič                             |46.4329 |13.7478  |
|METEO-1408_ |SI_BOVSKA_            |SI     |Zadlog                            |45.9395 |14.0023  |
|METEO-0030_ |SI_OSREDNJESLOVENSKA_ |SI     |Zagorje                           |46.1323 |14.9986  |
|METEO-14240_|HR_ZAGREBACKA_        |HR     |Zagreb                            |45.822  |16.034   |
|METEO-12915_|HU_ZALA_              |HU     |Zalaegerszeg                      |46.86   |16.8     |
|METEO-1485_ |SI_SAVINJSKA_         |SI     |Zavodnje                          |46.4329 |14.9958  |
|METEO-1486_ |SI_ZGORNJESAVSKA_     |SI     |Zelenica                          |46.4288 |14.2329  |
|METEO-1459_ |SI_KOROSKA_           |SI     |Zgornja Kapla                     |46.6434 |15.3502  |
|METEO-1487_ |SI_ZGORNJESAVSKA_     |SI     |Zgornja Radovna                   |46.424  |13.9352  |
|METEO-1488_ |SI_GORENJSKA_         |SI     |Zgornja Sorica                    |46.2221 |14.0285  |
|METEO-0042_ |SI_SAVINJSKA_         |SI     |Žalec                             |46.2527 |15.1604  |
|METEO-1490_ |SI_GORENJSKA_         |SI     |Žiri                              |46.05   |14.1197  |


The integration will automatically pull the weather data and forecasts for the selected location. Multiple location can be added.


## Data Source

The real-time weather observations are retrieved from the observation section of the ARSO.
3 Hour and daily weather forecasts are retrieved from the forecast3h and forecast24h sections of the ARSO.

## Supported Features

    Current Temperature (°C)
    Humidity (%)
    Pressure (hPa)
    Wind Speed (km/h)
    Cloud Conditions (translated to Home Assistant-compatible terms)
    Daily and Hourly Forecasts
    Dew point ---> only in current weather
    Wind gust speed (km/h)
    Visibility (km) ---> only in current weather
    Precipitation (mm)   ---> only in forecasts
    Wind Gust Speed (km/h) ---> only in forecasts

## State attributes

```
datetime: "2024-09-16"
temperature: 2
templow: 0
precipitation: 0
wind_speed: 38
wind_bearing: NW
wind_gust_speed: 0
condition: cloudy
pressure: 1013
```

## Weather forecasts are not part of the entity's state, they're instead made available by a separate API. 
The integration implements two of the async methods `async_forecast_daily`, `async_forecast_hourly`.

## Updating weather forecast(s) - Action `weather.get_forecasts `

To use actions on `weather` see this [Weather Integration](https://www.home-assistant.io/integrations/weather/#action-weatherget_forecasts) page.

![alt text](https://github.com/andrejs2/arso-vremenska-integracija/blob/main/images/kred1.JPG?raw=true)
![alt text](https://github.com/andrejs2/arso-vremenska-integracija/blob/main/images/kred2.JPG?raw=true)

### Examples
```
- trigger:
    - platform: time_pattern
      hours: /1 # Sproži se vsako uro
  action:
    - service: weather.get_forecasts
      data:
        type: hourly
      target:
        entity_id: weather.arso_vreme_ljubljana
      response_variable: hourly
  sensor:
    - name: Temperature forecast next hour
      unique_id: temperature_forecast_next_hour
      state: "{{ hourly['weather.arso_vreme_ljubljana'].forecast[0].temperature }}"
      unit_of_measurement: °C
```

## Unique ID Support

Each weather entity now gets a unique ID based on its location and configuration entry. This allows you to customize and edit the entity from the Home Assistant UI.


## Debugging

If you encounter issues, you can enable debug logging for the integration by adding the following to your configuration.yaml:

    logger:
      default: info
      logs:
        custom_components.arso_weather_integration: debug

## Known Issues

Precipitation Data: Real-time precipitation may not always be available. But is visible as attribute to weather entitiy.

Forecast Availability: Ensure the selected location supports both 3 hour and daily forecasts.


## Contributing

If you find any bugs or have feature requests, feel free to open an issue or submit a pull request on GitHub.

## About me
DIY enthusiast, passionate lawyer, proud dad, and fervent advocate for open source and privacy. Combining legal expertise with a love for hands-on projects🛠️⚖️

Kljub temu, da me je poklicna pot prinesla v čisto drug svet, ki nima nobene zveze s programiranjem in razvijanjem integracij, sem predan razvijalec odprtokodnih projektov, ki zagotavljajo visoko stopnjo zasebnosti in omogočajo lokalizacijo v slovenski jezik. 

### Motivation
This is my first integration for [Home Assistant](https://www.home-assistant.io/), and actually my first personal and solo project on the platform. In addition to this project, I serve as the [language leader](https://developers.home-assistant.io/docs/voice/language-leaders/) for the [Slovenian version of Home Assistant Assist](https://github.com/home-assistant/intents/tree/main/sentences/sl).

When I first started volunteering to translate sentences for the [Assist](https://www.home-assistant.io/voice_control/), I had little knowledge about the project itself, and even less about submitting PRs on GitHub—a complete beginner. The learning curve was steep, but today, [Slovenian](https://home-assistant.github.io/intents/) is one of the four languages with fully translated sentences for the voice assistant.

If you come across any bugs or mistakes in the **voice assistant**, please report them on [GitHub issues](https://github.com/home-assistant/intents/issues). Thank you!


Vse svoje projekte razvijam v prostem času, saj programiranje ni moj poklic, a mi je to v veselje. Vsaka pozornost, bodisi kavica ali evro, mi omogoča nadaljevanje tega dela in sem zanjo zelo hvaležen.

<a href="https://www.buymeacoffee.com/andrejs2" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>


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

