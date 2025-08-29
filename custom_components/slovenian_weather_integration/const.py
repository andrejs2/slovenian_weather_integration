DOMAIN = "slovenian_weather_integration"
DEFAULT_NAME = "ARSO Weather Integration"
DEFAULT_PLATFORMS = ["weather", "sensor"]  # Privzeto vključene platforme
# --- Mountain feature (options) ---
CONF_ENABLE_MOUNTAIN = "enable_mountain"
CONF_MOUNTAIN_REGION = "mountain_region"
DEFAULT_MOUNTAIN_REGION = "JULIAN-ALPS"

MOUNTAIN_DEVICE_SUFFIX = "mountain"
MOUNTAIN_COORDINATOR_KEY = "{}_mountain"  # f"{entry_id}_mountain"
