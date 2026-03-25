"""Climate platform for Smart Airco integration."""

from __future__ import annotations

# pyright: reportIncompatibleMethodOverride=false, reportIncompatibleVariableOverride=false

import logging
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    HVACAction,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_CONTROLLER_ENABLED,
    CONF_CONTROLLER_HVAC_MODE,
    CONF_CONTROLLER_TARGET_TEMPERATURE,
    DOMAIN,
    DEFAULT_CONTROLLER_HVAC_MODE,
    DEFAULT_CONTROLLER_TARGET_TEMPERATURE,
    ENTITY_SMART_CONTROLLER,
    CONF_SOLAR_FORECAST_SENSOR,
    CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_NET_EXPORT_SENSOR,
)
from .coordinator import SmartAircoCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Airco climate entities from a config entry."""
    coordinator: SmartAircoCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Create the main smart controller entity
    entities = [SmartAircoClimateEntity(coordinator, config_entry)]

    async_add_entities(entities)


class SmartAircoClimateEntity(CoordinatorEntity, ClimateEntity):
    """Smart Airco Climate Controller Entity."""

    def __init__(
        self, coordinator: SmartAircoCoordinator, config_entry: ConfigEntry
    ) -> None:
        """Initialize the Smart Airco climate entity."""
        super().__init__(coordinator)
        self.coordinator: SmartAircoCoordinator = coordinator
        self.config_entry = config_entry
        title = config_entry.title if hasattr(config_entry, "title") else "Smart Airco"
        self._attr_name = f"{title} Controller"
        self._attr_unique_id = f"{config_entry.entry_id}_{ENTITY_SMART_CONTROLLER}"

        # Climate entity configuration
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT]
        self._attr_supported_features = (
            ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TARGET_TEMPERATURE
        )
        self._attr_target_temperature_step = 0.5
        self._controller_mode = config_entry.data.get(
            CONF_CONTROLLER_HVAC_MODE, DEFAULT_CONTROLLER_HVAC_MODE
        )
        self._enabled = config_entry.data.get(CONF_CONTROLLER_ENABLED, True)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        return self._controller_mode if self._enabled else HVACMode.OFF

    @property
    def hvac_action(self) -> str | None:
        """Return current HVAC action."""
        if not self._enabled:
            return HVACAction.OFF

        if not self.coordinator.data:
            return HVACAction.IDLE

        sensor_data = self.coordinator.data.get("sensors", {})
        climate_entities = sensor_data.get("climate_entities", {})

        running_count = sum(
            1
            for climate in climate_entities.values()
            if climate.get("state") == self._controller_mode
        )

        if running_count > 0:
            return (
                HVACAction.HEATING
                if self._controller_mode == HVACMode.HEAT
                else HVACAction.COOLING
            )
        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        """Return current temperature (average of all climate entities)."""
        if not self.coordinator.data:
            return None

        temperatures = []
        for entity_id in self._controller_selected_entity_ids():
            # Get temperature from the actual climate entity
            climate_state = self.coordinator.hass.states.get(entity_id)
            if climate_state and climate_state.attributes.get("current_temperature"):
                try:
                    temp = float(climate_state.attributes["current_temperature"])
                    temperatures.append(temp)
                except (ValueError, TypeError):
                    continue

        return sum(temperatures) / len(temperatures) if temperatures else None

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature (average of all climate entities)."""
        configured_target = self.config_entry.data.get(
            CONF_CONTROLLER_TARGET_TEMPERATURE, DEFAULT_CONTROLLER_TARGET_TEMPERATURE
        )
        if configured_target is not None:
            try:
                return float(configured_target)
            except (TypeError, ValueError):
                return None

        temperatures = []
        for entity_id in self._controller_selected_entity_ids():
            # Get target temperature from the actual climate entity
            climate_state = self.coordinator.hass.states.get(entity_id)
            if climate_state and climate_state.attributes.get("temperature"):
                try:
                    temp = float(climate_state.attributes["temperature"])
                    temperatures.append(temp)
                except (ValueError, TypeError):
                    continue

        return sum(temperatures) / len(temperatures) if temperatures else None

    @property
    def min_temp(self) -> float:
        """Return the minimum supported controller temperature."""
        min_values = []
        for entity_id in self._controller_selected_entity_ids():
            climate_state = self.coordinator.hass.states.get(entity_id)
            if climate_state is None:
                continue
            try:
                min_values.append(float(climate_state.attributes.get("min_temp", 16.0)))
            except (TypeError, ValueError):
                continue
        return min(min_values) if min_values else 10.0

    @property
    def max_temp(self) -> float:
        """Return the maximum supported controller temperature."""
        max_values = []
        for entity_id in self._controller_selected_entity_ids():
            climate_state = self.coordinator.hass.states.get(entity_id)
            if climate_state is None:
                continue
            try:
                max_values.append(float(climate_state.attributes.get("max_temp", 35.0)))
            except (TypeError, ValueError):
                continue
        return max(max_values) if max_values else 35.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}

        sensors = self.coordinator.data.get("sensors", {})
        calculations = self.coordinator.data.get("calculations", {})
        decisions = self.coordinator.data.get("decisions", {})
        climate_entities = sensors.get("climate_entities", {})
        raw_update_interval = self.coordinator.config.get("update_interval", 300)
        update_interval_seconds = (
            int(raw_update_interval.total_seconds())
            if hasattr(raw_update_interval, "total_seconds")
            else int(raw_update_interval)
        )

        # Count climate entities by status
        enabled_count = sum(
            1 for c in climate_entities.values() if c.get("enabled", True)
        )
        manual_override_count = sum(
            1 for c in climate_entities.values() if c.get("manual_override", False)
        )
        running_count = sum(
            1
            for climate in climate_entities.values()
            if climate.get("state") == self._controller_mode
        )
        available_count = sum(
            1 for c in climate_entities.values() if c.get("can_run", False)
        )

        attributes = {
            "smart_airco_controller": True,
            "smart_airco_entry_id": self.config_entry.entry_id,
            # System status
            "controller_enabled": self._enabled,
            "controller_hvac_mode": self._controller_mode,
            "controller_target_temperature": self.target_temperature,
            "total_climate_entities": len(climate_entities),
            "enabled_entities": enabled_count,
            "manual_override_entities": manual_override_count,
            "available_entities": available_count,
            "running_entities": running_count,
            # Energy data
            "solar_forecast": sensors.get("forecast_power", 0),
            "solar_production": sensors.get("current_production", 0),
            "net_export": sensors.get("net_export", 0),
            # Configured sensor entity IDs for UI logic
            "forecast_sensor": self.coordinator.config.get(CONF_SOLAR_FORECAST_SENSOR),
            "production_sensor": self.coordinator.config.get(
                CONF_SOLAR_PRODUCTION_SENSOR
            ),
            "net_export_sensor": self.coordinator.config.get(CONF_NET_EXPORT_SENSOR),
            "predicted_surplus": calculations.get("predicted_surplus", 0),
            "current_surplus": calculations.get("current_surplus", 0),
            "total_ac_consumption": calculations.get("total_airco_consumption", 0),
            "critical_inputs_valid": calculations.get("critical_inputs_valid", True),
            "critical_input_errors": calculations.get("critical_input_errors", []),
            # Update interval
            "update_interval_seconds": update_interval_seconds,
            "update_interval_minutes": int(update_interval_seconds / 60),
            # Decision info
            "decision_reason": decisions.get("reason", "unknown"),
            "total_power_needed": decisions.get("total_power_needed", 0),
            "last_update": self.coordinator.data.get("last_update"),
            "configured_climate_entity_ids": sorted(climate_entities.keys()),
            "managed_climates": [],
        }

        # Add individual climate entity status
        for entity_id, climate_data in climate_entities.items():
            entity_name = climate_data.get("name", entity_id.split(".")[-1])
            safe_name = entity_id.replace(".", "_").replace("-", "_")

            decision = decisions.get("climate_decisions", {}).get(entity_id, {})
            cfg = climate_data.get("config", {})
            managed_climate = {
                "name": entity_name,
                "entity_id": entity_id,
                "enabled": climate_data.get("enabled", True),
                "state": climate_data.get("state", "unknown"),
                "power": climate_data.get("current_power", 0),
                "power_source": climate_data.get("power_source", "unknown"),
                "manual_override": climate_data.get("manual_override", False),
                "use_estimated_power": cfg.get("use_estimated_power", True),
                "estimated_wattage": cfg.get("wattage", 0),
                "power_sensor": cfg.get("power_sensor"),
                "windows_open": climate_data.get("windows_open", False),
                "window_sensors": cfg.get("window_sensors", []),
                "should_cool": decision.get("should_cool", False),
                "reason": decision.get("reason", "unknown"),
                "priority": climate_data.get("priority", 999),
            }
            attributes["managed_climates"].append(managed_climate)

            attributes.update(
                {
                    f"{safe_name}_display_name": entity_name,
                    f"{safe_name}_enabled": climate_data.get("enabled", True),
                    f"{safe_name}_state": climate_data.get("state", "unknown"),
                    f"{safe_name}_power": climate_data.get("current_power", 0),
                    f"{safe_name}_power_source": climate_data.get(
                        "power_source", "unknown"
                    ),
                    f"{safe_name}_manual_override": climate_data.get(
                        "manual_override", False
                    ),
                    f"{safe_name}_use_estimated_power": cfg.get(
                        "use_estimated_power", True
                    ),
                    f"{safe_name}_estimated_wattage": cfg.get("wattage", 0),
                    f"{safe_name}_power_sensor": cfg.get("power_sensor"),
                    f"{safe_name}_windows_open": climate_data.get(
                        "windows_open", False
                    ),
                    f"{safe_name}_window_sensors": cfg.get("window_sensors", []),
                    f"{safe_name}_should_cool": decision.get("should_cool", False),
                    f"{safe_name}_reason": decision.get("reason", "unknown"),
                    f"{safe_name}_priority": climate_data.get("priority", 999),
                    f"{safe_name}_entity_id": entity_id,
                }
            )

        return attributes

    def _controller_selected_entity_ids(self) -> list[str]:
        """Return climate entity IDs selected for controller management."""
        climate_entities = self.coordinator.config.get("climate_entities", [])
        selected_entity_ids = [
            config.get("entity_id")
            for config in climate_entities
            if config.get("enabled", True) and isinstance(config.get("entity_id"), str)
        ]
        if selected_entity_ids:
            return selected_entity_ids

        return [
            config.get("entity_id")
            for config in climate_entities
            if isinstance(config.get("entity_id"), str)
        ]

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        if hvac_mode in (HVACMode.COOL, HVACMode.HEAT):
            self._enabled = True
            self._controller_mode = hvac_mode
            self.coordinator.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    CONF_CONTROLLER_ENABLED: True,
                    CONF_CONTROLLER_HVAC_MODE: hvac_mode,
                },
            )
            _LOGGER.info("Smart Airco Controller enabled in %s mode", hvac_mode)
            # Trigger immediate evaluation
            await self.coordinator.async_request_refresh()
        elif hvac_mode == HVACMode.OFF:
            self._enabled = False
            self.coordinator.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    CONF_CONTROLLER_ENABLED: False,
                    CONF_CONTROLLER_HVAC_MODE: self._controller_mode,
                },
            )
            _LOGGER.info("Smart Airco Controller disabled")
            # Turn off all managed ACs
            await self._turn_off_all_acs()

        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the shared controller target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            return

        try:
            temperature = float(kwargs[ATTR_TEMPERATURE])
        except (TypeError, ValueError):
            return

        self.coordinator.hass.config_entries.async_update_entry(
            self.config_entry,
            data={
                **self.config_entry.data,
                CONF_CONTROLLER_ENABLED: self._enabled,
                CONF_CONTROLLER_HVAC_MODE: self._controller_mode,
                CONF_CONTROLLER_TARGET_TEMPERATURE: temperature,
            },
        )

        if self.coordinator.data:
            sensor_data = self.coordinator.data.get("sensors", {})
            climate_entities = sensor_data.get("climate_entities", {})
            for entity_id in self._controller_selected_entity_ids():
                climate_data = climate_entities.get(entity_id, {})
                if climate_data.get("state") == self._controller_mode:
                    await self.coordinator.async_set_climate_temperature(
                        entity_id, temperature
                    )

        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        """Turn on the Smart Airco controller."""
        await self.async_set_hvac_mode(self._controller_mode)

    async def async_turn_off(self) -> None:
        """Turn off the Smart Airco controller."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def _turn_off_all_acs(self) -> None:
        """Turn off all managed AC units."""
        if not self.coordinator.data:
            return

        sensor_data = self.coordinator.data.get("sensors", {})
        climate_entities = sensor_data.get("climate_entities", {})

        for entity_id, climate_data in climate_entities.items():
            if climate_data.get("state") not in ("off", "unknown"):
                _LOGGER.info("Turning off %s (controller disabled)", entity_id)
                await self.coordinator.async_set_climate_mode(
                    entity_id,
                    "off",
                    track_for_antichatter=False,
                )

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

        # Start automatic execution of decisions
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator updates and execute decisions if enabled.

        Note: Coordinator listeners are synchronous callbacks. Schedule any
        async work on the Home Assistant loop instead of awaiting here.
        """
        self._controller_mode = self.config_entry.data.get(
            CONF_CONTROLLER_HVAC_MODE, DEFAULT_CONTROLLER_HVAC_MODE
        )

        if self._enabled and self.coordinator.data:
            # Schedule execution of decisions without blocking the callback
            self.coordinator.hass.async_create_task(
                self.coordinator.async_execute_decisions()
            )

        self.async_write_ha_state()
