from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_airco import async_setup_entry, async_unload_entry
from custom_components.smart_airco.const import (
    CONF_CLIMATE_ENTITIES,
    CONF_NET_EXPORT_SENSOR,
    CONF_SOLAR_FORECAST_SENSOR,
    CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)
from custom_components.smart_airco.coordinator import SmartAircoCoordinator


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Smart Airco",
        data={
            CONF_SOLAR_FORECAST_SENSOR: "sensor.solar_forecast",
            CONF_SOLAR_PRODUCTION_SENSOR: "sensor.solar_production",
            CONF_NET_EXPORT_SENSOR: "sensor.net_export",
            CONF_UPDATE_INTERVAL: 300,
            CONF_CLIMATE_ENTITIES: [
                {
                    "entity_id": "climate.living_room",
                    "name": "Living Room",
                    "priority": 1,
                    "wattage": 1000,
                    "power_sensor": "sensor.living_room_power",
                    "use_estimated_power": False,
                    "window_sensors": ["binary_sensor.living_room_window"],
                    "enabled": True,
                },
                {
                    "entity_id": "climate.bedroom",
                    "name": "Bedroom",
                    "priority": 2,
                    "wattage": 800,
                    "power_sensor": None,
                    "use_estimated_power": True,
                    "window_sensors": [],
                    "enabled": True,
                },
            ],
        },
    )


@pytest.fixture
def enable_custom_integrations() -> bool:
    return True


@pytest.fixture
def seed_states(hass) -> None:
    hass.states.async_set("sensor.solar_forecast", "3500", {"estimate10": 3500})
    hass.states.async_set("sensor.solar_production", "3000")
    hass.states.async_set("sensor.net_export", "1500")
    hass.states.async_set(
        "climate.living_room",
        "off",
        {
            "current_temperature": 24.0,
            "temperature": 21.0,
            "hvac_modes": ["off", "auto", "heat", "cool", "dry", "fan_only"],
        },
    )
    hass.states.async_set(
        "climate.bedroom",
        "off",
        {
            "current_temperature": 23.0,
            "temperature": 20.0,
            "hvac_modes": ["off", "cool", "heat"],
        },
    )
    hass.states.async_set("sensor.living_room_power", "950", {"device_class": "power"})
    hass.states.async_set(
        "binary_sensor.living_room_window",
        "off",
        {"device_class": "window"},
    )


@pytest.fixture
def panel_patches() -> Generator[None]:
    with (
        patch("custom_components.smart_airco.async_register_panel", AsyncMock()),
        patch("custom_components.smart_airco.async_unregister_panel", AsyncMock()),
    ):
        yield


@pytest_asyncio.fixture
async def setup_integration(
    hass, mock_config_entry, seed_states, panel_patches
) -> AsyncGenerator[MockConfigEntry]:
    mock_config_entry.add_to_hass(hass)
    with (
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
        patch.object(
            hass.config_entries, "async_reload", AsyncMock(return_value=True)
        ) as mock_reload,
        patch.object(
            SmartAircoCoordinator,
            "async_config_entry_first_refresh",
            AsyncMock(return_value=None),
        ),
    ):
        hass.data["smart_airco_test_reload_mock"] = mock_reload
        assert await async_setup_entry(hass, mock_config_entry)
        await hass.async_block_till_done()
        try:
            yield mock_config_entry
        finally:
            await async_unload_entry(hass, mock_config_entry)
            hass.data.pop("smart_airco_test_reload_mock", None)
            await hass.async_block_till_done()
