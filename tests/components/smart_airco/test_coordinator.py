from __future__ import annotations

from datetime import timedelta
from time import monotonic
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.smart_airco.const import (
    CONF_CLIMATE_MANUAL_OVERRIDE,
    CONF_CONTROLLER_HVAC_MODE,
    CONF_CONTROLLER_TARGET_TEMPERATURE,
    DOMAIN,
)
from custom_components.smart_airco.coordinator import SmartAircoCoordinator


@pytest.mark.asyncio
async def test_fetch_sensor_data_uses_power_sensor_when_available(
    hass, mock_config_entry, seed_states
) -> None:
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)

    data = await coordinator._fetch_sensor_data()

    living_room = data["climate_entities"]["climate.living_room"]
    assert living_room["current_power"] == 950
    assert living_room["power_source"] == "sensor"


@pytest.mark.asyncio
async def test_fetch_sensor_data_falls_back_to_estimated_power(
    hass, mock_config_entry, seed_states
) -> None:
    hass.states.async_set(
        "sensor.living_room_power", "invalid", {"device_class": "power"}
    )
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)

    data = await coordinator._fetch_sensor_data()

    living_room = data["climate_entities"]["climate.living_room"]
    assert living_room["current_power"] == 1000
    assert living_room["power_source"] == "estimated_fallback"


@pytest.mark.asyncio
async def test_fetch_sensor_data_marks_windows_open_and_cannot_run(
    hass, mock_config_entry, seed_states
) -> None:
    hass.states.async_set(
        "binary_sensor.living_room_window",
        "on",
        {"device_class": "window"},
    )
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)

    data = await coordinator._fetch_sensor_data()

    living_room = data["climate_entities"]["climate.living_room"]
    assert living_room["windows_open"] is True
    assert living_room["can_run"] is False


@pytest.mark.asyncio
async def test_calculate_energy_data_and_priority_decisions(
    hass, mock_config_entry, seed_states
) -> None:
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)
    sensor_data = await coordinator._fetch_sensor_data()
    calculations = coordinator._calculate_energy_data(sensor_data)
    decisions = coordinator._calculate_airco_decisions(sensor_data, calculations)

    assert calculations["house_consumption_no_ac"] == 1500
    assert calculations["predicted_surplus"] == 2000
    assert calculations["current_surplus"] == 1500
    assert decisions["climate_decisions"]["climate.living_room"]["should_cool"] is True
    assert decisions["climate_decisions"]["climate.bedroom"]["should_cool"] is True
    assert decisions["total_power_needed"] == 1750


@pytest.mark.asyncio
async def test_calculate_airco_decisions_respects_priority_and_reasons(
    hass, mock_config_entry, seed_states
) -> None:
    hass.states.async_set("sensor.solar_forecast", "1200", {"estimate10": 1200})
    hass.states.async_set(
        "binary_sensor.living_room_window",
        "on",
        {"device_class": "window"},
    )
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)

    sensor_data = await coordinator._fetch_sensor_data()
    calculations = coordinator._calculate_energy_data(sensor_data)
    decisions = coordinator._calculate_airco_decisions(sensor_data, calculations)

    assert (
        decisions["climate_decisions"]["climate.living_room"]["reason"]
        == "windows_open"
    )
    assert decisions["climate_decisions"]["climate.bedroom"]["reason"].startswith(
        "insufficient_surplus"
    )
    assert decisions["climate_decisions"]["climate.bedroom"]["should_cool"] is False


@pytest.mark.asyncio
async def test_calculate_airco_decisions_marks_manual_override(
    hass, mock_config_entry, seed_states
) -> None:
    mock_config_entry.data["climate_entities"][1]["enabled"] = False
    mock_config_entry.data["climate_entities"][1][CONF_CLIMATE_MANUAL_OVERRIDE] = True
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)

    sensor_data = await coordinator._fetch_sensor_data()
    calculations = coordinator._calculate_energy_data(sensor_data)
    decisions = coordinator._calculate_airco_decisions(sensor_data, calculations)

    assert decisions["climate_decisions"]["climate.bedroom"]["should_cool"] is False
    assert (
        decisions["climate_decisions"]["climate.bedroom"]["reason"] == "manual_override"
    )


@pytest.mark.asyncio
async def test_invalid_forecast_input_forces_fail_safe_decisions(
    hass, mock_config_entry, seed_states
) -> None:
    hass.states.async_set("sensor.solar_forecast", "3500", {})
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)

    sensor_data = await coordinator._fetch_sensor_data()
    calculations = coordinator._calculate_energy_data(sensor_data)
    decisions = coordinator._calculate_airco_decisions(sensor_data, calculations)

    assert sensor_data["critical_inputs_valid"] is False
    assert (
        "solar_forecast_sensor_missing_estimate10"
        in sensor_data["critical_input_errors"]
    )
    assert calculations["critical_inputs_valid"] is False
    assert decisions["reason"] == "critical_inputs_invalid"
    assert all(
        not decision["should_cool"]
        for decision in decisions["climate_decisions"].values()
    )


@pytest.mark.asyncio
async def test_stale_live_sensor_forces_fail_safe_decisions(
    hass, mock_config_entry, seed_states
) -> None:
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)

    with patch.object(coordinator, "_is_state_stale", return_value=True):
        sensor_data = await coordinator._fetch_sensor_data()

    calculations = coordinator._calculate_energy_data(sensor_data)
    decisions = coordinator._calculate_airco_decisions(sensor_data, calculations)

    assert sensor_data["critical_inputs_valid"] is False
    assert "solar_forecast_sensor_stale" in sensor_data["critical_input_errors"]
    assert decisions["reason"] == "critical_inputs_invalid"


@pytest.mark.asyncio
async def test_recently_started_ac_respects_minimum_run_time(
    hass, mock_config_entry, seed_states
) -> None:
    hass.states.async_set(
        "climate.living_room",
        "cool",
        {"current_temperature": 24.0, "temperature": 21.0},
    )
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)
    coordinator._recent_hvac_changes["climate.living_room"] = (
        "cool",
        dt_util.utcnow() - timedelta(minutes=1),
    )

    hass.states.async_set("sensor.solar_forecast", "1200", {"estimate10": 1200})
    sensor_data = await coordinator._fetch_sensor_data()
    calculations = coordinator._calculate_energy_data(sensor_data)
    decisions = coordinator._calculate_airco_decisions(sensor_data, calculations)

    assert decisions["climate_decisions"]["climate.living_room"]["should_cool"] is True
    assert decisions["climate_decisions"]["climate.living_room"]["reason"].startswith(
        "minimum_run_time_remaining_"
    )


@pytest.mark.asyncio
async def test_recently_stopped_ac_respects_minimum_off_time(
    hass, mock_config_entry, seed_states
) -> None:
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)
    coordinator._recent_hvac_changes["climate.living_room"] = (
        "off",
        dt_util.utcnow() - timedelta(minutes=1),
    )

    sensor_data = await coordinator._fetch_sensor_data()
    calculations = coordinator._calculate_energy_data(sensor_data)
    decisions = coordinator._calculate_airco_decisions(sensor_data, calculations)

    assert decisions["climate_decisions"]["climate.living_room"]["should_cool"] is False
    assert decisions["climate_decisions"]["climate.living_room"]["reason"].startswith(
        "minimum_off_time_remaining_"
    )


@pytest.mark.asyncio
async def test_hysteresis_blocks_marginal_startup(
    hass, mock_config_entry, seed_states
) -> None:
    hass.states.async_set("sensor.solar_forecast", "2450", {"estimate10": 2450})
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)

    sensor_data = await coordinator._fetch_sensor_data()
    calculations = coordinator._calculate_energy_data(sensor_data)
    decisions = coordinator._calculate_airco_decisions(sensor_data, calculations)

    assert decisions["climate_decisions"]["climate.living_room"]["should_cool"] is False
    assert (
        "hysteresis_150W"
        in decisions["climate_decisions"]["climate.living_room"]["reason"]
    )
    assert decisions["climate_decisions"]["climate.bedroom"]["should_cool"] is True


@pytest.mark.asyncio
async def test_execute_decisions_only_calls_state_changes_when_needed(
    hass, mock_config_entry, seed_states
) -> None:
    mock_config_entry = mock_config_entry.__class__(
        domain=mock_config_entry.domain,
        title=mock_config_entry.title,
        data={**mock_config_entry.data, CONF_CONTROLLER_TARGET_TEMPERATURE: 21.0},
    )
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)
    coordinator.data = {
        "decisions": {
            "reason": "running_1_units",
            "available_surplus": 1500,
            "total_power_needed": 950,
            "climate_decisions": {
                "climate.living_room": {"should_cool": True, "reason": "priority_1"},
                "climate.bedroom": {"should_cool": False, "reason": "insufficient"},
            },
        },
        "sensors": {
            "climate_entities": {
                "climate.living_room": {"state": "off", "name": "Living Room"},
                "climate.bedroom": {"state": "cool", "name": "Bedroom"},
            }
        },
    }

    with (
        patch.object(
            coordinator, "async_set_climate_mode", AsyncMock()
        ) as mock_set_mode,
        patch.object(
            coordinator, "async_set_climate_temperature", AsyncMock()
        ) as mock_set_temp,
    ):
        await coordinator.async_execute_decisions()

    mock_set_mode.assert_any_await("climate.living_room", "cool")
    mock_set_mode.assert_any_await("climate.bedroom", "off")
    mock_set_temp.assert_awaited_once_with("climate.living_room", 21.0)


@pytest.mark.asyncio
async def test_execute_decisions_uses_controller_heat_mode(
    hass, mock_config_entry, seed_states
) -> None:
    heat_entry = mock_config_entry.__class__(
        domain=mock_config_entry.domain,
        title=mock_config_entry.title,
        data={**mock_config_entry.data, CONF_CONTROLLER_HVAC_MODE: "heat"},
    )
    coordinator = SmartAircoCoordinator(hass, heat_entry)
    coordinator.data = {
        "decisions": {
            "reason": "running_1_units",
            "available_surplus": 1500,
            "total_power_needed": 950,
            "climate_decisions": {
                "climate.living_room": {"should_cool": True, "reason": "priority_1"},
            },
        },
        "sensors": {
            "climate_entities": {
                "climate.living_room": {"state": "off", "name": "Living Room"},
            }
        },
    }

    with patch.object(
        coordinator, "async_set_climate_mode", AsyncMock()
    ) as mock_set_mode:
        await coordinator.async_execute_decisions()

    mock_set_mode.assert_awaited_once_with("climate.living_room", "heat")


@pytest.mark.asyncio
async def test_expected_coordinator_temperature_change_does_not_trigger_manual_override(
    hass, setup_integration
) -> None:
    coordinator: SmartAircoCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    coordinator._remember_expected_climate_change(
        "climate.bedroom",
        expected_temperature=21.0,
        track_for_antichatter=False,
    )

    hass.states.async_set(
        "climate.bedroom",
        "off",
        {"current_temperature": 23.0, "temperature": 21.0},
    )
    await hass.async_block_till_done()

    bedroom = next(
        c
        for c in setup_integration.data["climate_entities"]
        if c["entity_id"] == "climate.bedroom"
    )
    assert bedroom["enabled"] is True
    assert bedroom.get(CONF_CLIMATE_MANUAL_OVERRIDE, False) is False


def test_update_interval_accepts_seconds_and_timedelta(hass, mock_config_entry) -> None:
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)
    assert coordinator.update_interval == timedelta(seconds=300)

    entry = mock_config_entry.__class__(
        domain=mock_config_entry.domain,
        title=mock_config_entry.title,
        data={**mock_config_entry.data, "update_interval": timedelta(minutes=10)},
    )
    coordinator = SmartAircoCoordinator(hass, entry)
    assert coordinator.update_interval == timedelta(minutes=10)


@pytest.mark.asyncio
async def test_runtime_reload_updates_coordinator_config(
    hass, setup_integration
) -> None:
    coordinator: SmartAircoCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    reload_mock = hass.data["smart_airco_test_reload_mock"]

    hass.config_entries.async_update_entry(
        setup_integration,
        data={**setup_integration.data, "update_interval": 600},
    )
    await hass.async_block_till_done()

    reloaded: SmartAircoCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    assert reloaded.config["update_interval"] == 600
    reload_mock.assert_awaited_once_with(setup_integration.entry_id)
    assert reloaded.update_interval == timedelta(seconds=300)


@pytest.mark.asyncio
async def test_manual_override_disables_automation_for_changed_ac(
    hass, setup_integration
) -> None:
    reload_mock = hass.data["smart_airco_test_reload_mock"]

    hass.states.async_set(
        "climate.bedroom",
        "cool",
        {"current_temperature": 23.0, "temperature": 20.0},
    )
    await hass.async_block_till_done()

    bedroom = next(
        c
        for c in setup_integration.data["climate_entities"]
        if c["entity_id"] == "climate.bedroom"
    )
    assert bedroom["enabled"] is False
    assert bedroom[CONF_CLIMATE_MANUAL_OVERRIDE] is True
    reload_mock.assert_awaited_with(setup_integration.entry_id)


@pytest.mark.asyncio
async def test_manual_override_detects_supported_attribute_change(
    hass, setup_integration
) -> None:
    hass.states.async_set(
        "climate.bedroom",
        "off",
        {"current_temperature": 23.0, "temperature": 18.0},
    )
    await hass.async_block_till_done()

    bedroom = next(
        c
        for c in setup_integration.data["climate_entities"]
        if c["entity_id"] == "climate.bedroom"
    )
    assert bedroom["enabled"] is False
    assert bedroom[CONF_CLIMATE_MANUAL_OVERRIDE] is True


@pytest.mark.asyncio
async def test_expected_coordinator_state_change_does_not_trigger_manual_override(
    hass, setup_integration
) -> None:
    coordinator: SmartAircoCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    coordinator._pending_hvac_changes["climate.bedroom"] = {
        "expected_state": "cool",
        "expires_at": monotonic() + 30,
        "track_for_antichatter": True,
        "expected_temperature": None,
    }

    hass.states.async_set(
        "climate.bedroom",
        "cool",
        {"current_temperature": 23.0, "temperature": 20.0},
    )
    await hass.async_block_till_done()

    bedroom = next(
        c
        for c in setup_integration.data["climate_entities"]
        if c["entity_id"] == "climate.bedroom"
    )
    assert bedroom["enabled"] is True
    assert bedroom.get(CONF_CLIMATE_MANUAL_OVERRIDE, False) is False
