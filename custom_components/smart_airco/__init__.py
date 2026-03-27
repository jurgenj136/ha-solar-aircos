"""Smart Air Conditioning Controller Integration."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.components.climate.const import HVACMode
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_CLIMATE_ENTITIES,
    CONF_CLIMATE_HVAC_MODE,
    CONF_CLIMATE_PRESET_MODE,
    CONF_CLIMATE_TARGET_TEMPERATURE,
    CONF_CONTROLLER_HVAC_MODE,
    CONF_CONTROLLER_TARGET_TEMPERATURE,
    CONF_CONTROLLER_ENABLED,
    CONF_CLIMATE_ENTITY_ID,
    CONF_CLIMATE_ENABLED,
    CONF_CLIMATE_MANUAL_OVERRIDE,
    CONF_CLIMATE_PRIORITY,
    DOMAIN,
    DEFAULT_CLIMATE_HVAC_MODE,
    DEFAULT_CLIMATE_PRESET_MODE,
    DEFAULT_CLIMATE_TARGET_TEMPERATURE,
    DEFAULT_CONTROLLER_HVAC_MODE,
    DEFAULT_CONTROLLER_TARGET_TEMPERATURE,
    PRESET_OFF,
    PRESET_SOLAR_BASED,
    SMART_AIRCO_HVAC_MODES,
    SERVICE_EVALUATE_CONDITIONS,
    SERVICE_EXECUTE_DECISIONS,
    SERVICE_FORCE_UPDATE,
    SERVICE_SET_CLIMATE_PRIORITY,
    SERVICE_TOGGLE_CLIMATE_ENTITY,
    SERVICE_SET_CLIMATE_POWER,
    SERVICE_SET_CLIMATE_WINDOWS,
    SERVICE_ADD_CLIMATE,
    SERVICE_REMOVE_CLIMATE,
    SERVICE_SET_GLOBAL_SETTINGS,
)
from .coordinator import SmartAircoCoordinator
from .homekit_patch import async_acquire_homekit_patch, async_release_homekit_patch
from .panel import async_register_panel, async_unregister_panel

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SENSOR,
]


# Service schemas
SERVICE_EVALUATE_CONDITIONS_SCHEMA = vol.Schema(
    {vol.Optional("config_entry_id"): cv.string}
)
SERVICE_FORCE_UPDATE_SCHEMA = vol.Schema({vol.Optional("config_entry_id"): cv.string})
SERVICE_EXECUTE_DECISIONS_SCHEMA = vol.Schema(
    {vol.Optional("config_entry_id"): cv.string}
)

SERVICE_SET_CLIMATE_PRIORITY_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("priority"): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
    }
)

SERVICE_TOGGLE_CLIMATE_ENTITY_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("enabled"): cv.boolean,
    }
)

SERVICE_SET_CLIMATE_POWER_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("use_estimated_power"): cv.boolean,
        vol.Optional("wattage"): vol.All(vol.Coerce(int), vol.Range(min=100, max=5000)),
        vol.Optional("power_sensor"): vol.Any(None, cv.entity_id),
    }
)

SERVICE_SET_CLIMATE_WINDOWS_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("window_sensors"): [cv.entity_id],
    }
)

SERVICE_ADD_CLIMATE_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("name"): cv.string,
        vol.Optional("priority"): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
        vol.Optional("use_estimated_power", default=True): cv.boolean,
        vol.Optional("wattage", default=1000): vol.All(
            vol.Coerce(int), vol.Range(min=100, max=5000)
        ),
        vol.Optional("power_sensor"): cv.entity_id,
        vol.Optional("window_sensors", default=[]): [cv.entity_id],
        vol.Optional("enabled", default=True): cv.boolean,
    }
)

SERVICE_REMOVE_CLIMATE_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
        vol.Required("entity_id"): cv.entity_id,
    }
)

SERVICE_SET_GLOBAL_SETTINGS_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
        vol.Optional("controller_hvac_mode"): vol.In(SMART_AIRCO_HVAC_MODES),
        vol.Optional("controller_target_temperature"): vol.All(vol.Coerce(float)),
        vol.Optional("forecast_sensor"): vol.Any(None, cv.entity_id),
        vol.Optional("production_sensor"): vol.Any(None, cv.entity_id),
        vol.Optional("net_export_sensor"): vol.Any(None, cv.entity_id),
        vol.Optional("update_interval_minutes"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=60)
        ),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart Airco from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    register_panel = not hass.data[DOMAIN]
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    entry = await _async_migrate_entry_data(hass, entry)
    async_acquire_homekit_patch(hass)

    try:
        # Create the coordinator
        coordinator = SmartAircoCoordinator(hass, entry)

        # Fetch initial data so we have data when entities are added
        await coordinator.async_config_entry_first_refresh()
        await coordinator.async_execute_decisions()

        hass.data[DOMAIN][entry.entry_id] = coordinator
        entry.async_on_unload(coordinator.async_setup_manual_override_tracking())
        entry.async_on_unload(
            coordinator.async_add_listener(
                lambda: hass.async_create_task(coordinator.async_execute_decisions())
            )
        )

        # Set up all platforms for this config entry
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Register native custom panel once for the domain
        if register_panel:
            try:
                await async_register_panel(hass)
            except Exception:
                _LOGGER.exception("Failed to register Smart Airco sidebar panel")
                await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
                hass.data[DOMAIN].pop(entry.entry_id, None)
                async_release_homekit_patch(hass)
                return False

        # Register services
        await _async_register_services(hass)
    except Exception:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        async_release_homekit_patch(hass)
        raise

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload an entry after config changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        async_release_homekit_patch(hass)

    # Unregister services if this is the last entry
    if not hass.data[DOMAIN]:
        await _async_unregister_services(hass)

        # Remove sidebar panel when no instances remain
        try:
            await async_unregister_panel(hass)
        except Exception:  # pragma: no cover
            _LOGGER.debug("Sidebar panel already removed or not present")

    return unload_ok


async def _async_migrate_entry_data(
    hass: HomeAssistant, entry: ConfigEntry
) -> ConfigEntry:
    """Migrate older Smart Airco config data to the current per-climate model."""
    climate_entities = entry.data.get(CONF_CLIMATE_ENTITIES, [])
    if not isinstance(climate_entities, list):
        return entry

    migrated_climates = []
    changed = False
    default_hvac_mode = entry.data.get(
        CONF_CONTROLLER_HVAC_MODE, DEFAULT_CONTROLLER_HVAC_MODE
    )
    default_target_temperature = entry.data.get(
        CONF_CONTROLLER_TARGET_TEMPERATURE, DEFAULT_CONTROLLER_TARGET_TEMPERATURE
    )

    for climate in climate_entities:
        if not isinstance(climate, dict):
            migrated_climates.append(climate)
            continue

        updated = dict(climate)
        if CONF_CLIMATE_PRESET_MODE not in updated:
            updated[CONF_CLIMATE_PRESET_MODE] = (
                PRESET_SOLAR_BASED
                if updated.get(CONF_CLIMATE_ENABLED, True)
                else PRESET_OFF
            )
            changed = True
        if CONF_CLIMATE_HVAC_MODE not in updated:
            updated[CONF_CLIMATE_HVAC_MODE] = default_hvac_mode
            changed = True
        if CONF_CLIMATE_TARGET_TEMPERATURE not in updated:
            updated[CONF_CLIMATE_TARGET_TEMPERATURE] = default_target_temperature
            changed = True
        should_be_enabled = updated.get(CONF_CLIMATE_PRESET_MODE) != PRESET_OFF
        if updated.get(CONF_CLIMATE_ENABLED, True) != should_be_enabled:
            updated[CONF_CLIMATE_ENABLED] = should_be_enabled
            changed = True
        migrated_climates.append(updated)

    if changed:
        new_data = {**entry.data, CONF_CLIMATE_ENTITIES: migrated_climates}
        hass.config_entries.async_update_entry(entry, data=new_data)

    return entry


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register Smart Airco services."""

    if hass.services.has_service(DOMAIN, SERVICE_EVALUATE_CONDITIONS):
        return

    def _get_default_coordinator(
        *, reject_if_ambiguous: bool = False
    ) -> SmartAircoCoordinator | None:
        coordinators = hass.data.get(DOMAIN, {})
        if reject_if_ambiguous and len(coordinators) > 1:
            _LOGGER.error(
                "Multiple Smart Airco instances exist; config_entry_id is required for this service call"
            )
            return None
        return next(iter(coordinators.values()), None)

    def _get_coordinator_by_entry_id(
        config_entry_id: str | None,
        *,
        reject_if_ambiguous: bool = False,
    ) -> SmartAircoCoordinator | None:
        if not config_entry_id:
            return _get_default_coordinator(reject_if_ambiguous=reject_if_ambiguous)
        coordinator = hass.data.get(DOMAIN, {}).get(config_entry_id)
        if coordinator is None:
            _LOGGER.error(
                "Smart Airco config entry %s not found",
                config_entry_id,
            )
        return coordinator

    def _find_coordinator_for_climate(
        entity_id: str,
        config_entry_id: str | None = None,
    ) -> tuple[SmartAircoCoordinator | None, list[dict[str, Any]], int | None]:
        if config_entry_id:
            coordinators = [
                coordinator
                for coordinator in [hass.data.get(DOMAIN, {}).get(config_entry_id)]
                if coordinator is not None
            ]
        else:
            coordinators = list(hass.data[DOMAIN].values())

        for coordinator in coordinators:
            climate_entities = deepcopy(
                coordinator.config.get(CONF_CLIMATE_ENTITIES, [])
            )
            for index, climate_config in enumerate(climate_entities):
                if climate_config.get(CONF_CLIMATE_ENTITY_ID) == entity_id:
                    return coordinator, climate_entities, index
        return None, [], None

    def _update_entry_climates(
        coordinator: SmartAircoCoordinator, climate_entities: list[dict[str, Any]]
    ) -> None:
        hass.config_entries.async_update_entry(
            coordinator.entry,
            data={**coordinator.entry.data, CONF_CLIMATE_ENTITIES: climate_entities},
        )

    async def handle_evaluate_conditions(call: ServiceCall) -> None:
        """Handle evaluate conditions service call."""
        if config_entry_id := call.data.get("config_entry_id"):
            coordinators = [
                coordinator
                for coordinator in [_get_coordinator_by_entry_id(config_entry_id)]
                if coordinator is not None
            ]
        else:
            coordinators = list(hass.data[DOMAIN].values())

        for coordinator in coordinators:
            await coordinator.async_request_refresh()
        _LOGGER.info(
            "Manually triggered condition evaluation for %d Smart Airco instance(s)",
            len(coordinators),
        )

    async def handle_force_update(call: ServiceCall) -> None:
        """Handle force update service call."""
        if config_entry_id := call.data.get("config_entry_id"):
            coordinators = [
                coordinator
                for coordinator in [_get_coordinator_by_entry_id(config_entry_id)]
                if coordinator is not None
            ]
        else:
            coordinators = list(hass.data[DOMAIN].values())

        for coordinator in coordinators:
            await coordinator.async_request_refresh()
        _LOGGER.info("Forced update for %d Smart Airco instance(s)", len(coordinators))

    async def handle_execute_decisions(call: ServiceCall) -> None:
        """Handle execute decisions service call."""
        if config_entry_id := call.data.get("config_entry_id"):
            coordinators = [
                coordinator
                for coordinator in [_get_coordinator_by_entry_id(config_entry_id)]
                if coordinator is not None
            ]
        else:
            coordinators = list(hass.data[DOMAIN].values())

        for coordinator in coordinators:
            await coordinator.async_execute_decisions()
        _LOGGER.info(
            "Manually executed decisions for %d Smart Airco instance(s)",
            len(coordinators),
        )

    async def handle_set_climate_priority(call: ServiceCall) -> None:
        """Handle set climate priority service call."""
        entity_id = call.data["entity_id"]
        new_priority = call.data["priority"]
        config_entry_id = call.data.get("config_entry_id")

        coordinator, climate_entities, climate_index = _find_coordinator_for_climate(
            entity_id,
            config_entry_id,
        )
        if not coordinator:
            _LOGGER.error(
                "Climate entity %s not found in any Smart Airco configuration",
                entity_id,
            )
            return
        if climate_index is None:
            _LOGGER.error("Climate entity %s index not found", entity_id)
            return

        old_priority = climate_entities[climate_index].get(CONF_CLIMATE_PRIORITY, 999)
        climate_entities[climate_index][CONF_CLIMATE_PRIORITY] = new_priority
        _update_entry_climates(coordinator, climate_entities)
        _LOGGER.info(
            "Updated priority for %s from %d to %d",
            entity_id,
            old_priority,
            new_priority,
        )

    async def handle_toggle_climate_entity(call: ServiceCall) -> None:
        """Handle toggle climate entity service call."""
        entity_id = call.data["entity_id"]
        enabled = call.data["enabled"]
        config_entry_id = call.data.get("config_entry_id")

        coordinator, climate_entities, climate_index = _find_coordinator_for_climate(
            entity_id,
            config_entry_id,
        )
        if not coordinator:
            _LOGGER.error(
                "Climate entity %s not found in any Smart Airco configuration",
                entity_id,
            )
            return
        if climate_index is None:
            _LOGGER.error("Climate entity %s index not found", entity_id)
            return

        old_enabled = climate_entities[climate_index].get(CONF_CLIMATE_ENABLED, True)
        climate_entities[climate_index][CONF_CLIMATE_ENABLED] = enabled
        climate_entities[climate_index][CONF_CLIMATE_PRESET_MODE] = (
            PRESET_SOLAR_BASED if enabled else PRESET_OFF
        )
        climate_entities[climate_index][CONF_CLIMATE_MANUAL_OVERRIDE] = False
        if not enabled:
            await coordinator.async_set_climate_mode(
                entity_id,
                "off",
                track_for_antichatter=False,
            )
        _update_entry_climates(coordinator, climate_entities)
        _LOGGER.info(
            "%s automatic control for %s",
            "Enabled" if enabled else "Disabled",
            entity_id,
        )
        if old_enabled == enabled:
            return

    async def handle_set_climate_power(call: ServiceCall) -> None:
        """Handle updating per-AC power settings."""
        entity_id = call.data["entity_id"]
        config_entry_id = call.data.get("config_entry_id")
        coordinator, climate_entities, climate_index = _find_coordinator_for_climate(
            entity_id,
            config_entry_id,
        )
        if not coordinator:
            _LOGGER.error(
                "Climate entity %s not found in any Smart Airco configuration",
                entity_id,
            )
            return
        if climate_index is None:
            _LOGGER.error("Climate entity %s index not found", entity_id)
            return

        changed = False
        climate_config = climate_entities[climate_index]
        if "use_estimated_power" in call.data:
            climate_config["use_estimated_power"] = call.data["use_estimated_power"]
            changed = True
        if "wattage" in call.data:
            climate_config["wattage"] = call.data["wattage"]
            changed = True
        if "power_sensor" in call.data:
            climate_config["power_sensor"] = call.data["power_sensor"] or None
            changed = True
        if changed:
            _update_entry_climates(coordinator, climate_entities)

    async def handle_set_climate_windows(call: ServiceCall) -> None:
        """Handle updating per-AC window sensors."""
        entity_id = call.data["entity_id"]
        sensors = call.data["window_sensors"]
        config_entry_id = call.data.get("config_entry_id")
        coordinator, climate_entities, climate_index = _find_coordinator_for_climate(
            entity_id,
            config_entry_id,
        )
        if not coordinator:
            _LOGGER.error(
                "Climate entity %s not found in any Smart Airco configuration",
                entity_id,
            )
            return
        if climate_index is None:
            _LOGGER.error("Climate entity %s index not found", entity_id)
            return

        climate_entities[climate_index]["window_sensors"] = sensors
        _update_entry_climates(coordinator, climate_entities)

    async def handle_add_climate(call: ServiceCall) -> None:
        """Add a new climate entity to the configuration."""
        data = call.data
        entity_id = data["entity_id"]
        coordinator = _get_coordinator_by_entry_id(
            data.get("config_entry_id"),
            reject_if_ambiguous=True,
        )
        if coordinator is None:
            _LOGGER.error("No Smart Airco coordinator available")
            return
        climate_entities = deepcopy(coordinator.config.get(CONF_CLIMATE_ENTITIES, []))
        # Prevent duplicates
        if any(c.get(CONF_CLIMATE_ENTITY_ID) == entity_id for c in climate_entities):
            _LOGGER.warning("Climate %s already configured", entity_id)
            return
        new_cfg = {
            CONF_CLIMATE_ENTITY_ID: entity_id,
            "name": data.get(
                "name", entity_id.split(".")[-1].replace("_", " ").title()
            ),
            "priority": data.get("priority", (len(climate_entities) + 1)),
            "manual_override": False,
            CONF_CLIMATE_PRESET_MODE: (
                DEFAULT_CLIMATE_PRESET_MODE if data.get("enabled", True) else PRESET_OFF
            ),
            CONF_CLIMATE_HVAC_MODE: coordinator.climate_hvac_mode(
                {CONF_CLIMATE_ENTITY_ID: entity_id}
            ),
            CONF_CLIMATE_TARGET_TEMPERATURE: coordinator.config.get(
                CONF_CONTROLLER_TARGET_TEMPERATURE, DEFAULT_CLIMATE_TARGET_TEMPERATURE
            ),
            "use_estimated_power": data.get("use_estimated_power", True),
            "wattage": data.get("wattage", 1000),
            "power_sensor": data.get("power_sensor"),
            "window_sensors": data.get("window_sensors", []),
            "enabled": data.get("enabled", True),
        }
        climate_entities.append(new_cfg)
        _update_entry_climates(coordinator, climate_entities)

    async def handle_remove_climate(call: ServiceCall) -> None:
        """Remove a climate entity from configuration."""
        entity_id = call.data["entity_id"]
        coordinator = _get_coordinator_by_entry_id(
            call.data.get("config_entry_id"),
            reject_if_ambiguous=True,
        )
        if coordinator is None:
            _LOGGER.error("No Smart Airco coordinator available")
            return
        climate_entities = [
            c
            for c in deepcopy(coordinator.config.get(CONF_CLIMATE_ENTITIES, []))
            if c.get(CONF_CLIMATE_ENTITY_ID) != entity_id
        ]
        _update_entry_climates(coordinator, climate_entities)

    async def handle_set_global(call: ServiceCall) -> None:
        """Update global sensors and update interval."""
        data = call.data
        coordinator = _get_coordinator_by_entry_id(
            data.get("config_entry_id"),
            reject_if_ambiguous=True,
        )
        if coordinator is None:
            _LOGGER.error("No Smart Airco coordinator available")
            return
        new_data = dict(coordinator.entry.data)
        if "forecast_sensor" in data:
            new_data["solar_forecast_sensor"] = data["forecast_sensor"] or None
        if "production_sensor" in data:
            new_data["solar_production_sensor"] = data["production_sensor"] or None
        if "net_export_sensor" in data:
            new_data["net_export_sensor"] = data["net_export_sensor"] or None
        if "update_interval_minutes" in data:
            new_data["update_interval"] = data["update_interval_minutes"] * 60
        new_data.setdefault(CONF_CONTROLLER_ENABLED, True)
        new_data.setdefault(CONF_CONTROLLER_HVAC_MODE, DEFAULT_CONTROLLER_HVAC_MODE)
        new_data.setdefault(
            CONF_CONTROLLER_TARGET_TEMPERATURE, DEFAULT_CONTROLLER_TARGET_TEMPERATURE
        )
        climate_entities = deepcopy(new_data.get(CONF_CLIMATE_ENTITIES, []))
        if "controller_hvac_mode" in data:
            new_data[CONF_CONTROLLER_HVAC_MODE] = data["controller_hvac_mode"]
            for climate in climate_entities:
                climate[CONF_CLIMATE_HVAC_MODE] = data["controller_hvac_mode"]
        if "controller_target_temperature" in data:
            new_data[CONF_CONTROLLER_TARGET_TEMPERATURE] = data[
                "controller_target_temperature"
            ]
            for climate in climate_entities:
                climate[CONF_CLIMATE_TARGET_TEMPERATURE] = data[
                    "controller_target_temperature"
                ]
        new_data[CONF_CLIMATE_ENTITIES] = climate_entities
        hass.config_entries.async_update_entry(coordinator.entry, data=new_data)

    # Register all services
    hass.services.async_register(
        DOMAIN,
        SERVICE_EVALUATE_CONDITIONS,
        handle_evaluate_conditions,
        schema=SERVICE_EVALUATE_CONDITIONS_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_FORCE_UPDATE,
        handle_force_update,
        schema=SERVICE_FORCE_UPDATE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_EXECUTE_DECISIONS,
        handle_execute_decisions,
        schema=SERVICE_EXECUTE_DECISIONS_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CLIMATE_PRIORITY,
        handle_set_climate_priority,
        schema=SERVICE_SET_CLIMATE_PRIORITY_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_TOGGLE_CLIMATE_ENTITY,
        handle_toggle_climate_entity,
        schema=SERVICE_TOGGLE_CLIMATE_ENTITY_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CLIMATE_POWER,
        handle_set_climate_power,
        schema=SERVICE_SET_CLIMATE_POWER_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CLIMATE_WINDOWS,
        handle_set_climate_windows,
        schema=SERVICE_SET_CLIMATE_WINDOWS_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_CLIMATE,
        handle_add_climate,
        schema=SERVICE_ADD_CLIMATE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_CLIMATE,
        handle_remove_climate,
        schema=SERVICE_REMOVE_CLIMATE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_GLOBAL_SETTINGS,
        handle_set_global,
        schema=SERVICE_SET_GLOBAL_SETTINGS_SCHEMA,
    )

    _LOGGER.info("Registered Smart Airco services")


async def _async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister Smart Airco services."""
    services = [
        SERVICE_EVALUATE_CONDITIONS,
        SERVICE_FORCE_UPDATE,
        SERVICE_EXECUTE_DECISIONS,
        SERVICE_SET_CLIMATE_PRIORITY,
        SERVICE_TOGGLE_CLIMATE_ENTITY,
        SERVICE_SET_CLIMATE_POWER,
        SERVICE_SET_CLIMATE_WINDOWS,
        SERVICE_ADD_CLIMATE,
        SERVICE_REMOVE_CLIMATE,
        SERVICE_SET_GLOBAL_SETTINGS,
    ]

    for service in services:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)

    _LOGGER.info("Unregistered Smart Airco services")
