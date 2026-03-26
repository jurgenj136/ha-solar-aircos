"""DataUpdateCoordinator for Smart Airco integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from datetime import datetime, timedelta
from time import monotonic
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.components.climate.const import HVACMode
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CLIMATE_ENTITIES,
    CONF_CLIMATE_ENTITY_ID,
    CONF_CLIMATE_ENABLED,
    CONF_CLIMATE_HVAC_MODE,
    CONF_CLIMATE_MANUAL_OVERRIDE,
    CONF_CLIMATE_NAME,
    CONF_CLIMATE_POWER_SENSOR,
    CONF_CLIMATE_PRESET_MODE,
    CONF_CLIMATE_PRIORITY,
    CONF_CLIMATE_TARGET_TEMPERATURE,
    CONF_CLIMATE_USE_ESTIMATED_POWER,
    CONF_CLIMATE_WATTAGE,
    CONF_CLIMATE_WINDOW_SENSORS,
    CONF_NET_EXPORT_SENSOR,
    CONF_SOLAR_FORECAST_SENSOR,
    CONF_SOLAR_PRODUCTION_SENSOR,
    DEFAULT_CLIMATE_HVAC_MODE,
    DEFAULT_CLIMATE_PRESET_MODE,
    DEFAULT_CLIMATE_TARGET_TEMPERATURE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    PRESET_OFF,
    PRESET_ON,
    PRESET_SOLAR_BASED,
)

_LOGGER = logging.getLogger(__name__)
_EXPECTED_HVAC_CHANGE_TTL_SECONDS = 30.0
_LIVE_SENSOR_STALE_MINUTES = 15
_FORECAST_SENSOR_STALE_HOURS = 12
_MINIMUM_RUN_TIME = timedelta(minutes=15)
_MINIMUM_OFF_TIME = timedelta(minutes=10)
_SURPLUS_HYSTERESIS_WATTS = 150
_MANUAL_OVERRIDE_ATTRIBUTES = {
    "temperature",
    "target_temp_high",
    "target_temp_low",
    "preset_mode",
    "fan_mode",
    "swing_mode",
    "swing_horizontal_mode",
    "humidity",
}


class SmartAircoCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Smart Airco data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self._pending_hvac_changes: dict[str, dict[str, Any]] = {}
        self._recent_hvac_changes: dict[str, tuple[str, datetime]] = {}

        # Normalize update_interval (supports timedelta or seconds as int)
        raw_interval = entry.data.get("update_interval", DEFAULT_UPDATE_INTERVAL)
        if isinstance(raw_interval, (int, float)):
            normalized_interval = timedelta(seconds=int(raw_interval))
        elif isinstance(raw_interval, timedelta):
            normalized_interval = raw_interval
        else:
            normalized_interval = DEFAULT_UPDATE_INTERVAL

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=normalized_interval,
        )

    @property
    def config(self) -> Mapping[str, Any]:
        """Return the latest config entry data."""
        return cast(Mapping[str, Any], self.entry.data)

    @property
    def climate_entities(self) -> list[dict[str, Any]]:
        """Get the configured climate entities."""
        return self.config.get(CONF_CLIMATE_ENTITIES, [])

    def climate_hvac_mode(self, climate_config: Mapping[str, Any]) -> str:
        """Return the configured Smart Airco HVAC mode for one climate."""
        value = climate_config.get(CONF_CLIMATE_HVAC_MODE, DEFAULT_CLIMATE_HVAC_MODE)
        return value if isinstance(value, str) else DEFAULT_CLIMATE_HVAC_MODE

    def climate_target_temperature(
        self, climate_config: Mapping[str, Any]
    ) -> float | None:
        """Return the configured Smart Airco target temperature for one climate."""
        value = climate_config.get(
            CONF_CLIMATE_TARGET_TEMPERATURE, DEFAULT_CLIMATE_TARGET_TEMPERATURE
        )
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def climate_preset_mode(self, climate_config: Mapping[str, Any]) -> str:
        """Return the configured Smart Airco preset mode for one climate."""
        value = climate_config.get(
            CONF_CLIMATE_PRESET_MODE, DEFAULT_CLIMATE_PRESET_MODE
        )
        return value if isinstance(value, str) else DEFAULT_CLIMATE_PRESET_MODE

    @callback
    def async_setup_manual_override_tracking(self):
        """Track state changes on managed climates to detect manual overrides."""
        entity_ids: list[str] = []
        for climate_config in self.climate_entities:
            entity_id = climate_config.get(CONF_CLIMATE_ENTITY_ID)
            if isinstance(entity_id, str):
                entity_ids.append(entity_id)
        if not entity_ids:
            return lambda: None

        tracked_entity_ids: tuple[str, ...] = tuple(entity_ids)
        return async_track_state_change_event(
            self.hass,
            tracked_entity_ids,
            self._handle_managed_climate_state_change,
        )

    @callback
    def _handle_managed_climate_state_change(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Disable automation when a managed climate changes outside the coordinator."""
        entity_id = event.data.get("entity_id")
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")

        if not entity_id or old_state is None or new_state is None:
            return
        if self._consume_expected_hvac_change(entity_id, new_state):
            return
        if not self._is_manual_override_change(old_state, new_state):
            return

        climate_config = next(
            (
                config
                for config in self.climate_entities
                if config.get(CONF_CLIMATE_ENTITY_ID) == entity_id
            ),
            None,
        )
        if climate_config is None:
            return

        self.hass.async_create_task(
            self.async_disable_climate_automation_for_manual_override(
                entity_id,
                old_state.state,
                new_state.state,
            )
        )

    def _is_manual_override_change(self, old_state: State, new_state: State) -> bool:
        """Return True when a climate change likely reflects user intent."""
        if old_state.state != new_state.state:
            return True

        for attribute in _MANUAL_OVERRIDE_ATTRIBUTES:
            if old_state.attributes.get(attribute) != new_state.attributes.get(
                attribute
            ):
                return True

        return False

    @callback
    def _consume_expected_hvac_change(self, entity_id: str, new_state: State) -> bool:
        """Return True if the state change matches a recent coordinator command."""
        pending = self._pending_hvac_changes.get(entity_id)
        if pending is None:
            return False

        expires_at = pending.get("expires_at", 0.0)
        if monotonic() > expires_at:
            self._pending_hvac_changes.pop(entity_id, None)
            return False

        matched = False
        expected_state = pending.get("expected_state")
        if expected_state is not None and new_state.state == expected_state:
            matched = True
            pending.pop("expected_state", None)
            if pending.get("track_for_antichatter", False):
                self._recent_hvac_changes[entity_id] = (
                    new_state.state,
                    dt_util.utcnow(),
                )

        expected_temperature = pending.get("expected_temperature")
        if expected_temperature is not None:
            try:
                current_temperature = float(new_state.attributes.get("temperature"))
            except (TypeError, ValueError):
                current_temperature = None

            if (
                current_temperature is not None
                and abs(current_temperature - float(expected_temperature)) < 0.25
            ):
                matched = True
                pending.pop("expected_temperature", None)

        if (
            not pending.get("expected_state")
            and pending.get("expected_temperature") is None
        ):
            self._pending_hvac_changes.pop(entity_id, None)
        else:
            self._pending_hvac_changes[entity_id] = pending

        return matched

    def _remember_expected_climate_change(
        self,
        entity_id: str,
        *,
        expected_state: str | None = None,
        expected_temperature: float | None = None,
        track_for_antichatter: bool = True,
    ) -> None:
        """Track an expected coordinator-driven climate change."""
        pending = self._pending_hvac_changes.get(entity_id, {})
        if expected_state is not None:
            pending["expected_state"] = expected_state
        if expected_temperature is not None:
            pending["expected_temperature"] = expected_temperature
        pending["track_for_antichatter"] = track_for_antichatter
        pending["expires_at"] = monotonic() + _EXPECTED_HVAC_CHANGE_TTL_SECONDS
        self._pending_hvac_changes[entity_id] = pending

    async def async_disable_climate_automation_for_manual_override(
        self,
        entity_id: str,
        previous_state: str,
        new_state: str,
    ) -> None:
        """Translate a manual climate change into Smart Airco state."""
        climate_entities = []
        changed = False
        current_state = self.hass.states.get(entity_id)
        target_temperature = None
        if current_state is not None:
            try:
                value = current_state.attributes.get("temperature")
                target_temperature = None if value is None else float(value)
            except (TypeError, ValueError):
                target_temperature = None

        for climate_config in self.climate_entities:
            updated_config = dict(climate_config)
            if updated_config.get(CONF_CLIMATE_ENTITY_ID) == entity_id:
                if new_state == HVACMode.OFF:
                    updated_config[CONF_CLIMATE_PRESET_MODE] = PRESET_OFF
                    updated_config[CONF_CLIMATE_ENABLED] = False
                else:
                    updated_config[CONF_CLIMATE_PRESET_MODE] = PRESET_ON
                    updated_config[CONF_CLIMATE_ENABLED] = True
                    if new_state in (HVACMode.COOL, HVACMode.HEAT):
                        updated_config[CONF_CLIMATE_HVAC_MODE] = new_state
                    if target_temperature is not None:
                        updated_config[CONF_CLIMATE_TARGET_TEMPERATURE] = (
                            target_temperature
                        )
                updated_config[CONF_CLIMATE_MANUAL_OVERRIDE] = True
                if updated_config != climate_config:
                    changed = True
            climate_entities.append(updated_config)

        if not changed:
            return

        _LOGGER.info(
            "Manual override detected for %s (%s -> %s); syncing Smart Airco preset state",
            entity_id,
            previous_state,
            new_state,
        )
        self.hass.config_entries.async_update_entry(
            self.entry,
            data={**self.entry.data, CONF_CLIMATE_ENTITIES: climate_entities},
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from sensors and calculate energy surplus."""
        try:
            data = await self._fetch_sensor_data()
            calculations = self._calculate_energy_data(data)
            decisions = self._calculate_airco_decisions(data, calculations)

            return {
                "sensors": data,
                "calculations": calculations,
                "decisions": decisions,
                "last_update": dt_util.utcnow(),
            }
        except Exception as err:
            raise UpdateFailed(f"Error communicating with sensors: {err}") from err

    async def _fetch_sensor_data(self) -> dict[str, Any]:
        """Fetch data from all configured sensors."""
        data: dict[str, Any] = {"critical_input_errors": []}

        # Solar forecast data
        forecast_power = self._read_forecast_power(
            self.config.get(CONF_SOLAR_FORECAST_SENSOR),
            data["critical_input_errors"],
        )
        if forecast_power is not None:
            data["forecast_power"] = forecast_power

        # Current solar production
        current_production = self._read_numeric_sensor_state(
            self.config.get(CONF_SOLAR_PRODUCTION_SENSOR),
            sensor_label="solar_production_sensor",
            stale_after=self._live_sensor_stale_after,
            errors=data["critical_input_errors"],
        )
        if current_production is not None:
            data["current_production"] = current_production

        # Net export to grid
        net_export = self._read_numeric_sensor_state(
            self.config.get(CONF_NET_EXPORT_SENSOR),
            sensor_label="net_export_sensor",
            stale_after=self._live_sensor_stale_after,
            errors=data["critical_input_errors"],
        )
        if net_export is not None:
            data["net_export"] = net_export

        data["critical_inputs_valid"] = not data["critical_input_errors"]

        # Climate entity data
        data["climate_entities"] = {}
        total_airco_consumption = 0

        for climate_config in self.climate_entities:
            entity_id = climate_config.get(CONF_CLIMATE_ENTITY_ID)
            if not entity_id:
                continue

            climate_data = {
                "config": climate_config,
                "enabled": climate_config.get(CONF_CLIMATE_ENABLED, True),
                "manual_override": climate_config.get(
                    CONF_CLIMATE_MANUAL_OVERRIDE, False
                ),
                "preset_mode": self.climate_preset_mode(climate_config),
                "priority": climate_config.get(CONF_CLIMATE_PRIORITY, 999),
                "name": climate_config.get(CONF_CLIMATE_NAME, entity_id),
                "desired_hvac_mode": self.climate_hvac_mode(climate_config),
                "target_temperature": self.climate_target_temperature(climate_config),
            }

            # Get climate entity state
            climate_state = self.hass.states.get(entity_id)
            climate_data["state"] = climate_state.state if climate_state else "unknown"
            climate_data["available"] = (
                climate_state is not None and climate_state.state != "unavailable"
            )
            climate_data["recent_hvac_change"] = self._recent_hvac_changes.get(
                entity_id
            )

            # Get current power consumption
            power_consumption = 0
            use_estimated = climate_config.get(CONF_CLIMATE_USE_ESTIMATED_POWER, True)

            if not use_estimated and climate_config.get(CONF_CLIMATE_POWER_SENSOR):
                # Use real-time power sensor
                power_sensor = climate_config[CONF_CLIMATE_POWER_SENSOR]
                power_state = self.hass.states.get(power_sensor)
                if power_state and power_state.state not in ("unknown", "unavailable"):
                    try:
                        power_consumption = int(float(power_state.state))
                        climate_data["power_source"] = "sensor"
                    except (ValueError, TypeError):
                        _LOGGER.warning(
                            "Invalid power sensor value for %s: %s",
                            entity_id,
                            power_state.state,
                        )
                        # Fall back to estimated
                        power_consumption = climate_config.get(
                            CONF_CLIMATE_WATTAGE, 1000
                        )
                        climate_data["power_source"] = "estimated_fallback"
                else:
                    _LOGGER.warning(
                        "Power sensor %s unavailable for %s", power_sensor, entity_id
                    )
                    # Fall back to estimated
                    power_consumption = climate_config.get(CONF_CLIMATE_WATTAGE, 1000)
                    climate_data["power_source"] = "estimated_fallback"
            else:
                # Use estimated power
                power_consumption = climate_config.get(CONF_CLIMATE_WATTAGE, 1000)
                climate_data["power_source"] = "estimated"

            climate_data["current_power"] = power_consumption

            # Only count power if AC is currently running (cooling)
            if climate_data["state"] == climate_data["desired_hvac_mode"]:
                total_airco_consumption += power_consumption

            # Check window sensors
            window_sensors = climate_config.get(CONF_CLIMATE_WINDOW_SENSORS, [])
            windows_open = any(
                self.hass.states.is_state(window, "on") for window in window_sensors
            )
            climate_data["windows_open"] = windows_open
            climate_data["can_run"] = (
                climate_data["preset_mode"] == PRESET_SOLAR_BASED
                and not windows_open
                and climate_data["available"]
            )

            data["climate_entities"][entity_id] = climate_data

        data["total_airco_consumption"] = total_airco_consumption
        return data

    @property
    def _live_sensor_stale_after(self) -> timedelta:
        """Return the maximum age for live production and export sensors."""
        update_interval = self.update_interval
        if update_interval is None:
            update_interval = DEFAULT_UPDATE_INTERVAL
        return max(
            update_interval * 3,
            timedelta(minutes=_LIVE_SENSOR_STALE_MINUTES),
        )

    def _read_forecast_power(self, entity_id: Any, errors: list[str]) -> int | None:
        """Read Solcast-style forecast power from a configured forecast sensor."""
        state = self._get_required_state(
            entity_id,
            sensor_label="solar_forecast_sensor",
            stale_after=timedelta(hours=_FORECAST_SENSOR_STALE_HOURS),
            errors=errors,
        )
        if state is None:
            return None

        estimate10 = state.attributes.get("estimate10")
        if estimate10 in (None, "unknown", "unavailable"):
            errors.append("solar_forecast_sensor_missing_estimate10")
            _LOGGER.warning(
                "Forecast sensor %s is missing the expected Solcast estimate10 attribute",
                entity_id,
            )
            return None

        try:
            return int(float(estimate10))
        except (TypeError, ValueError):
            errors.append("solar_forecast_sensor_invalid_estimate10")
            _LOGGER.warning(
                "Forecast sensor %s has an invalid estimate10 value: %s",
                entity_id,
                estimate10,
            )
            return None

    def _read_numeric_sensor_state(
        self,
        entity_id: Any,
        *,
        sensor_label: str,
        stale_after: timedelta,
        errors: list[str],
    ) -> int | None:
        """Read a required numeric sensor state with fail-safe validation."""
        state = self._get_required_state(
            entity_id,
            sensor_label=sensor_label,
            stale_after=stale_after,
            errors=errors,
        )
        if state is None:
            return None

        try:
            return int(float(state.state))
        except (TypeError, ValueError):
            errors.append(f"{sensor_label}_invalid_state")
            _LOGGER.warning(
                "Critical sensor %s has a non-numeric state: %s",
                entity_id,
                state.state,
            )
            return None

    def _get_required_state(
        self,
        entity_id: Any,
        *,
        sensor_label: str,
        stale_after: timedelta,
        errors: list[str],
    ) -> State | None:
        """Return a valid state object for a required critical input."""
        if not isinstance(entity_id, str) or not entity_id:
            errors.append(f"{sensor_label}_not_configured")
            _LOGGER.warning("Critical sensor %s is not configured", sensor_label)
            return None

        state = self.hass.states.get(entity_id)
        if state is None:
            errors.append(f"{sensor_label}_missing")
            _LOGGER.warning("Critical sensor %s not found: %s", sensor_label, entity_id)
            return None
        if state.state in ("unknown", "unavailable"):
            errors.append(f"{sensor_label}_unavailable")
            _LOGGER.warning(
                "Critical sensor %s unavailable: %s", sensor_label, entity_id
            )
            return None
        if self._is_state_stale(state, stale_after):
            errors.append(f"{sensor_label}_stale")
            _LOGGER.warning("Critical sensor %s is stale: %s", sensor_label, entity_id)
            return None

        return state

    def _is_state_stale(self, state: State, stale_after: timedelta) -> bool:
        """Return True if a state update is older than the allowed window."""
        return dt_util.utcnow() - state.last_updated > stale_after

    def _calculate_energy_data(self, sensor_data: dict[str, Any]) -> dict[str, Any]:
        """Calculate energy surplus and consumption data."""
        if sensor_data.get("critical_input_errors"):
            return {
                "house_consumption_no_ac": 0,
                "predicted_surplus": 0,
                "current_surplus": 0,
                "total_airco_consumption": sensor_data.get(
                    "total_airco_consumption", 0
                ),
                "critical_inputs_valid": False,
                "critical_input_errors": sensor_data.get("critical_input_errors", []),
            }

        current_production = sensor_data.get("current_production", 0)
        net_export = sensor_data.get("net_export", 0)
        total_airco_consumption = sensor_data.get("total_airco_consumption", 0)
        forecast_power = sensor_data.get("forecast_power", 0)

        # Calculate house consumption without airco
        house_consumption_no_ac = max(
            current_production - net_export - total_airco_consumption, 0
        )

        # Calculate predicted surplus based on forecast
        predicted_surplus = forecast_power - house_consumption_no_ac

        # Current surplus (what we're exporting right now)
        current_surplus = net_export

        return {
            "house_consumption_no_ac": house_consumption_no_ac,
            "predicted_surplus": predicted_surplus,
            "current_surplus": current_surplus,
            "total_airco_consumption": total_airco_consumption,
            "critical_inputs_valid": True,
            "critical_input_errors": [],
        }

    def _calculate_airco_decisions(
        self, sensor_data: dict[str, Any], calculations: dict[str, Any]
    ) -> dict[str, Any]:
        """Calculate what the airco units should be doing based on priority and available surplus."""
        predicted_surplus = calculations.get("predicted_surplus", 0)
        climate_entities = sensor_data.get("climate_entities", {})

        decisions = {
            "climate_decisions": {},
            "total_power_needed": 0,
            "reason": "no_available_climates",
            "available_surplus": predicted_surplus,
            "critical_input_errors": sensor_data.get("critical_input_errors", []),
        }

        forced_on_climates = []
        solar_based_climates = []

        for entity_id, climate_data in climate_entities.items():
            preset_mode = climate_data.get("preset_mode", PRESET_SOLAR_BASED)
            climate_payload = {
                "entity_id": entity_id,
                "priority": climate_data["priority"],
                "power": climate_data["current_power"],
                "name": climate_data["name"],
                "current_state": climate_data["state"],
                "desired_hvac_mode": climate_data["desired_hvac_mode"],
                "target_temperature": climate_data.get("target_temperature"),
                "recent_hvac_change": climate_data.get("recent_hvac_change"),
            }

            if preset_mode == PRESET_OFF:
                decisions["climate_decisions"][entity_id] = {
                    "should_cool": False,
                    "reason": PRESET_OFF,
                    "power": climate_data.get("current_power", 0),
                }
                continue

            if preset_mode == PRESET_ON:
                forced_on_climates.append(climate_payload)
                continue

            if sensor_data.get("critical_input_errors"):
                decisions["climate_decisions"][entity_id] = {
                    "should_cool": False,
                    "reason": "critical_inputs_invalid",
                    "power": climate_data.get("current_power", 0),
                }
                continue

            if climate_data["can_run"]:
                solar_based_climates.append(climate_payload)
                continue

            reason = "cannot_run"
            if climate_data.get("manual_override"):
                reason = "manual_override"
            elif climate_data.get("windows_open"):
                reason = "windows_open"
            elif not climate_data.get("available"):
                reason = "unavailable"

            decisions["climate_decisions"][entity_id] = {
                "should_cool": False,
                "reason": reason,
                "power": climate_data.get("current_power", 0),
            }

        for climate in forced_on_climates:
            entity_id = climate["entity_id"]
            decisions["climate_decisions"][entity_id] = {
                "should_cool": True,
                "reason": PRESET_ON,
                "power": climate["power"],
            }

        solar_based_climates.sort(key=lambda x: x["priority"])

        if not forced_on_climates and not solar_based_climates:
            decisions["reason"] = (
                "critical_inputs_invalid"
                if sensor_data.get("critical_input_errors")
                else "no_available_climates"
            )
            return decisions

        running_power = sum(climate["power"] for climate in forced_on_climates)
        if forced_on_climates:
            decisions["reason"] = f"forced_on_{len(forced_on_climates)}_units"
        else:
            decisions["reason"] = "insufficient_surplus"

        for climate in solar_based_climates:
            entity_id = climate["entity_id"]
            power_needed = climate["power"]
            current_state = climate["current_state"]
            desired_hvac_mode = climate["desired_hvac_mode"]

            min_run_remaining = self._minimum_run_time_remaining(
                current_state,
                climate.get("recent_hvac_change"),
                desired_hvac_mode,
            )
            if min_run_remaining is not None:
                decisions["climate_decisions"][entity_id] = {
                    "should_cool": True,
                    "reason": f"minimum_run_time_remaining_{min_run_remaining}s",
                    "power": power_needed,
                }
                running_power += power_needed
                decisions["reason"] = (
                    f"running_{len([d for d in decisions['climate_decisions'].values() if d['should_cool']])}_units"
                )
                continue

            min_off_remaining = self._minimum_off_time_remaining(
                current_state,
                climate.get("recent_hvac_change"),
                desired_hvac_mode,
            )
            if min_off_remaining is not None:
                decisions["climate_decisions"][entity_id] = {
                    "should_cool": False,
                    "reason": f"minimum_off_time_remaining_{min_off_remaining}s",
                    "power": power_needed,
                }
                continue

            # Check if we have enough surplus for this AC
            if current_state == desired_hvac_mode:
                can_run = (
                    running_power + power_needed
                    <= predicted_surplus + _SURPLUS_HYSTERESIS_WATTS
                )
                success_reason = (
                    f"priority_{climate['priority']}_running_with_hysteresis"
                )
            else:
                can_run = (
                    running_power + power_needed + _SURPLUS_HYSTERESIS_WATTS
                    <= predicted_surplus
                )
                success_reason = (
                    f"priority_{climate['priority']}_surplus_available_with_hysteresis"
                )

            if can_run:
                # We can run this AC
                decisions["climate_decisions"][entity_id] = {
                    "should_cool": True,
                    "reason": success_reason,
                    "power": power_needed,
                }
                running_power += power_needed
                decisions["reason"] = (
                    f"running_{len([d for d in decisions['climate_decisions'].values() if d['should_cool']])}_units"
                )
            else:
                # Not enough surplus for this AC
                decisions["climate_decisions"][entity_id] = {
                    "should_cool": False,
                    "reason": (
                        "insufficient_surplus_"
                        f"need_{power_needed}W_have_{predicted_surplus - running_power}W_"
                        f"hysteresis_{_SURPLUS_HYSTERESIS_WATTS}W"
                    ),
                    "power": power_needed,
                }

        # Set decisions for climate entities that cannot run
        for entity_id, climate_data in climate_entities.items():
            if entity_id not in decisions["climate_decisions"]:
                decisions["climate_decisions"][entity_id] = {
                    "should_cool": False,
                    "reason": "cannot_run",
                    "power": climate_data["current_power"],
                }

        decisions["total_power_needed"] = running_power
        return decisions

    def _minimum_run_time_remaining(
        self,
        current_state: str,
        recent_hvac_change: tuple[str, datetime] | None,
        controller_hvac_mode: str,
    ) -> int | None:
        """Return remaining minimum run time in seconds if cooling must continue."""
        if current_state != controller_hvac_mode or recent_hvac_change is None:
            return None

        changed_state, changed_at = recent_hvac_change
        if changed_state != controller_hvac_mode:
            return None

        elapsed = dt_util.utcnow() - changed_at
        if elapsed >= _MINIMUM_RUN_TIME:
            return None
        return max(int((_MINIMUM_RUN_TIME - elapsed).total_seconds()), 1)

    def _minimum_off_time_remaining(
        self,
        current_state: str,
        recent_hvac_change: tuple[str, datetime] | None,
        controller_hvac_mode: str,
    ) -> int | None:
        """Return remaining minimum off time in seconds if startup must wait."""
        if current_state == controller_hvac_mode or recent_hvac_change is None:
            return None

        changed_state, changed_at = recent_hvac_change
        if changed_state != "off":
            return None

        elapsed = dt_util.utcnow() - changed_at
        if elapsed >= _MINIMUM_OFF_TIME:
            return None
        return max(int((_MINIMUM_OFF_TIME - elapsed).total_seconds()), 1)

    async def async_set_climate_mode(
        self,
        entity_id: str,
        hvac_mode: str,
        *,
        track_for_antichatter: bool = True,
    ) -> None:
        """Set HVAC mode for a climate entity."""
        try:
            self._remember_expected_climate_change(
                entity_id,
                expected_state=hvac_mode,
                track_for_antichatter=track_for_antichatter,
            )
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": entity_id, "hvac_mode": hvac_mode},
                blocking=True,
            )
            _LOGGER.info("Set %s to %s", entity_id, hvac_mode)
        except Exception as err:
            self._pending_hvac_changes.pop(entity_id, None)
            _LOGGER.error("Failed to set %s to %s: %s", entity_id, hvac_mode, err)

    async def async_set_climate_temperature(
        self, entity_id: str, temperature: float
    ) -> None:
        """Set target temperature for a climate entity."""
        try:
            self._remember_expected_climate_change(
                entity_id,
                expected_temperature=temperature,
                track_for_antichatter=False,
            )
            await self.hass.services.async_call(
                "climate",
                "set_temperature",
                {"entity_id": entity_id, "temperature": temperature},
                blocking=True,
            )
            _LOGGER.info("Set %s target temperature to %s", entity_id, temperature)
        except Exception as err:
            pending = self._pending_hvac_changes.get(entity_id)
            if pending is not None:
                pending.pop("expected_temperature", None)
                if not pending.get("expected_state"):
                    self._pending_hvac_changes.pop(entity_id, None)
            _LOGGER.error(
                "Failed to set %s target temperature to %s: %s",
                entity_id,
                temperature,
                err,
            )

    async def async_execute_decisions(self) -> None:
        """Execute the airco decisions based on current data."""
        if not self.data:
            _LOGGER.warning("No data available for executing decisions")
            return

        decisions = self.data.get("decisions", {})
        climate_decisions = decisions.get("climate_decisions", {})
        sensor_data = self.data.get("sensors", {})
        climate_entities = sensor_data.get("climate_entities", {})

        _LOGGER.info(
            "Executing decisions: %s (surplus: %dW, total needed: %dW)",
            decisions.get("reason", "unknown"),
            decisions.get("available_surplus", 0),
            decisions.get("total_power_needed", 0),
        )

        # Execute decisions for each climate entity
        for entity_id, climate_decision in climate_decisions.items():
            if entity_id not in climate_entities:
                continue

            current_state = climate_entities[entity_id]["state"]
            should_cool = climate_decision["should_cool"]
            climate_name = climate_entities[entity_id]["name"]
            desired_hvac_mode = climate_entities[entity_id].get(
                "desired_hvac_mode", DEFAULT_CLIMATE_HVAC_MODE
            )
            desired_target_temperature = climate_entities[entity_id].get(
                "target_temperature"
            )
            climate_state = self.hass.states.get(entity_id)
            current_target_temperature = None
            if climate_state is not None:
                try:
                    current_target_temperature = float(
                        climate_state.attributes.get("temperature")
                    )
                except (TypeError, ValueError):
                    current_target_temperature = None

            _LOGGER.debug(
                "Climate %s (%s): should_cool=%s, current=%s, reason=%s",
                climate_name,
                entity_id,
                should_cool,
                current_state,
                climate_decision.get("reason", "unknown"),
            )

            # Execute state change if needed
            if should_cool and current_state != desired_hvac_mode:
                _LOGGER.info(
                    "Turning ON %s (%s) in %s mode - %s",
                    climate_name,
                    entity_id,
                    desired_hvac_mode,
                    climate_decision.get("reason"),
                )
                await self.async_set_climate_mode(entity_id, desired_hvac_mode)
                if desired_target_temperature is not None:
                    await self.async_set_climate_temperature(
                        entity_id, desired_target_temperature
                    )
            elif (
                should_cool
                and desired_target_temperature is not None
                and (
                    current_target_temperature is None
                    or abs(current_target_temperature - desired_target_temperature)
                    >= 0.25
                )
            ):
                _LOGGER.info(
                    "Updating target temperature for %s (%s) to %s",
                    climate_name,
                    entity_id,
                    desired_target_temperature,
                )
                await self.async_set_climate_temperature(
                    entity_id, desired_target_temperature
                )
            elif not should_cool and current_state not in ("off", "unknown"):
                _LOGGER.info(
                    "Turning OFF %s (%s) - %s",
                    climate_name,
                    entity_id,
                    climate_decision.get("reason"),
                )
                await self.async_set_climate_mode(entity_id, "off")
