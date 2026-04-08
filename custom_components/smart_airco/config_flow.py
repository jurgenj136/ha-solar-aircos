"""Config flow for Smart Airco integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_CLIMATE_ENTITIES,
    CONF_NET_EXPORT_SENSOR,
    CONF_SOLAR_FORECAST_SENSOR,
    CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class SmartAircoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Airco."""

    VERSION = 1

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
        """Redirect to the sidebar panel for climate management."""
        return self.async_abort(reason="managed_via_panel")
