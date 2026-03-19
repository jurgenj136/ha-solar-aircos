"""Diagnostics support for Smart Airco."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_TO_REDACT = {
    "entity_id",
    "name",
    "power_sensor",
    "window_sensors",
    "solar_forecast_sensor",
    "solar_production_sensor",
    "net_export_sensor",
    "forecast_sensor",
    "production_sensor",
    "configured_climate_entity_ids",
}


def _sanitize_runtime_data(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return coordinator data in a form that can be safely redacted."""
    if data is None:
        return None

    sanitized = dict(data)
    sensors = dict(sanitized.get("sensors", {}))
    climate_entities = sensors.get("climate_entities", {})
    if isinstance(climate_entities, dict):
        sensors["climate_entities"] = [
            {"entity_id": entity_id, **climate_data}
            for entity_id, climate_data in climate_entities.items()
        ]

    decisions = dict(sanitized.get("decisions", {}))
    climate_decisions = decisions.get("climate_decisions", {})
    if isinstance(climate_decisions, dict):
        decisions["climate_decisions"] = [
            {"entity_id": entity_id, **decision}
            for entity_id, decision in climate_decisions.items()
        ]

    sanitized["sensors"] = sensors
    sanitized["decisions"] = decisions
    return sanitized


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data.get(DOMAIN, {}).get(config_entry.entry_id)

    return async_redact_data(
        {
            "config_entry": {
                "entry_id": config_entry.entry_id,
                "title": config_entry.title,
                "domain": config_entry.domain,
                "version": config_entry.version,
                "data": dict(config_entry.data),
            },
            "coordinator": {
                "last_update_success": coordinator.last_update_success
                if coordinator
                else None,
                "update_interval_seconds": (
                    int(coordinator.update_interval.total_seconds())
                    if coordinator and coordinator.update_interval
                    else None
                ),
                "data": _sanitize_runtime_data(coordinator.data)
                if coordinator
                else None,
            },
        },
        _TO_REDACT,
    )
