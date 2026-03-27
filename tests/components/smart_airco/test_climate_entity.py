from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.climate.const import HVACAction, HVACMode
from homeassistant.const import ATTR_TEMPERATURE

from custom_components.smart_airco.climate import SmartAircoManagedClimateEntity
from custom_components.smart_airco.const import (
    ATTR_SMART_AIRCO_SOLAR_AUTOMATION_ENABLED,
    CONF_CLIMATE_ENABLED,
    CONF_CLIMATE_ENTITIES,
    CONF_CLIMATE_HVAC_MODE,
    CONF_CLIMATE_MANUAL_OVERRIDE,
    CONF_CLIMATE_PRESET_MODE,
    CONF_CLIMATE_TARGET_TEMPERATURE,
    DOMAIN,
    PRESET_OFF,
    PRESET_ON,
    PRESET_SOLAR_BASED,
)
from custom_components.smart_airco.coordinator import SmartAircoCoordinator


def _entity(coordinator: SmartAircoCoordinator, config_entry, index: int = 0):
    return SmartAircoManagedClimateEntity(
        coordinator,
        config_entry,
        config_entry.data[CONF_CLIMATE_ENTITIES][index],
    )


def test_managed_climate_basic_properties(hass, mock_config_entry, seed_states) -> None:
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)
    entity = _entity(coordinator, mock_config_entry, 0)

    assert entity.hvac_mode == HVACMode.COOL
    assert entity.hvac_modes == [
        HVACMode.OFF,
        HVACMode.AUTO,
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
    ]
    assert entity.preset_mode == PRESET_SOLAR_BASED
    assert entity.current_temperature == pytest.approx(24.0)
    assert entity.target_temperature == pytest.approx(21.0)
    assert entity.min_temp == pytest.approx(10.0)
    assert entity.max_temp == pytest.approx(35.0)


def test_managed_climate_reports_off_hvac_mode_when_preset_off(
    hass, mock_config_entry, seed_states
) -> None:
    mock_config_entry.data[CONF_CLIMATE_ENTITIES][0][CONF_CLIMATE_PRESET_MODE] = (
        PRESET_OFF
    )
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)
    entity = _entity(coordinator, mock_config_entry, 0)

    assert entity.hvac_mode == HVACMode.OFF


def test_managed_climate_hvac_action_reflects_desired_mode(
    hass, mock_config_entry
) -> None:
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)
    entity = _entity(coordinator, mock_config_entry, 0)

    coordinator.data = {
        "sensors": {
            "climate_entities": {
                "climate.living_room": {
                    "state": HVACMode.COOL,
                    "desired_hvac_mode": HVACMode.COOL,
                }
            }
        }
    }
    assert entity.hvac_action == HVACAction.COOLING

    coordinator.data["sensors"]["climate_entities"]["climate.living_room"][
        "desired_hvac_mode"
    ] = HVACMode.HEAT
    coordinator.data["sensors"]["climate_entities"]["climate.living_room"]["state"] = (
        HVACMode.HEAT
    )
    mock_config_entry.data[CONF_CLIMATE_ENTITIES][0][CONF_CLIMATE_HVAC_MODE] = (
        HVACMode.HEAT
    )
    assert entity.hvac_action == HVACAction.HEATING

    coordinator.data["sensors"]["climate_entities"]["climate.living_room"]["state"] = (
        HVACMode.OFF
    )
    assert entity.hvac_action == HVACAction.IDLE


@pytest.mark.asyncio
async def test_set_hvac_mode_updates_per_climate_preferences(
    hass, setup_integration
) -> None:
    coordinator: SmartAircoCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    entity = _entity(coordinator, setup_integration, 0)

    with (
        patch.object(coordinator, "async_request_refresh", AsyncMock()) as mock_refresh,
        patch.object(entity, "async_write_ha_state"),
    ):
        await entity.async_set_hvac_mode(HVACMode.HEAT)

    updated = setup_integration.data[CONF_CLIMATE_ENTITIES][0]
    assert updated[CONF_CLIMATE_HVAC_MODE] == HVACMode.HEAT
    mock_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_hvac_mode_accepts_supported_non_off_modes(
    hass, setup_integration
) -> None:
    coordinator: SmartAircoCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    entity = _entity(coordinator, setup_integration, 0)

    with (
        patch.object(coordinator, "async_request_refresh", AsyncMock()) as mock_refresh,
        patch.object(entity, "async_write_ha_state"),
    ):
        await entity.async_set_hvac_mode(HVACMode.DRY)

    updated = setup_integration.data[CONF_CLIMATE_ENTITIES][0]
    assert updated[CONF_CLIMATE_HVAC_MODE] == HVACMode.DRY
    mock_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_turn_off_sets_preset_off_and_turns_off_underlying_climate(
    hass, setup_integration
) -> None:
    coordinator: SmartAircoCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    entity = _entity(coordinator, setup_integration, 0)

    with (
        patch.object(
            coordinator, "async_set_climate_mode", AsyncMock()
        ) as mock_set_mode,
        patch.object(coordinator, "async_request_refresh", AsyncMock()) as mock_refresh,
        patch.object(entity, "async_write_ha_state"),
    ):
        await entity.async_turn_off()

    updated = setup_integration.data[CONF_CLIMATE_ENTITIES][0]
    assert updated[CONF_CLIMATE_ENABLED] is False
    assert updated[CONF_CLIMATE_PRESET_MODE] == PRESET_OFF
    assert updated.get(CONF_CLIMATE_MANUAL_OVERRIDE, False) is False
    mock_set_mode.assert_awaited_once_with(
        "climate.living_room", HVACMode.OFF, track_for_antichatter=False
    )
    mock_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_turn_on_sets_preset_on_and_uses_desired_settings(
    hass, setup_integration
) -> None:
    coordinator: SmartAircoCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    entity = _entity(coordinator, setup_integration, 0)

    with (
        patch.object(
            coordinator, "async_set_climate_mode", AsyncMock()
        ) as mock_set_mode,
        patch.object(
            coordinator, "async_set_climate_temperature", AsyncMock()
        ) as mock_set_temp,
        patch.object(coordinator, "async_request_refresh", AsyncMock()) as mock_refresh,
        patch.object(entity, "async_write_ha_state"),
    ):
        await entity.async_turn_on()

    updated = setup_integration.data[CONF_CLIMATE_ENTITIES][0]
    assert updated[CONF_CLIMATE_PRESET_MODE] == PRESET_ON
    mock_set_mode.assert_awaited_once_with(
        "climate.living_room", HVACMode.COOL, track_for_antichatter=False
    )
    mock_set_temp.assert_awaited_once_with("climate.living_room", 21.0)
    mock_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_temperature_updates_running_climate(hass, setup_integration) -> None:
    coordinator: SmartAircoCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    entity = _entity(coordinator, setup_integration, 0)
    coordinator.data = {
        "sensors": {
            "climate_entities": {
                "climate.living_room": {
                    "state": HVACMode.COOL,
                    "desired_hvac_mode": HVACMode.COOL,
                }
            }
        }
    }

    with (
        patch.object(
            coordinator, "async_set_climate_temperature", AsyncMock()
        ) as mock_set_temp,
        patch.object(coordinator, "async_request_refresh", AsyncMock()) as mock_refresh,
        patch.object(entity, "async_write_ha_state"),
    ):
        await entity.async_set_temperature(**{ATTR_TEMPERATURE: 22.5})

    updated = setup_integration.data[CONF_CLIMATE_ENTITIES][0]
    assert updated[CONF_CLIMATE_TARGET_TEMPERATURE] == 22.5
    mock_set_temp.assert_awaited_once_with("climate.living_room", 22.5)
    mock_refresh.assert_awaited_once()


def test_extra_state_attributes_expose_smart_airco_fields(
    hass, mock_config_entry, seed_states
) -> None:
    coordinator = SmartAircoCoordinator(hass, mock_config_entry)
    entity = _entity(coordinator, mock_config_entry, 0)
    coordinator.data = {
        "sensors": {
            "climate_entities": {
                "climate.living_room": {
                    "name": "Living Room",
                    "enabled": True,
                    "manual_override": False,
                    "windows_open": False,
                    "power_source": "sensor",
                    "current_power": 950,
                }
            }
        },
        "decisions": {
            "climate_decisions": {
                "climate.living_room": {"should_cool": True, "reason": "priority_1"}
            }
        },
    }

    attrs = entity.extra_state_attributes
    assert attrs["smart_airco_managed"] is True
    assert attrs["smart_airco_active"] is True
    assert attrs["smart_airco_preset_mode"] == PRESET_SOLAR_BASED
    assert attrs["smart_airco_hvac_mode"] == HVACMode.COOL
    assert attrs["source_entity_id"] == "climate.living_room"
    assert attrs[ATTR_SMART_AIRCO_SOLAR_AUTOMATION_ENABLED] is True
    assert attrs["decision_reason"] == "priority_1"
