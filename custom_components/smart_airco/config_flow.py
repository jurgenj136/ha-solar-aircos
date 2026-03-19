"""Config flow for Smart Airco integration."""

from __future__ import annotations

import logging
from typing import Any
import uuid

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from .const import (
    CONF_CLIMATE_ENTITIES,
    CONF_CLIMATE_ENTITY_ID,
    CONF_CLIMATE_ENABLED,
    CONF_CLIMATE_NAME,
    CONF_CLIMATE_POWER_SENSOR,
    CONF_CLIMATE_PRIORITY,
    CONF_CLIMATE_USE_ESTIMATED_POWER,
    CONF_CLIMATE_WATTAGE,
    CONF_CLIMATE_WINDOW_SENSORS,
    CONF_NET_EXPORT_SENSOR,
    CONF_SOLAR_FORECAST_SENSOR,
    CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_UPDATE_INTERVAL,
    DEFAULT_AIRCO_WATTAGE,
    DEFAULT_CLIMATE_NAME,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_CLIMATE_ENTITIES,
    MAX_PRIORITY,
    MIN_PRIORITY,
)

_LOGGER = logging.getLogger(__name__)


class SmartAircoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Airco."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._climate_entities: list[dict[str, Any]] = []
        self._current_climate_config: dict[str, Any] = {}
        self._editing_climate_id: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Create the entry immediately; settings are configured in the panel."""
        # Single instance guard
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        data: dict[str, Any] = {
            CONF_CLIMATE_ENTITIES: [],
            CONF_UPDATE_INTERVAL: 300,  # seconds (5 minutes)
        }
        return self.async_create_entry(title="Smart Airco", data=data)

    async def async_step_climate_list(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show list of configured climate entities and options to add/edit/remove."""
        if user_input is not None:
            action = user_input.get("action")

            if action == "add":
                self._current_climate_config = {}
                self._editing_climate_id = None
                return await self.async_step_climate_config()

            elif action == "edit" and user_input.get("climate_id"):
                climate_id = user_input["climate_id"]
                # Find the climate entity to edit
                for climate in self._climate_entities:
                    if climate.get("id") == climate_id:
                        self._current_climate_config = climate.copy()
                        self._editing_climate_id = climate_id
                        return await self.async_step_climate_config()

            elif action == "remove" and user_input.get("climate_id"):
                climate_id = user_input["climate_id"]
                self._climate_entities = [
                    c for c in self._climate_entities if c.get("id") != climate_id
                ]
                # Reorder priorities
                self._reorder_priorities()
                return await self.async_step_climate_list()

            elif action == "finish":
                if not self._climate_entities:
                    return self.async_show_form(
                        step_id="climate_list", errors={"base": "no_climate_entities"}
                    )

                # Save climate entities to data
                self._data[CONF_CLIMATE_ENTITIES] = self._climate_entities
                return self.async_create_entry(
                    title=self._data[CONF_NAME],
                    data=self._data,
                )

        # Build options for existing climate entities
        climate_options = []
        for climate in sorted(
            self._climate_entities, key=lambda x: x.get(CONF_CLIMATE_PRIORITY, 999)
        ):
            entity_name = self.hass.states.get(climate[CONF_CLIMATE_ENTITY_ID])
            entity_name = (
                entity_name.name if entity_name else climate[CONF_CLIMATE_ENTITY_ID]
            )
            climate_options.append(
                {
                    "value": climate["id"],
                    "label": f"Priority {climate[CONF_CLIMATE_PRIORITY]}: {climate[CONF_CLIMATE_NAME]} ({entity_name})",
                }
            )

        # Build schema based on current state
        schema_dict = {
            vol.Required("action"): vol.In(
                {"add": "Add New Climate Entity", "finish": "Finish Configuration"}
            )
        }

        if climate_options:
            schema_dict[vol.Required("action")] = vol.In(
                {
                    "add": "Add New Climate Entity",
                    "edit": "Edit Climate Entity",
                    "remove": "Remove Climate Entity",
                    "finish": "Finish Configuration",
                }
            )
            schema_dict[vol.Optional("climate_id")] = vol.In(
                {opt["value"]: opt["label"] for opt in climate_options}
            )

        data_schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="climate_list",
            data_schema=data_schema,
            description_placeholders={
                "climate_count": str(len(self._climate_entities)),
                "max_climates": str(MAX_CLIMATE_ENTITIES),
            },
        )

    async def async_step_climate_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure a single climate entity."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await self._validate_climate_config(user_input)

            if not errors:
                # Create or update climate config
                climate_config = {
                    "id": self._editing_climate_id or str(uuid.uuid4()),
                    CONF_CLIMATE_ENTITY_ID: user_input[CONF_CLIMATE_ENTITY_ID],
                    CONF_CLIMATE_NAME: user_input[CONF_CLIMATE_NAME],
                    CONF_CLIMATE_PRIORITY: user_input[CONF_CLIMATE_PRIORITY],
                    CONF_CLIMATE_WATTAGE: user_input[CONF_CLIMATE_WATTAGE],
                    CONF_CLIMATE_POWER_SENSOR: user_input.get(
                        CONF_CLIMATE_POWER_SENSOR
                    ),
                    CONF_CLIMATE_USE_ESTIMATED_POWER: user_input.get(
                        CONF_CLIMATE_USE_ESTIMATED_POWER, True
                    ),
                    CONF_CLIMATE_WINDOW_SENSORS: user_input.get(
                        CONF_CLIMATE_WINDOW_SENSORS, []
                    ),
                    CONF_CLIMATE_ENABLED: user_input.get(CONF_CLIMATE_ENABLED, True),
                }

                if self._editing_climate_id:
                    # Update existing
                    for i, climate in enumerate(self._climate_entities):
                        if climate["id"] == self._editing_climate_id:
                            self._climate_entities[i] = climate_config
                            break
                else:
                    # Add new
                    self._climate_entities.append(climate_config)

                # Reorder priorities to avoid conflicts
                self._reorder_priorities()

                return await self.async_step_climate_list()

        # Get current values for editing
        current_values = self._current_climate_config

        # Get next available priority
        used_priorities = {
            c.get(CONF_CLIMATE_PRIORITY, 1) for c in self._climate_entities
        }
        if self._editing_climate_id:
            # When editing, current priority is available
            used_priorities.discard(current_values.get(CONF_CLIMATE_PRIORITY))

        next_priority = 1
        while next_priority in used_priorities and next_priority <= MAX_PRIORITY:
            next_priority += 1

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_CLIMATE_ENTITY_ID,
                    default=current_values.get(CONF_CLIMATE_ENTITY_ID),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="climate")
                ),
                vol.Required(
                    CONF_CLIMATE_NAME,
                    default=current_values.get(CONF_CLIMATE_NAME, DEFAULT_CLIMATE_NAME),
                ): str,
                vol.Required(
                    CONF_CLIMATE_PRIORITY,
                    default=current_values.get(CONF_CLIMATE_PRIORITY, next_priority),
                ): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_PRIORITY, max=MAX_PRIORITY)
                ),
                vol.Optional(
                    CONF_CLIMATE_USE_ESTIMATED_POWER,
                    default=current_values.get(CONF_CLIMATE_USE_ESTIMATED_POWER, True),
                ): bool,
                vol.Required(
                    CONF_CLIMATE_WATTAGE,
                    default=current_values.get(
                        CONF_CLIMATE_WATTAGE, DEFAULT_AIRCO_WATTAGE
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=100, max=5000)),
                vol.Optional(
                    CONF_CLIMATE_POWER_SENSOR,
                    default=current_values.get(CONF_CLIMATE_POWER_SENSOR),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="power",
                    )
                ),
                vol.Optional(
                    CONF_CLIMATE_WINDOW_SENSORS,
                    default=current_values.get(CONF_CLIMATE_WINDOW_SENSORS, []),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="binary_sensor",
                        multiple=True,
                    )
                ),
                vol.Optional(
                    CONF_CLIMATE_ENABLED,
                    default=current_values.get(CONF_CLIMATE_ENABLED, True),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="climate_config",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "editing": "Editing" if self._editing_climate_id else "Adding",
                "climate_name": current_values.get(CONF_CLIMATE_NAME, "New Climate"),
            },
        )

    def _reorder_priorities(self) -> None:
        """Reorder priorities to ensure no gaps or duplicates."""
        # Sort by current priority, then reassign 1, 2, 3, etc.
        sorted_climates = sorted(
            self._climate_entities, key=lambda x: x.get(CONF_CLIMATE_PRIORITY, 999)
        )
        for i, climate in enumerate(sorted_climates):
            climate[CONF_CLIMATE_PRIORITY] = i + 1

    async def _validate_input(self, user_input: dict[str, Any]) -> dict[str, str]:
        """Validate the user input."""
        errors = {}

        # Check if sensors exist and are available
        for sensor_key in [
            CONF_SOLAR_FORECAST_SENSOR,
            CONF_SOLAR_PRODUCTION_SENSOR,
            CONF_NET_EXPORT_SENSOR,
        ]:
            if sensor_id := user_input.get(sensor_key):
                state = self.hass.states.get(sensor_id)
                if not state:
                    errors[sensor_key] = "entity_not_found"

        return errors

    async def _validate_climate_config(
        self, user_input: dict[str, Any]
    ) -> dict[str, str]:
        """Validate climate entity configuration."""
        errors = {}

        # Check if climate entity exists
        if climate_entity := user_input.get(CONF_CLIMATE_ENTITY_ID):
            state = self.hass.states.get(climate_entity)
            if not state:
                errors[CONF_CLIMATE_ENTITY_ID] = "entity_not_found"
            elif not climate_entity.startswith("climate."):
                errors[CONF_CLIMATE_ENTITY_ID] = "not_climate_entity"
            else:
                # Check if already configured (unless editing)
                for climate in self._climate_entities:
                    if (
                        climate[CONF_CLIMATE_ENTITY_ID] == climate_entity
                        and climate["id"] != self._editing_climate_id
                    ):
                        errors[CONF_CLIMATE_ENTITY_ID] = "already_configured"
                        break

        # Check priority conflicts
        priority = user_input.get(CONF_CLIMATE_PRIORITY)
        if priority:
            for climate in self._climate_entities:
                if (
                    climate.get(CONF_CLIMATE_PRIORITY) == priority
                    and climate["id"] != self._editing_climate_id
                ):
                    errors[CONF_CLIMATE_PRIORITY] = "priority_already_used"
                    break

        # Check power sensor exists (if provided and not using estimated power)
        if not user_input.get(CONF_CLIMATE_USE_ESTIMATED_POWER, True):
            power_sensor = user_input.get(CONF_CLIMATE_POWER_SENSOR)
            if power_sensor:
                state = self.hass.states.get(power_sensor)
                if not state:
                    errors[CONF_CLIMATE_POWER_SENSOR] = "entity_not_found"

        # Check window sensors exist
        if window_sensors := user_input.get(CONF_CLIMATE_WINDOW_SENSORS):
            for sensor in window_sensors:
                state = self.hass.states.get(sensor)
                if not state:
                    errors[CONF_CLIMATE_WINDOW_SENSORS] = "window_sensor_not_found"
                    break

        # Check if we're at the limit
        if (
            not self._editing_climate_id
            and len(self._climate_entities) >= MAX_CLIMATE_ENTITIES
        ):
            errors["base"] = "max_climate_entities_reached"

        return errors

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SmartAircoOptionsFlow:
        """Get the options flow for this handler."""
        # Do not pass the entry; Home Assistant injects config_entry on the instance
        return SmartAircoOptionsFlow()


class SmartAircoOptionsFlow(config_entries.OptionsFlow):
    """Handle Smart Airco options."""

    def __init__(self) -> None:
        """Initialize Smart Airco options flow (config_entry injected by HA)."""
        self._current_climate_config: dict[str, Any] = {}
        self._editing_climate_id: str | None = None

    @property
    def config_entry(self) -> config_entries.ConfigEntry:  # type: ignore[override]
        # Provided by the parent OptionsFlow at runtime
        return super().config_entry  # type: ignore[attr-defined]

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the Smart Airco options."""
        return self.async_show_menu(
            step_id="init", menu_options=["global_settings", "manage_climates"]
        )

    async def async_step_global_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure global settings."""
        if user_input is not None:
            # Convert update interval from minutes to seconds
            if CONF_UPDATE_INTERVAL in user_input:
                user_input[CONF_UPDATE_INTERVAL] = user_input[CONF_UPDATE_INTERVAL] * 60

            # Update the config entry data
            new_data = {**self.config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )

            return self.async_create_entry(title="", data={})

        # Get current values, converting seconds back to minutes for display
        current_update_interval = (
            self.config_entry.data.get(CONF_UPDATE_INTERVAL, 300) // 60
        )

        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SOLAR_FORECAST_SENSOR,
                    default=self.config_entry.data.get(CONF_SOLAR_FORECAST_SENSOR),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(
                    CONF_SOLAR_PRODUCTION_SENSOR,
                    default=self.config_entry.data.get(CONF_SOLAR_PRODUCTION_SENSOR),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(
                    CONF_NET_EXPORT_SENSOR,
                    default=self.config_entry.data.get(CONF_NET_EXPORT_SENSOR),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=current_update_interval,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
            }
        )

        return self.async_show_form(
            step_id="global_settings",
            data_schema=data_schema,
        )

    async def async_step_manage_climates(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Explain how climate entities are managed."""
        return self.async_show_form(
            step_id="manage_climates",
            data_schema=vol.Schema({}),
            description_placeholders={
                "info": "Use the Smart Airco sidebar panel to add, edit, and remove climate entities. The panel now supports full runtime management."
            },
        )
