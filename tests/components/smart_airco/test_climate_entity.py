from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.climate.const import HVACAction, HVACMode
from homeassistant.const import ATTR_TEMPERATURE

from custom_components.smart_airco.climate import SmartAircoClimateEntity
from custom_components.smart_airco.const import (
    CONF_CONTROLLER_ENABLED,
    CONF_CONTROLLER_HVAC_MODE,
    CONF_CONTROLLER_TARGET_TEMPERATURE,
    DOMAIN,
)
from custom_components.smart_airco.coordinator import SmartAircoCoordinator


@pytest.mark.asyncio
async def test_controller_hvac_mode_and_turn_on_off(hass, setup_integration) -> None:
    coordinator: SmartAircoCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    entity = SmartAircoClimateEntity(coordinator, setup_integration)

    assert entity.hvac_mode == HVACMode.COOL

    with (
        patch.object(entity, "_turn_off_all_acs", AsyncMock()) as mock_turn_off,
        patch.object(entity, "async_write_ha_state"),
    ):
        await entity.async_turn_off()

    assert entity.hvac_mode == HVACMode.OFF
    assert setup_integration.data[CONF_CONTROLLER_ENABLED] is False
    mock_turn_off.assert_awaited_once()

    with (
        patch.object(coordinator, "async_request_refresh", AsyncMock()) as mock_refresh,
        patch.object(entity, "async_write_ha_state"),
    ):
        await entity.async_turn_on()

    assert entity.hvac_mode == HVACMode.COOL
    assert setup_integration.data[CONF_CONTROLLER_ENABLED] is True
    mock_refresh.assert_awaited_once()

    with (
        patch.object(coordinator, "async_request_refresh", AsyncMock()) as mock_refresh,
        patch.object(entity, "async_write_ha_state"),
    ):
        await entity.async_set_hvac_mode(HVACMode.HEAT)

    assert entity.hvac_mode == HVACMode.HEAT
    assert setup_integration.data[CONF_CONTROLLER_HVAC_MODE] == HVACMode.HEAT
    mock_refresh.assert_awaited_once()


def test_controller_hvac_action_reflects_actual_runtime(
    hass, mock_config_entry
) -> None:
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)
    entity = SmartAircoClimateEntity(coordinator, mock_config_entry)

    coordinator.__dict__["data"] = None
    assert entity.hvac_action == HVACAction.IDLE

    coordinator.data = {
        "sensors": {
            "climate_entities": {
                "climate.living_room": {"state": "off"},
                "climate.bedroom": {"state": "cool"},
            }
        },
        "decisions": {
            "climate_decisions": {"climate.living_room": {"should_cool": True}}
        },
    }
    assert entity.hvac_action == HVACAction.COOLING

    coordinator.data["sensors"]["climate_entities"]["climate.bedroom"]["state"] = "off"
    assert entity.hvac_action == HVACAction.IDLE

    entity._enabled = False
    assert entity.hvac_action == HVACAction.OFF

    entity._enabled = True
    entity._controller_mode = HVACMode.HEAT
    coordinator.data["sensors"]["climate_entities"]["climate.bedroom"]["state"] = "heat"
    assert entity.hvac_action == HVACAction.HEATING


def test_controller_restores_persisted_disabled_state(hass, mock_config_entry) -> None:
    disabled_entry = mock_config_entry.__class__(
        domain=mock_config_entry.domain,
        title=mock_config_entry.title,
        data={**mock_config_entry.data, CONF_CONTROLLER_ENABLED: False},
    )
    coordinator = SmartAircoCoordinator(hass, disabled_entry)
    entity = SmartAircoClimateEntity(coordinator, disabled_entry)

    assert entity.hvac_mode == HVACMode.OFF


def test_controller_restores_persisted_heat_mode(hass, mock_config_entry) -> None:
    heat_entry = mock_config_entry.__class__(
        domain=mock_config_entry.domain,
        title=mock_config_entry.title,
        data={
            **mock_config_entry.data,
            CONF_CONTROLLER_ENABLED: True,
            CONF_CONTROLLER_HVAC_MODE: HVACMode.HEAT,
        },
    )
    coordinator = SmartAircoCoordinator(hass, heat_entry)
    entity = SmartAircoClimateEntity(coordinator, heat_entry)

    assert entity.hvac_mode == HVACMode.HEAT


def test_controller_temperature_averages_and_attributes(
    hass, mock_config_entry, seed_states
) -> None:
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)
    entity = SmartAircoClimateEntity(coordinator, mock_config_entry)
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
                    "state": "off",
                    "current_power": 950,
                    "power_source": "sensor",
                    "priority": 1,
                    "windows_open": False,
                    "config": mock_config_entry.data["climate_entities"][0],
                },
                "climate.bedroom": {
                    "name": "Bedroom",
                    "enabled": True,
                    "can_run": True,
                    "state": "cool",
                    "current_power": 800,
                    "power_source": "estimated",
                    "priority": 2,
                    "windows_open": False,
                    "config": mock_config_entry.data["climate_entities"][1],
                },
            },
        },
        "calculations": {
            "predicted_surplus": 2000,
            "current_surplus": 1500,
            "total_airco_consumption": 800,
        },
        "decisions": {
            "reason": "running_1_units",
            "total_power_needed": 800,
            "climate_decisions": {
                "climate.living_room": {"should_cool": False, "reason": "idle"},
                "climate.bedroom": {"should_cool": True, "reason": "priority_2"},
            },
        },
        "last_update": "now",
    }

    assert entity.current_temperature == pytest.approx(23.5)
    assert entity.target_temperature == pytest.approx(20.5)

    attributes = entity.extra_state_attributes
    assert attributes["smart_airco_controller"] is True
    assert attributes["configured_climate_entity_ids"] == [
        "climate.bedroom",
        "climate.living_room",
    ]
    assert attributes["update_interval_seconds"] == 300
    assert attributes["controller_hvac_mode"] == HVACMode.COOL
    assert attributes["controller_target_temperature"] == pytest.approx(20.5)
    assert attributes["climate_living_room_entity_id"] == "climate.living_room"
    assert attributes["climate_bedroom_reason"] == "priority_2"
    assert attributes["managed_climates"][1]["entity_id"] == "climate.bedroom"


@pytest.mark.asyncio
async def test_controller_set_temperature_persists_and_updates_running_selected_climates(
    hass, setup_integration
) -> None:
    coordinator: SmartAircoCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    entity = SmartAircoClimateEntity(coordinator, setup_integration)
    coordinator.data = {
        "sensors": {
            "climate_entities": {
                "climate.living_room": {"state": HVACMode.COOL, "enabled": True},
                "climate.bedroom": {"state": "off", "enabled": True},
            }
        },
        "decisions": {},
        "calculations": {},
    }

    with (
        patch.object(
            coordinator, "async_set_climate_temperature", AsyncMock()
        ) as mock_set_temp,
        patch.object(entity, "async_write_ha_state"),
    ):
        await entity.async_set_temperature(**{ATTR_TEMPERATURE: 22.5})

    assert setup_integration.data[CONF_CONTROLLER_TARGET_TEMPERATURE] == 22.5
    assert entity.target_temperature == pytest.approx(22.5)
    mock_set_temp.assert_awaited_once_with("climate.living_room", 22.5)


def test_controller_temperature_averages_only_selected_climates(
    hass, mock_config_entry, seed_states
) -> None:
    selected_entry = mock_config_entry.__class__(
        domain=mock_config_entry.domain,
        title=mock_config_entry.title,
        data={
            **mock_config_entry.data,
            "climate_entities": [
                {**mock_config_entry.data["climate_entities"][0], "enabled": True},
                {**mock_config_entry.data["climate_entities"][1], "enabled": False},
            ],
        },
    )
    coordinator = SmartAircoCoordinator(hass, selected_entry)
    entity = SmartAircoClimateEntity(coordinator, selected_entry)
    coordinator.data = {
        "sensors": {
            "climate_entities": {
                "climate.living_room": {"state": "off", "enabled": True},
                "climate.bedroom": {"state": "off", "enabled": False},
            }
        },
        "decisions": {},
        "calculations": {},
    }

    assert entity.current_temperature == pytest.approx(24.0)
    assert entity.target_temperature == pytest.approx(21.0)


def test_coordinator_update_schedules_execution_when_enabled(
    hass, mock_config_entry
) -> None:
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)
    entity = SmartAircoClimateEntity(coordinator, mock_config_entry)
    coordinator.data = {"decisions": {}, "sensors": {}, "calculations": {}}

    def _close_task(coro):
        coro.close()

    with (
        patch.object(
            hass, "async_create_task", side_effect=_close_task
        ) as mock_create_task,
        patch.object(entity, "async_write_ha_state"),
    ):
        entity._handle_coordinator_update()

    mock_create_task.assert_called_once()

    entity._enabled = False
    with (
        patch.object(
            hass, "async_create_task", side_effect=_close_task
        ) as mock_create_task,
        patch.object(entity, "async_write_ha_state"),
    ):
        entity._handle_coordinator_update()

    mock_create_task.assert_not_called()
