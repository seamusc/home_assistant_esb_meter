"""ESB Meter sensor entity."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EsbMeterCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EsbMeterCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EsbMeterSensor(coordinator, entry)])


class EsbMeterSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the most recent ESB half-hourly reading."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator: EsbMeterCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_energy"
        self._attr_name = f"ESB Meter ({entry.data.get('mprn', '')})"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.latest_reading
