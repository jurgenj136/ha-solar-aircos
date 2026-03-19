"""Sensor platform for Smart Airco integration."""

from __future__ import annotations

# pyright: reportIncompatibleMethodOverride=false, reportIncompatibleVariableOverride=false

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SmartAircoCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Airco sensor entities from a config entry."""
    coordinator: SmartAircoCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = []

    # Add main system sensors
    entities.extend(
        [
            SmartAircoEnergySurplusSensor(coordinator, config_entry),
            SmartAircoPredictedSurplusSensor(coordinator, config_entry),
            SmartAircoTotalConsumptionSensor(coordinator, config_entry),
            SmartAircoRunningCountSensor(coordinator, config_entry),
            SmartAircoSystemStatusSensor(coordinator, config_entry),
        ]
    )

    # Add individual climate entity sensors
    for climate_config in coordinator.climate_entities:
        entity_id = climate_config.get("entity_id")
        if entity_id:
            entities.extend(
                [
                    SmartAircoClimatePowerSensor(
                        coordinator, config_entry, climate_config
                    ),
                    SmartAircoClimateStatusSensor(
                        coordinator, config_entry, climate_config
                    ),
                ]
            )

    async_add_entities(entities)


class SmartAircoBaseSensor(CoordinatorEntity, SensorEntity):
    """Base sensor for Smart Airco integration."""

    def __init__(
        self,
        coordinator: SmartAircoCoordinator,
        config_entry: ConfigEntry,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._sensor_type = sensor_type
        title = config_entry.title if hasattr(config_entry, "title") else "Smart Airco"
        self._attr_name = f"{title} {sensor_type}"
        self._attr_unique_id = (
            f"{config_entry.entry_id}_{sensor_type.lower().replace(' ', '_')}"
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success


class SmartAircoEnergySurplusSensor(SmartAircoBaseSensor):
    """Sensor for current energy surplus."""

    def __init__(
        self, coordinator: SmartAircoCoordinator, config_entry: ConfigEntry
    ) -> None:
        """Initialize the energy surplus sensor."""
        super().__init__(coordinator, config_entry, "Current Surplus")
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_icon = "mdi:solar-power"

    @property
    def native_value(self) -> int | None:
        """Return the current energy surplus."""
        if not self.coordinator.data:
            return None
        calculations = self.coordinator.data.get("calculations", {})
        return calculations.get("current_surplus", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}

        sensors = self.coordinator.data.get("sensors", {})
        return {
            "solar_production": sensors.get("current_production", 0),
            "net_export": sensors.get("net_export", 0),
        }


class SmartAircoPredictedSurplusSensor(SmartAircoBaseSensor):
    """Sensor for predicted energy surplus."""

    def __init__(
        self, coordinator: SmartAircoCoordinator, config_entry: ConfigEntry
    ) -> None:
        """Initialize the predicted surplus sensor."""
        super().__init__(coordinator, config_entry, "Predicted Surplus")
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_icon = "mdi:crystal-ball"

    @property
    def native_value(self) -> int | None:
        """Return the predicted energy surplus."""
        if not self.coordinator.data:
            return None
        calculations = self.coordinator.data.get("calculations", {})
        return calculations.get("predicted_surplus", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}

        sensors = self.coordinator.data.get("sensors", {})
        calculations = self.coordinator.data.get("calculations", {})
        return {
            "solar_forecast": sensors.get("forecast_power", 0),
            "house_consumption": calculations.get("house_consumption_no_ac", 0),
        }


class SmartAircoTotalConsumptionSensor(SmartAircoBaseSensor):
    """Sensor for total AC consumption."""

    def __init__(
        self, coordinator: SmartAircoCoordinator, config_entry: ConfigEntry
    ) -> None:
        """Initialize the total consumption sensor."""
        super().__init__(coordinator, config_entry, "Total AC Consumption")
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_icon = "mdi:air-conditioner"

    @property
    def native_value(self) -> int | None:
        """Return the total AC consumption."""
        if not self.coordinator.data:
            return None
        calculations = self.coordinator.data.get("calculations", {})
        return calculations.get("total_airco_consumption", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}

        sensors = self.coordinator.data.get("sensors", {})
        climate_entities = sensors.get("climate_entities", {})

        # Count running ACs and their power
        running_acs = []
        for entity_id, climate_data in climate_entities.items():
            if climate_data.get("state") == "cool":
                running_acs.append(
                    {
                        "entity_id": entity_id,
                        "name": climate_data.get("name", entity_id),
                        "power": climate_data.get("current_power", 0),
                        "power_source": climate_data.get("power_source", "unknown"),
                    }
                )

        return {
            "running_count": len(running_acs),
            "running_acs": running_acs,
        }


class SmartAircoRunningCountSensor(SmartAircoBaseSensor):
    """Sensor for count of running ACs."""

    def __init__(
        self, coordinator: SmartAircoCoordinator, config_entry: ConfigEntry
    ) -> None:
        """Initialize the running count sensor."""
        super().__init__(coordinator, config_entry, "Running ACs")
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:counter"

    @property
    def native_value(self) -> int | None:
        """Return the count of running ACs."""
        if not self.coordinator.data:
            return None

        sensors = self.coordinator.data.get("sensors", {})
        climate_entities = sensors.get("climate_entities", {})

        return sum(
            1 for climate in climate_entities.values() if climate.get("state") == "cool"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}

        sensors = self.coordinator.data.get("sensors", {})
        climate_entities = sensors.get("climate_entities", {})

        return {
            "total_entities": len(climate_entities),
            "enabled_entities": sum(
                1 for c in climate_entities.values() if c.get("enabled", True)
            ),
            "available_entities": sum(
                1 for c in climate_entities.values() if c.get("can_run", False)
            ),
        }


class SmartAircoSystemStatusSensor(SmartAircoBaseSensor):
    """Sensor for system status."""

    def __init__(
        self, coordinator: SmartAircoCoordinator, config_entry: ConfigEntry
    ) -> None:
        """Initialize the system status sensor."""
        super().__init__(coordinator, config_entry, "System Status")
        self._attr_icon = "mdi:information"

    @property
    def native_value(self) -> str | None:
        """Return the system status."""
        if not self.coordinator.data:
            return "unknown"

        decisions = self.coordinator.data.get("decisions", {})
        return decisions.get("reason", "unknown")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}

        decisions = self.coordinator.data.get("decisions", {})
        return {
            "available_surplus": decisions.get("available_surplus", 0),
            "total_power_needed": decisions.get("total_power_needed", 0),
            "critical_input_errors": decisions.get("critical_input_errors", []),
            "last_update": self.coordinator.data.get("last_update"),
        }


class SmartAircoClimatePowerSensor(SmartAircoBaseSensor):
    """Sensor for individual climate entity power consumption."""

    def __init__(
        self,
        coordinator: SmartAircoCoordinator,
        config_entry: ConfigEntry,
        climate_config: dict,
    ) -> None:
        """Initialize the climate power sensor."""
        self.climate_config = climate_config
        entity_id = climate_config.get("entity_id", "unknown")
        climate_name = climate_config.get("name", entity_id.split(".")[-1])

        super().__init__(coordinator, config_entry, f"{climate_name} Power")
        self._attr_unique_id = (
            f"{config_entry.entry_id}_{entity_id.replace('.', '_')}_power"
        )
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_icon = "mdi:lightning-bolt"

    @property
    def native_value(self) -> int | None:
        """Return the climate entity power consumption."""
        if not self.coordinator.data:
            return None

        entity_id = self.climate_config.get("entity_id")
        if not isinstance(entity_id, str):
            return None
        sensors = self.coordinator.data.get("sensors", {})
        climate_entities = sensors.get("climate_entities", {})
        climate_data = climate_entities.get(entity_id, {})

        # Return actual power only if AC is running
        if climate_data.get("state") == "cool":
            return climate_data.get("current_power", 0)
        return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}

        entity_id = self.climate_config.get("entity_id")
        if not isinstance(entity_id, str):
            return {}
        sensors = self.coordinator.data.get("sensors", {})
        climate_entities = sensors.get("climate_entities", {})
        climate_data = climate_entities.get(entity_id, {})

        decisions = self.coordinator.data.get("decisions", {})
        climate_decision = decisions.get("climate_decisions", {}).get(entity_id, {})

        return {
            "entity_id": entity_id,
            "state": climate_data.get("state", "unknown"),
            "power_source": climate_data.get("power_source", "unknown"),
            "estimated_power": self.climate_config.get("wattage", 0),
            "priority": climate_data.get("priority", 999),
            "should_cool": climate_decision.get("should_cool", False),
            "decision_reason": climate_decision.get("reason", "unknown"),
        }


class SmartAircoClimateStatusSensor(SmartAircoBaseSensor):
    """Sensor for individual climate entity status."""

    def __init__(
        self,
        coordinator: SmartAircoCoordinator,
        config_entry: ConfigEntry,
        climate_config: dict,
    ) -> None:
        """Initialize the climate status sensor."""
        self.climate_config = climate_config
        entity_id = climate_config.get("entity_id", "unknown")
        climate_name = climate_config.get("name", entity_id.split(".")[-1])

        super().__init__(coordinator, config_entry, f"{climate_name} Status")
        self._attr_unique_id = (
            f"{config_entry.entry_id}_{entity_id.replace('.', '_')}_status"
        )
        self._attr_icon = "mdi:thermostat"

    @property
    def native_value(self) -> str | None:
        """Return the climate entity status."""
        if not self.coordinator.data:
            return "unknown"

        entity_id = self.climate_config.get("entity_id")
        if not isinstance(entity_id, str):
            return "unknown"
        sensors = self.coordinator.data.get("sensors", {})
        climate_entities = sensors.get("climate_entities", {})
        climate_data = climate_entities.get(entity_id, {})
        decisions = self.coordinator.data.get("decisions", {})
        climate_decision = decisions.get("climate_decisions", {}).get(entity_id, {})

        if climate_data.get("state") == "cool":
            return "cooling"
        else:
            reason = climate_decision.get("reason", "unknown")
            if "windows_open" in reason:
                return "windows_open"
            elif "manual_override" in reason:
                return "manual_override"
            elif "disabled" in reason:
                return "disabled"
            elif "unavailable" in reason:
                return "unavailable"
            elif "insufficient" in reason:
                return "insufficient_power"
            else:
                return "idle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}

        entity_id = self.climate_config.get("entity_id")
        if not isinstance(entity_id, str):
            return {}
        sensors = self.coordinator.data.get("sensors", {})
        climate_entities = sensors.get("climate_entities", {})
        climate_data = climate_entities.get(entity_id, {})

        decisions = self.coordinator.data.get("decisions", {})
        climate_decision = decisions.get("climate_decisions", {}).get(entity_id, {})

        # Get current temperature from the actual climate entity
        climate_state = self.coordinator.hass.states.get(entity_id)
        current_temp = None
        target_temp = None
        if climate_state:
            current_temp = climate_state.attributes.get("current_temperature")
            target_temp = climate_state.attributes.get("temperature")

        return {
            "entity_id": entity_id,
            "enabled": climate_data.get("enabled", True),
            "manual_override": climate_data.get("manual_override", False),
            "priority": climate_data.get("priority", 999),
            "windows_open": climate_data.get("windows_open", False),
            "can_run": climate_data.get("can_run", False),
            "hvac_state": climate_data.get("state", "unknown"),
            "current_temperature": current_temp,
            "target_temperature": target_temp,
            "decision_reason": climate_decision.get("reason", "unknown"),
            "power_consumption": climate_data.get("current_power", 0),
        }
