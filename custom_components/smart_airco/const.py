"""Constants for the Smart Airco integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.climate.const import HVACMode

DOMAIN = "smart_airco"

# Panel constants
PANEL_TITLE = "Smart Airco"
PANEL_ICON = "mdi:air-conditioner"
PANEL_NAME = "smart-airco-panel"
PANEL_FRONTEND_URL_PATH = "smart-airco"
PANEL_FOLDER = "frontend"
PANEL_FILENAME = "smart-airco-panel.js"
PANEL_URL = f"/api/panel_custom/{DOMAIN}"

# Configuration keys - Global settings
CONF_SOLAR_FORECAST_SENSOR = "solar_forecast_sensor"
CONF_SOLAR_PRODUCTION_SENSOR = "solar_production_sensor"
CONF_NET_EXPORT_SENSOR = "net_export_sensor"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_CONTROLLER_ENABLED = "controller_enabled"
CONF_CONTROLLER_HVAC_MODE = "controller_hvac_mode"
CONF_CONTROLLER_TARGET_TEMPERATURE = "controller_target_temperature"

# Configuration keys - Climate entities
CONF_CLIMATE_ENTITIES = "climate_entities"
CONF_CLIMATE_ENTITY_ID = "entity_id"
CONF_CLIMATE_NAME = "name"
CONF_CLIMATE_PRIORITY = "priority"
CONF_CLIMATE_WATTAGE = "wattage"
CONF_CLIMATE_POWER_SENSOR = "power_sensor"
CONF_CLIMATE_USE_ESTIMATED_POWER = "use_estimated_power"
CONF_CLIMATE_WINDOW_SENSORS = "window_sensors"
CONF_CLIMATE_ENABLED = "enabled"
CONF_CLIMATE_MANUAL_OVERRIDE = "manual_override"
CONF_CLIMATE_HVAC_MODE = "hvac_mode"
CONF_CLIMATE_TARGET_TEMPERATURE = "target_temperature"

# Default values
DEFAULT_AIRCO_WATTAGE = 1000
DEFAULT_UPDATE_INTERVAL = timedelta(minutes=5)
DEFAULT_CLIMATE_NAME = "Air Conditioning"
DEFAULT_CONTROLLER_HVAC_MODE = HVACMode.COOL
DEFAULT_CONTROLLER_TARGET_TEMPERATURE = None
DEFAULT_CLIMATE_HVAC_MODE = HVACMode.COOL
DEFAULT_CLIMATE_TARGET_TEMPERATURE = None

PRESET_ACTIVE = "active"
PRESET_INACTIVE = "inactive"

# Service names
SERVICE_EVALUATE_CONDITIONS = "evaluate_conditions"
SERVICE_FORCE_UPDATE = "force_update"
SERVICE_EXECUTE_DECISIONS = "execute_decisions"
SERVICE_SET_CLIMATE_PRIORITY = "set_climate_priority"
SERVICE_TOGGLE_CLIMATE_ENTITY = "toggle_climate_entity"
SERVICE_SET_CLIMATE_POWER = "set_climate_power"
SERVICE_SET_CLIMATE_WINDOWS = "set_climate_windows"
SERVICE_ADD_CLIMATE = "add_climate"
SERVICE_REMOVE_CLIMATE = "remove_climate"
SERVICE_SET_GLOBAL_SETTINGS = "set_global_settings"

# Entity names
ENTITY_SMART_CONTROLLER = "smart_controller"
ENTITY_ENERGY_SURPLUS = "energy_surplus"
ENTITY_PREDICTED_SURPLUS = "predicted_surplus"
ENTITY_AUTOMATION_STATUS = "automation_status"

# Limits
MAX_CLIMATE_ENTITIES = 10
MIN_PRIORITY = 1
MAX_PRIORITY = 10
