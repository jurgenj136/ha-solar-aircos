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
    ATTR_SMART_AIRCO_ACTIVE,
    ATTR_SMART_AIRCO_ENTRY_ID,
    ATTR_SMART_AIRCO_HVAC_MODE,
    ATTR_SMART_AIRCO_MANAGED,
    ATTR_SMART_AIRCO_PRESET_MODE,
    ATTR_SMART_AIRCO_SOLAR_AUTOMATION_ENABLED,
    ATTR_SMART_AIRCO_SOURCE_ENTITY_ID,
    ATTR_SMART_AIRCO_TARGET_TEMPERATURE,
    CONF_CLIMATE_ENABLED,
    CONF_CLIMATE_ENTITIES,
    CONF_CLIMATE_ENTITY_ID,
    CONF_CLIMATE_HVAC_MODE,
    CONF_CLIMATE_MANUAL_OVERRIDE,
    CONF_CLIMATE_NAME,
    CONF_CLIMATE_PRESET_MODE,
    CONF_CLIMATE_PRIORITY,
    CONF_CLIMATE_TARGET_TEMPERATURE,
    CONF_CLIMATE_WATTAGE,
    CONF_CLIMATE_POWER_SENSOR,
    CONF_CLIMATE_USE_ESTIMATED_POWER,
    CONF_CLIMATE_WINDOW_SENSORS,
    DEFAULT_CLIMATE_HVAC_MODE,
    DEFAULT_CLIMATE_PRESET_MODE,
    DEFAULT_CLIMATE_TARGET_TEMPERATURE,
    DOMAIN,
    PRESET_OFF,
    PRESET_ON,
    PRESET_SOLAR_BASED,
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

    entities = [
        SmartAircoManagedClimateEntity(coordinator, config_entry, climate_config)
        for climate_config in coordinator.climate_entities
        if isinstance(climate_config.get(CONF_CLIMATE_ENTITY_ID), str)
    ]

    async_add_entities(entities)


class SmartAircoManagedClimateEntity(CoordinatorEntity, ClimateEntity):
    """Smart Airco companion climate entity for one managed climate."""

    def __init__(
        self,
        coordinator: SmartAircoCoordinator,
        config_entry: ConfigEntry,
        climate_config: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self.coordinator: SmartAircoCoordinator = coordinator
        self.config_entry = config_entry
        self._source_entity_id = climate_config[CONF_CLIMATE_ENTITY_ID]
        base_name = climate_config.get(
            CONF_CLIMATE_NAME,
            self._source_entity_id.split(".")[-1].replace("_", " ").title(),
        )
        self._attr_name = f"{base_name} Smart Airco"
        self._attr_unique_id = f"{config_entry.entry_id}_{self._source_entity_id.replace('.', '_')}_smart_airco"
        self._attr_translation_key = "managed_climate"
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_modes = self._homeassistant_hvac_modes()
        self._attr_preset_modes = [PRESET_OFF, PRESET_ON, PRESET_SOLAR_BASED]
        self._attr_supported_features = (
            ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.PRESET_MODE
        )
        self._attr_target_temperature_step = 0.5

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    def _config(self) -> dict[str, Any]:
        for climate_config in self.coordinator.config.get(CONF_CLIMATE_ENTITIES, []):
            if climate_config.get(CONF_CLIMATE_ENTITY_ID) == self._source_entity_id:
                return climate_config
        return {CONF_CLIMATE_ENTITY_ID: self._source_entity_id}

    def _runtime(self) -> dict[str, Any]:
        sensors = (
            self.coordinator.data.get("sensors", {}) if self.coordinator.data else {}
        )
        return sensors.get("climate_entities", {}).get(self._source_entity_id, {})

    def _desired_hvac_mode(self) -> str:
        return self._config().get(CONF_CLIMATE_HVAC_MODE, DEFAULT_CLIMATE_HVAC_MODE)

    def _supported_hvac_modes(self) -> list[str]:
        return self.coordinator.supported_hvac_modes(self._source_entity_id)

    def _homeassistant_hvac_modes(self) -> list[HVACMode]:
        return [
            HVACMode.OFF,
            *(HVACMode(mode) for mode in self._supported_hvac_modes()),
        ]

    def _preset_mode(self) -> str:
        value = self._config().get(
            CONF_CLIMATE_PRESET_MODE, DEFAULT_CLIMATE_PRESET_MODE
        )
        return value if isinstance(value, str) else DEFAULT_CLIMATE_PRESET_MODE

    def _active(self) -> bool:
        return self._preset_mode() != PRESET_OFF

    @property
    def hvac_mode(self) -> HVACMode:
        """Return desired Smart Airco HVAC mode for this climate."""
        if self._preset_mode() == PRESET_OFF:
            return HVACMode.OFF
        return HVACMode(self._desired_hvac_mode())

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return supported Smart Airco HVAC modes for this climate."""
        return self._homeassistant_hvac_modes()

    @property
    def preset_mode(self) -> str | None:
        """Return Smart Airco participation state."""
        return self._preset_mode()

    @property
    def hvac_action(self) -> str | None:
        """Return current Smart Airco action for this climate."""
        if not self._active():
            return HVACAction.OFF

        runtime = self._runtime()
        current_state = runtime.get("state")
        desired_mode = self._desired_hvac_mode()
        if self._preset_mode() == PRESET_OFF:
            return HVACAction.OFF
        if current_state == desired_mode:
            if desired_mode == HVACMode.HEAT:
                return HVACAction.HEATING
            if desired_mode == HVACMode.COOL:
                return HVACAction.COOLING
            if desired_mode == HVACMode.DRY:
                return HVACAction.DRYING
            if desired_mode == HVACMode.FAN_ONLY:
                return HVACAction.FAN
        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        """Return current temperature from the underlying climate."""
        climate_state = self.coordinator.hass.states.get(self._source_entity_id)
        if climate_state is None:
            return None
        try:
            value = climate_state.attributes.get("current_temperature")
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    @property
    def target_temperature(self) -> float | None:
        """Return Smart Airco target temperature for this climate."""
        configured = self._config().get(
            CONF_CLIMATE_TARGET_TEMPERATURE, DEFAULT_CLIMATE_TARGET_TEMPERATURE
        )
        if configured is not None:
            try:
                return float(configured)
            except (TypeError, ValueError):
                return None

        climate_state = self.coordinator.hass.states.get(self._source_entity_id)
        if climate_state is None:
            return None
        try:
            value = climate_state.attributes.get("temperature")
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    @property
    def min_temp(self) -> float:
        """Return min temperature based on the underlying climate."""
        climate_state = self.coordinator.hass.states.get(self._source_entity_id)
        if climate_state is None:
            return 10.0
        try:
            return float(climate_state.attributes.get("min_temp", 10.0))
        except (TypeError, ValueError):
            return 10.0

    @property
    def max_temp(self) -> float:
        """Return max temperature based on the underlying climate."""
        climate_state = self.coordinator.hass.states.get(self._source_entity_id)
        if climate_state is None:
            return 35.0
        try:
            return float(climate_state.attributes.get("max_temp", 35.0))
        except (TypeError, ValueError):
            return 35.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return Smart Airco specific attributes for this climate."""
        config = self._config()
        runtime = self._runtime()
        decisions = (
            self.coordinator.data.get("decisions", {}) if self.coordinator.data else {}
        )
        decision = decisions.get("climate_decisions", {}).get(
            self._source_entity_id, {}
        )
        return {
            ATTR_SMART_AIRCO_MANAGED: True,
            ATTR_SMART_AIRCO_ENTRY_ID: self.config_entry.entry_id,
            ATTR_SMART_AIRCO_SOURCE_ENTITY_ID: self._source_entity_id,
            ATTR_SMART_AIRCO_ACTIVE: self._active(),
            ATTR_SMART_AIRCO_PRESET_MODE: self._preset_mode(),
            ATTR_SMART_AIRCO_HVAC_MODE: self._desired_hvac_mode(),
            ATTR_SMART_AIRCO_TARGET_TEMPERATURE: self.target_temperature,
            ATTR_SMART_AIRCO_SOLAR_AUTOMATION_ENABLED: (
                self._preset_mode() == PRESET_SOLAR_BASED
            ),
            "supported_hvac_modes": self._supported_hvac_modes(),
            "priority": config.get(CONF_CLIMATE_PRIORITY, 999),
            "manual_override": config.get(CONF_CLIMATE_MANUAL_OVERRIDE, False),
            "windows_open": runtime.get("windows_open", False),
            "power_source": runtime.get("power_source", "unknown"),
            "estimated_wattage": config.get(CONF_CLIMATE_WATTAGE, 0),
            "power_sensor": config.get(CONF_CLIMATE_POWER_SENSOR),
            "use_estimated_power": config.get(CONF_CLIMATE_USE_ESTIMATED_POWER, True),
            "window_sensors": config.get(CONF_CLIMATE_WINDOW_SENSORS, []),
            "decision_reason": decision.get("reason", "unknown"),
            "should_run": decision.get("should_cool", False),
        }

    async def _async_update_config(self, **updates: Any) -> None:
        climate_entities = []
        changed = False

        for climate_config in self.coordinator.config.get(CONF_CLIMATE_ENTITIES, []):
            updated = dict(climate_config)
            if updated.get(CONF_CLIMATE_ENTITY_ID) == self._source_entity_id:
                updated.update(updates)
                changed = True
            climate_entities.append(updated)

        if not changed:
            return

        self.coordinator.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, CONF_CLIMATE_ENTITIES: climate_entities},
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set Smart Airco desired HVAC mode for this climate."""
        if hvac_mode == HVACMode.OFF:
            await self.async_set_preset_mode(PRESET_OFF)
            return

        if hvac_mode not in self._supported_hvac_modes():
            return

        await self._async_update_config(**{CONF_CLIMATE_HVAC_MODE: hvac_mode})
        if self._preset_mode() == PRESET_OFF:
            await self.async_set_preset_mode(PRESET_ON)
            return

        if self._preset_mode() == PRESET_ON:
            await self.coordinator.async_set_climate_mode(
                self._source_entity_id, hvac_mode
            )
            if self.target_temperature is not None:
                await self.coordinator.async_set_climate_temperature(
                    self._source_entity_id, self.target_temperature
                )
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set Smart Airco participation state for this climate."""
        if preset_mode not in (PRESET_OFF, PRESET_ON, PRESET_SOLAR_BASED):
            return

        enabled = preset_mode != PRESET_OFF
        await self._async_update_config(
            **{
                CONF_CLIMATE_ENABLED: enabled,
                CONF_CLIMATE_PRESET_MODE: preset_mode,
                CONF_CLIMATE_MANUAL_OVERRIDE: False,
            }
        )
        if preset_mode == PRESET_OFF:
            await self.coordinator.async_set_climate_mode(
                self._source_entity_id,
                HVACMode.OFF,
                track_for_antichatter=False,
            )
        elif preset_mode == PRESET_ON:
            await self.coordinator.async_set_climate_mode(
                self._source_entity_id,
                self._desired_hvac_mode(),
                track_for_antichatter=False,
            )
            if self.target_temperature is not None:
                await self.coordinator.async_set_climate_temperature(
                    self._source_entity_id, self.target_temperature
                )
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set Smart Airco target temperature for this climate."""
        if ATTR_TEMPERATURE not in kwargs:
            return
        try:
            temperature = float(kwargs[ATTR_TEMPERATURE])
        except (TypeError, ValueError):
            return

        await self._async_update_config(
            **{CONF_CLIMATE_TARGET_TEMPERATURE: temperature}
        )
        runtime = self._runtime()
        if self._preset_mode() == PRESET_ON or (
            self._preset_mode() == PRESET_SOLAR_BASED
            and runtime.get("state") == self._desired_hvac_mode()
        ):
            await self.coordinator.async_set_climate_temperature(
                self._source_entity_id, temperature
            )
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        """Turn on Smart Airco participation for this climate."""
        await self.async_set_preset_mode(PRESET_ON)

    async def async_turn_off(self) -> None:
        """Turn off Smart Airco participation for this climate."""
        await self.async_set_preset_mode(PRESET_OFF)
