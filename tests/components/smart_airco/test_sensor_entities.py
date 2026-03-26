from __future__ import annotations

from homeassistant.components.climate.const import HVACMode
from custom_components.smart_airco.sensor import (
    SmartAircoClimatePowerSensor,
    SmartAircoClimateStatusSensor,
    SmartAircoEnergySurplusSensor,
    SmartAircoPredictedSurplusSensor,
    SmartAircoRunningCountSensor,
    SmartAircoSystemStatusSensor,
    SmartAircoTotalConsumptionSensor,
)
from custom_components.smart_airco.coordinator import SmartAircoCoordinator


def _build_coordinator_with_data(hass, mock_config_entry) -> SmartAircoCoordinator:
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)
    coordinator.data = {
        "sensors": {
            "forecast_power": 3500,
            "current_production": 3000,
            "net_export": 1500,
            "climate_entities": {
                "climate.living_room": {
                    "name": "Living Room",
                    "enabled": True,
                    "can_run": True,
                    "state": "cool",
                    "desired_hvac_mode": "cool",
                    "target_temperature": 21.0,
                    "current_power": 950,
                    "power_source": "sensor",
                    "priority": 1,
                    "windows_open": False,
                    "config": mock_config_entry.data["climate_entities"][0],
                },
                "climate.bedroom": {
                    "name": "Bedroom",
                    "enabled": True,
                    "can_run": False,
                    "state": "off",
                    "desired_hvac_mode": "cool",
                    "target_temperature": 20.0,
                    "current_power": 800,
                    "power_source": "estimated",
                    "priority": 2,
                    "windows_open": True,
                    "config": mock_config_entry.data["climate_entities"][1],
                },
            },
        },
        "calculations": {
            "house_consumption_no_ac": 1550,
            "predicted_surplus": 1950,
            "current_surplus": 1500,
            "total_airco_consumption": 950,
        },
        "decisions": {
            "reason": "running_1_units",
            "available_surplus": 1950,
            "total_power_needed": 950,
            "climate_decisions": {
                "climate.living_room": {
                    "should_cool": True,
                    "reason": "priority_1_surplus_available",
                },
                "climate.bedroom": {
                    "should_cool": False,
                    "reason": "windows_open",
                },
            },
        },
        "last_update": "now",
    }
    return coordinator


def test_current_surplus_sensor_exposes_value_and_attributes(
    hass, mock_config_entry, seed_states
) -> None:
    coordinator = _build_coordinator_with_data(hass, mock_config_entry)
    entity = SmartAircoEnergySurplusSensor(coordinator, mock_config_entry)

    assert entity.native_value == 1500
    assert entity.extra_state_attributes == {
        "solar_production": 3000,
        "net_export": 1500,
    }


def test_predicted_surplus_sensor_exposes_house_consumption(
    hass, mock_config_entry
) -> None:
    coordinator = _build_coordinator_with_data(hass, mock_config_entry)
    entity = SmartAircoPredictedSurplusSensor(coordinator, mock_config_entry)

    assert entity.native_value == 1950
    assert entity.extra_state_attributes == {
        "solar_forecast": 3500,
        "house_consumption": 1550,
    }


def test_total_consumption_sensor_lists_only_running_acs(
    hass, mock_config_entry
) -> None:
    coordinator = _build_coordinator_with_data(hass, mock_config_entry)
    entity = SmartAircoTotalConsumptionSensor(coordinator, mock_config_entry)

    assert entity.native_value == 950
    attrs = entity.extra_state_attributes
    assert attrs["running_count"] == 1
    assert attrs["running_acs"] == [
        {
            "entity_id": "climate.living_room",
            "name": "Living Room",
            "power": 950,
            "power_source": "sensor",
        }
    ]


def test_running_count_and_system_status_sensors(hass, mock_config_entry) -> None:
    coordinator = _build_coordinator_with_data(hass, mock_config_entry)
    running = SmartAircoRunningCountSensor(coordinator, mock_config_entry)
    status = SmartAircoSystemStatusSensor(coordinator, mock_config_entry)

    assert running.native_value == 1
    assert running.extra_state_attributes == {
        "total_entities": 2,
        "enabled_entities": 2,
        "available_entities": 1,
    }
    assert status.native_value == "running_1_units"
    attrs = status.extra_state_attributes
    assert attrs["smart_airco_panel_anchor"] is True
    assert attrs["available_surplus"] == 1950
    assert attrs["predicted_surplus"] == 1950
    assert attrs["running_entities"] == 1
    assert attrs["managed_climates"][0]["smart_airco_hvac_mode"] == "cool"


def test_running_count_uses_actual_hvac_state_not_desired_state(
    hass, mock_config_entry
) -> None:
    coordinator = _build_coordinator_with_data(hass, mock_config_entry)
    coordinator.data["sensors"]["climate_entities"]["climate.living_room"]["state"] = (
        "off"
    )
    coordinator.data["decisions"]["climate_decisions"]["climate.living_room"][
        "should_cool"
    ] = True

    running = SmartAircoRunningCountSensor(coordinator, mock_config_entry)

    assert running.native_value == 0


def test_climate_power_sensor_reports_zero_when_not_cooling(
    hass, mock_config_entry
) -> None:
    coordinator = _build_coordinator_with_data(hass, mock_config_entry)
    bedroom_cfg = mock_config_entry.data["climate_entities"][1]
    entity = SmartAircoClimatePowerSensor(coordinator, mock_config_entry, bedroom_cfg)

    assert entity.native_value == 0
    assert entity.extra_state_attributes["decision_reason"] == "windows_open"
    assert entity.extra_state_attributes["power_source"] == "estimated"


def test_climate_status_sensor_maps_reason_and_live_temperatures(
    hass, mock_config_entry, seed_states
) -> None:
    coordinator = _build_coordinator_with_data(hass, mock_config_entry)
    bedroom_cfg = mock_config_entry.data["climate_entities"][1]
    entity = SmartAircoClimateStatusSensor(coordinator, mock_config_entry, bedroom_cfg)

    assert entity.native_value == "windows_open"
    attrs = entity.extra_state_attributes
    assert attrs["entity_id"] == "climate.bedroom"
    assert attrs["windows_open"] is True
    assert attrs["can_run"] is False
    assert attrs["current_temperature"] == 23.0
    assert attrs["target_temperature"] == 20.0
    assert attrs["decision_reason"] == "windows_open"


def test_running_and_power_sensors_follow_heat_mode(hass, mock_config_entry) -> None:
    coordinator = _build_coordinator_with_data(hass, mock_config_entry)
    coordinator.data["sensors"]["climate_entities"]["climate.living_room"]["state"] = (
        "heat"
    )
    coordinator.data["sensors"]["climate_entities"]["climate.living_room"][
        "desired_hvac_mode"
    ] = "heat"

    running = SmartAircoRunningCountSensor(coordinator, mock_config_entry)
    total = SmartAircoTotalConsumptionSensor(coordinator, mock_config_entry)
    living_cfg = mock_config_entry.data["climate_entities"][0]
    power = SmartAircoClimatePowerSensor(coordinator, mock_config_entry, living_cfg)
    status = SmartAircoClimateStatusSensor(coordinator, mock_config_entry, living_cfg)

    assert running.native_value == 1
    assert total.extra_state_attributes["running_count"] == 1
    assert power.native_value == 950
    assert power.extra_state_attributes["smart_airco_hvac_mode"] == HVACMode.HEAT
    assert status.native_value == "heating"
