from __future__ import annotations

import pytest
from homeassistant.components.diagnostics import REDACTED

from custom_components.smart_airco.const import DOMAIN
from custom_components.smart_airco.diagnostics import (
    _sanitize_runtime_data,
    async_get_config_entry_diagnostics,
)


@pytest.mark.asyncio
async def test_config_entry_diagnostics_include_config_and_runtime_data(
    hass, setup_integration
) -> None:
    coordinator = hass.data[DOMAIN][setup_integration.entry_id]
    coordinator.data = {
        "sensors": {
            "critical_input_errors": [],
            "climate_entities": {
                "climate.bedroom": {"name": "Bedroom", "enabled": True},
            },
        },
        "calculations": {"predicted_surplus": 1200, "critical_inputs_valid": True},
        "decisions": {
            "reason": "running_1_units",
            "critical_input_errors": [],
            "climate_decisions": {
                "climate.bedroom": {"should_cool": False, "reason": "disabled"},
            },
        },
    }

    diagnostics = await async_get_config_entry_diagnostics(hass, setup_integration)

    assert diagnostics["config_entry"]["entry_id"] == setup_integration.entry_id
    assert diagnostics["config_entry"]["data"]["solar_forecast_sensor"] == REDACTED
    assert diagnostics["coordinator"]["last_update_success"] is True
    assert diagnostics["coordinator"]["update_interval_seconds"] == 300
    assert (
        diagnostics["coordinator"]["data"]["decisions"]["reason"] == "running_1_units"
    )
    assert (
        diagnostics["coordinator"]["data"]["sensors"]["climate_entities"][0][
            "entity_id"
        ]
        == REDACTED
    )
    assert (
        diagnostics["coordinator"]["data"]["sensors"]["climate_entities"][0]["name"]
        == REDACTED
    )


def test_sanitize_runtime_data_with_none_sensors_and_decisions() -> None:
    """_sanitize_runtime_data should not crash when sensors/decisions are None."""
    result = _sanitize_runtime_data({"sensors": None, "decisions": None})
    assert result is not None
    # sensors starts as {} then gets climate_entities normalized to a list
    assert result["sensors"] == {"climate_entities": []}
    # decisions starts as {} then gets climate_decisions normalized to a list
    assert result["decisions"] == {"climate_decisions": []}


def test_sanitize_runtime_data_returns_none_for_none_input() -> None:
    """_sanitize_runtime_data(None) should return None."""
    assert _sanitize_runtime_data(None) is None
