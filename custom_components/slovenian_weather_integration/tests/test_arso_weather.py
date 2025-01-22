import pytest
from unittest.mock import patch, AsyncMock
from custom_components.arso_weather_integration.weather import ArsoWeather

# API mock data based on django_api.txt
MOCK_API_RESPONSE = {
    "observation": {
        "features": [
            {
                "properties": {
                    "days": [
                        {
                            "timeline": [
                                {
                                    "clouds_icon_wwsyn_icon": "overcast_heavyRA_day",
                                    "t": "15",
                                    "msl": "1005",
                                    "rh": "95",
                                    "ff_val": "19",
                                    "tp_acc": "25.1",
                                    "dd_shortText": "SV",
                                    "wwsyn_shortText": "dež",
                                    "valid": "2024-09-12T12:00:00+00:00"
                                },
                                {
                                    "clouds_icon_wwsyn_icon": "overcast_modRA_day",
                                    "t": "12",
                                    "msl": "1008",
                                    "rh": "93",
                                    "ff_val": "8",
                                    "tp_acc": "20.1",
                                    "dd_shortText": "V",
                                    "wwsyn_shortText": "dež",
                                    "valid": "2024-09-12T15:00:00+00:00"
                                }
                            ]
                        }
                    ]
                }
            }
        ]
    }
}


@pytest.mark.asyncio
async def test_update_weather_data():
    """Test fetching and updating weather data."""
    # Mock the API call to ARSO
    with patch("aiohttp.ClientSession.get") as mock_get:
        # Create a mock response object
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=MOCK_API_RESPONSE)
        mock_get.return_value.__aenter__.return_value = mock_response

        # Initialize ArsoWeather object with just location
        arso_weather = ArsoWeather(location="Ljubljana")

        # Call the async_update method
        await arso_weather.async_update()

        # Assert the weather data is updated correctly based on the mock API response
        assert arso_weather.native_temperature == 15
        assert arso_weather.native_pressure == 1005
        assert arso_weather.humidity == 95
        assert arso_weather.native_wind_speed == 19
        assert arso_weather.condition == "rainy"  # Mapped from "overcast_heavyRA_day"

        # Assert the hourly forecast is processed correctly
        hourly_forecast = await arso_weather.async_forecast_hourly()
        assert len(hourly_forecast) == 2
        assert hourly_forecast[0]["temperature"] == 15
        assert hourly_forecast[0]["condition"] == "rainy"  # Mapped from "overcast_heavyRA_day"
        assert hourly_forecast[1]["temperature"] == 12
        assert hourly_forecast[1]["condition"] == "rainy"  # Mapped from "overcast_modRA_day"
