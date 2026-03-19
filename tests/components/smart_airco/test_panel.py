from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_airco import async_setup_entry, async_unload_entry
from custom_components.smart_airco.const import DOMAIN
from custom_components.smart_airco.coordinator import SmartAircoCoordinator


@pytest.mark.asyncio
async def test_custom_panel_registers_once_and_unregisters_on_last_entry(
    hass, mock_config_entry, seed_states
) -> None:
    first_entry = mock_config_entry
    second_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Smart Airco Upstairs",
        data={**mock_config_entry.data, "climate_entities": []},
    )
    first_entry.add_to_hass(hass)
    second_entry.add_to_hass(hass)

    with (
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
        patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)),
        patch.object(
            SmartAircoCoordinator,
            "async_config_entry_first_refresh",
            AsyncMock(return_value=None),
        ),
        patch(
            "custom_components.smart_airco.async_register_panel", AsyncMock()
        ) as mock_register,
        patch(
            "custom_components.smart_airco.async_unregister_panel", AsyncMock()
        ) as mock_unregister,
    ):
        assert await async_setup_entry(hass, first_entry)
        assert await async_setup_entry(hass, second_entry)
        await hass.async_block_till_done()

        mock_register.assert_awaited_once()

        await async_unload_entry(hass, first_entry)
        await hass.async_block_till_done()
        mock_unregister.assert_not_called()

        await async_unload_entry(hass, second_entry)
        await hass.async_block_till_done()
        mock_unregister.assert_awaited_once()


@pytest.mark.asyncio
async def test_setup_fails_if_panel_registration_fails(
    hass, mock_config_entry, seed_states
) -> None:
    mock_config_entry.add_to_hass(hass)

    with (
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
        patch.object(
            hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)
        ) as mock_unload_platforms,
        patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)),
        patch.object(
            SmartAircoCoordinator,
            "async_config_entry_first_refresh",
            AsyncMock(return_value=None),
        ),
        patch(
            "custom_components.smart_airco.async_register_panel",
            AsyncMock(side_effect=RuntimeError("panel boom")),
        ),
    ):
        assert await async_setup_entry(hass, mock_config_entry) is False

    assert mock_config_entry.entry_id not in hass.data[DOMAIN]
    mock_unload_platforms.assert_awaited_once()
