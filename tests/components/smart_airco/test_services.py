from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_airco import async_setup_entry, async_unload_entry
from custom_components.smart_airco.const import (
    CONF_CLIMATE_MANUAL_OVERRIDE,
    CONF_CONTROLLER_HVAC_MODE,
    CONF_CONTROLLER_TARGET_TEMPERATURE,
    DOMAIN,
)
from custom_components.smart_airco.coordinator import SmartAircoCoordinator


@pytest.mark.asyncio
async def test_service_set_climate_priority_updates_entry_data(
    hass, setup_integration
) -> None:
    await hass.services.async_call(
        DOMAIN,
        "set_climate_priority",
        {"entity_id": "climate.bedroom", "priority": 1},
        blocking=True,
    )
    await hass.async_block_till_done()

    climate_entities = setup_integration.data["climate_entities"]
    bedroom = next(c for c in climate_entities if c["entity_id"] == "climate.bedroom")
    assert bedroom["priority"] == 1


@pytest.mark.asyncio
async def test_service_toggle_climate_entity_disables_and_turns_off_ac(
    hass, setup_integration
) -> None:
    coordinator: SmartAircoCoordinator = hass.data[DOMAIN][setup_integration.entry_id]

    with patch.object(
        coordinator, "async_set_climate_mode", AsyncMock()
    ) as mock_set_mode:
        await hass.services.async_call(
            DOMAIN,
            "toggle_climate_entity",
            {"entity_id": "climate.bedroom", "enabled": False},
            blocking=True,
        )
        await hass.async_block_till_done()

    bedroom = next(
        c
        for c in setup_integration.data["climate_entities"]
        if c["entity_id"] == "climate.bedroom"
    )
    assert bedroom["enabled"] is False
    mock_set_mode.assert_awaited_once_with(
        "climate.bedroom",
        "off",
        track_for_antichatter=False,
    )


@pytest.mark.asyncio
async def test_service_toggle_climate_entity_reenables_from_manual_override(
    hass, setup_integration
) -> None:
    climate_entities = []
    for climate in setup_integration.data["climate_entities"]:
        updated = dict(climate)
        if updated["entity_id"] == "climate.bedroom":
            updated["enabled"] = False
            updated[CONF_CLIMATE_MANUAL_OVERRIDE] = True
        climate_entities.append(updated)

    hass.config_entries.async_update_entry(
        setup_integration,
        data={**setup_integration.data, "climate_entities": climate_entities},
    )
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        "toggle_climate_entity",
        {"entity_id": "climate.bedroom", "enabled": True},
        blocking=True,
    )
    await hass.async_block_till_done()

    bedroom = next(
        c
        for c in setup_integration.data["climate_entities"]
        if c["entity_id"] == "climate.bedroom"
    )
    assert bedroom["enabled"] is True
    assert bedroom[CONF_CLIMATE_MANUAL_OVERRIDE] is False


@pytest.mark.asyncio
async def test_service_set_climate_power_updates_selected_fields(
    hass, setup_integration
) -> None:
    await hass.services.async_call(
        DOMAIN,
        "set_climate_power",
        {
            "entity_id": "climate.bedroom",
            "use_estimated_power": False,
            "wattage": 900,
            "power_sensor": None,
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    bedroom = next(
        c
        for c in setup_integration.data["climate_entities"]
        if c["entity_id"] == "climate.bedroom"
    )
    assert bedroom["use_estimated_power"] is False
    assert bedroom["wattage"] == 900
    assert bedroom["power_sensor"] is None


@pytest.mark.asyncio
async def test_service_set_climate_windows_replaces_sensor_list(
    hass, setup_integration
) -> None:
    await hass.services.async_call(
        DOMAIN,
        "set_climate_windows",
        {
            "entity_id": "climate.bedroom",
            "window_sensors": ["binary_sensor.living_room_window"],
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    bedroom = next(
        c
        for c in setup_integration.data["climate_entities"]
        if c["entity_id"] == "climate.bedroom"
    )
    assert bedroom["window_sensors"] == ["binary_sensor.living_room_window"]


@pytest.mark.asyncio
async def test_service_add_and_remove_climate(hass, setup_integration) -> None:
    hass.states.async_set(
        "climate.office",
        "off",
        {"current_temperature": 22.0, "temperature": 20.0},
    )

    await hass.services.async_call(
        DOMAIN,
        "add_climate",
        {
            "entity_id": "climate.office",
            "name": "Office",
            "priority": 3,
            "wattage": 700,
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    assert any(
        c["entity_id"] == "climate.office"
        for c in setup_integration.data["climate_entities"]
    )

    await hass.services.async_call(
        DOMAIN,
        "remove_climate",
        {"entity_id": "climate.office"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert not any(
        c["entity_id"] == "climate.office"
        for c in setup_integration.data["climate_entities"]
    )


@pytest.mark.asyncio
async def test_service_set_global_settings_updates_entry_data(
    hass, setup_integration
) -> None:
    hass.states.async_set("sensor.production_alt", "2500")

    await hass.services.async_call(
        DOMAIN,
        "set_global_settings",
        {
            "controller_hvac_mode": "dry",
            "controller_target_temperature": 22.5,
            "forecast_sensor": None,
            "production_sensor": "sensor.production_alt",
            "net_export_sensor": "sensor.net_export",
            "update_interval_minutes": 15,
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    assert setup_integration.data["solar_forecast_sensor"] is None
    assert setup_integration.data[CONF_CONTROLLER_HVAC_MODE] == "dry"
    assert setup_integration.data[CONF_CONTROLLER_TARGET_TEMPERATURE] == 22.5
    assert setup_integration.data["solar_production_sensor"] == "sensor.production_alt"
    assert setup_integration.data["update_interval"] == 900


@pytest.mark.asyncio
async def test_refresh_and_execute_services_call_coordinator_methods(
    hass, setup_integration
) -> None:
    coordinator: SmartAircoCoordinator = hass.data[DOMAIN][setup_integration.entry_id]

    with (
        patch.object(coordinator, "async_request_refresh", AsyncMock()) as mock_refresh,
        patch.object(
            coordinator, "async_execute_decisions", AsyncMock()
        ) as mock_execute,
    ):
        await hass.services.async_call(DOMAIN, "evaluate_conditions", {}, blocking=True)
        await hass.services.async_call(DOMAIN, "force_update", {}, blocking=True)
        await hass.services.async_call(DOMAIN, "execute_decisions", {}, blocking=True)
        await hass.async_block_till_done()

    assert mock_refresh.await_count == 2
    mock_execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_find_coordinator_for_climate_no_domain_key(
    hass, setup_integration
) -> None:
    """Service should log an error (not crash) when hass.data has no DOMAIN key."""
    # Remove all coordinators so DOMAIN key becomes empty, then remove it entirely
    saved = dict(hass.data.get(DOMAIN, {}))
    hass.data.pop(DOMAIN, None)

    # Calling set_climate_priority for a non-existent entity when DOMAIN is missing
    # should gracefully return without raising.
    await hass.services.async_call(
        DOMAIN,
        "set_climate_priority",
        {"entity_id": "climate.nonexistent", "priority": 1},
        blocking=True,
    )
    await hass.async_block_till_done()

    # Restore state so fixture teardown can clean up
    hass.data[DOMAIN] = saved


@pytest.mark.asyncio
async def test_toggle_climate_entity_noop_when_already_same_state(
    hass, setup_integration
) -> None:
    """Toggling to the current enabled state should be a no-op (no config update)."""
    bedroom = next(
        c
        for c in setup_integration.data["climate_entities"]
        if c["entity_id"] == "climate.bedroom"
    )
    original_enabled = bedroom["enabled"]  # True

    with patch.object(hass.config_entries, "async_update_entry") as mock_update:
        await hass.services.async_call(
            DOMAIN,
            "toggle_climate_entity",
            {"entity_id": "climate.bedroom", "enabled": original_enabled},
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_add_climate_service_targets_requested_config_entry(
    hass, setup_integration, panel_patches, seed_states
) -> None:
    second_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Smart Airco Upstairs",
        data={
            **setup_integration.data,
            "climate_entities": [],
        },
    )
    second_entry.add_to_hass(hass)

    with (
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
        patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)),
        patch.object(
            SmartAircoCoordinator,
            "async_config_entry_first_refresh",
            AsyncMock(return_value=None),
        ),
    ):
        assert await async_setup_entry(hass, second_entry)
        await hass.async_block_till_done()

    try:
        hass.states.async_set(
            "climate.office",
            "off",
            {"current_temperature": 22.0, "temperature": 20.0},
        )

        await hass.services.async_call(
            DOMAIN,
            "add_climate",
            {
                "config_entry_id": second_entry.entry_id,
                "entity_id": "climate.office",
                "name": "Office",
                "priority": 3,
                "wattage": 700,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

        assert not any(
            c["entity_id"] == "climate.office"
            for c in setup_integration.data["climate_entities"]
        )
        assert any(
            c["entity_id"] == "climate.office"
            for c in second_entry.data["climate_entities"]
        )
    finally:
        await async_unload_entry(hass, second_entry)
        await hass.async_block_till_done()
