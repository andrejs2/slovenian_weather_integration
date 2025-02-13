import logging
from homeassistant.helpers.entity_registry import async_get
from .const import LOCATION_MAPPING

_LOGGER = logging.getLogger(__name__)

def normalize_location(location):
    """Normalizira ime lokacije, da se ujema z ARSO podatki."""
    location = location.lower().replace(" ", "_")
    return LOCATION_MAPPING.get(location, location)

async def async_remove_sensors(hass, domain):
    """Asinhrono odstrani vse senzorje povezane z domeno."""
    entity_registry = await async_get(hass)
    entities = list(entity_registry.entities.keys())

    for entity_id in entities:
        if entity_id.startswith(f"sensor.{domain}"):
            _LOGGER.info("🗑️ Odstranjujem senzor: %s", entity_id)
            entity_registry.async_remove(entity_id)

    _LOGGER.info("Vsi senzorji za domeno %s odstranjeni.", domain)
