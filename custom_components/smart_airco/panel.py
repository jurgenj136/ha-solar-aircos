"""Panel registration for Smart Airco."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    PANEL_FILENAME,
    PANEL_FOLDER,
    PANEL_FRONTEND_URL_PATH,
    PANEL_ICON,
    PANEL_NAME,
    PANEL_TITLE,
    PANEL_URL,
)

_LOGGER = logging.getLogger(__name__)
_PANEL_DATA_KEY = f"{DOMAIN}_panel"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the Smart Airco custom panel."""
    panel_file = Path(__file__).parent / PANEL_FOLDER / PANEL_FILENAME
    if not panel_file.exists():
        raise FileNotFoundError(f"Smart Airco panel asset missing: {panel_file}")

    cache_bust = int(panel_file.stat().st_mtime)
    panel_data = hass.data.setdefault(_PANEL_DATA_KEY, {})

    if not panel_data.get("static_path_registered"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(PANEL_URL, str(panel_file), cache_headers=False)]
        )
        panel_data["static_path_registered"] = True

    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_NAME,
        frontend_url_path=PANEL_FRONTEND_URL_PATH,
        module_url=f"{PANEL_URL}?m={cache_bust}",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        require_admin=True,
        config={},
        config_panel_domain=DOMAIN,
    )

    _LOGGER.debug("Registered Smart Airco custom panel")


async def async_unregister_panel(hass: HomeAssistant) -> None:
    """Unregister the Smart Airco custom panel."""
    frontend.async_remove_panel(hass, PANEL_FRONTEND_URL_PATH)
    _LOGGER.debug("Unregistered Smart Airco custom panel")
