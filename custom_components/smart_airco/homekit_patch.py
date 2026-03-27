"""HomeKit thermostat patching for Smart Airco climates."""

from __future__ import annotations

from importlib import import_module
import logging
from types import ModuleType
from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_ACTION,
    ATTR_PRESET_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    HVACAction,
    HVACMode,
    SERVICE_SET_PRESET_MODE,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, State, callback

from .const import (
    ATTR_SMART_AIRCO_MANAGED,
    ATTR_SMART_AIRCO_PRESET_MODE,
    ATTR_SMART_AIRCO_SOLAR_AUTOMATION_ENABLED,
    DOMAIN,
    PRESET_OFF,
    PRESET_ON,
    PRESET_SOLAR_BASED,
)

_LOGGER = logging.getLogger(__name__)

_RUNTIME_KEY = f"{DOMAIN}_homekit_patch"
_SOLAR_SERVICE_UNIQUE_ID = "smart_airco_solar"
_SOLAR_SERVICE_NAME = "Solar"


def async_acquire_homekit_patch(hass: HomeAssistant) -> bool:
    """Install the Smart Airco HomeKit thermostat patch if possible."""
    runtime = hass.data.setdefault(
        _RUNTIME_KEY,
        {
            "ref_count": 0,
            "patched": False,
            "original_class": None,
            "patched_class": None,
            "accessories_module": None,
            "thermostats_module": None,
        },
    )
    runtime["ref_count"] += 1

    if runtime["patched"]:
        return True

    modules = _async_import_homekit_modules()
    if modules is None:
        return False

    accessories_module, thermostats_module, const_module, util_module = modules
    original_class = accessories_module.TYPES.get("Thermostat")
    if original_class is None:
        _LOGGER.debug(
            "HomeKit thermostat accessory missing; skipping Smart Airco patch"
        )
        return False

    patched_class = _build_smart_airco_homekit_thermostat(
        original_class,
        thermostats_module,
        const_module,
        util_module,
    )
    accessories_module.TYPES["Thermostat"] = patched_class
    if getattr(thermostats_module, "Thermostat", None) is original_class:
        thermostats_module.Thermostat = patched_class

    runtime.update(
        {
            "patched": True,
            "original_class": original_class,
            "patched_class": patched_class,
            "accessories_module": accessories_module,
            "thermostats_module": thermostats_module,
        }
    )
    return True


def async_release_homekit_patch(hass: HomeAssistant) -> None:
    """Release one Smart Airco HomeKit patch reference."""
    runtime = hass.data.get(_RUNTIME_KEY)
    if runtime is None:
        return

    runtime["ref_count"] = max(runtime["ref_count"] - 1, 0)
    if runtime["ref_count"]:
        return

    if runtime["patched"]:
        accessories_module = runtime.get("accessories_module")
        thermostats_module = runtime.get("thermostats_module")
        original_class = runtime.get("original_class")
        patched_class = runtime.get("patched_class")

        if accessories_module is not None and original_class is not None:
            if accessories_module.TYPES.get("Thermostat") is patched_class:
                accessories_module.TYPES["Thermostat"] = original_class

        if thermostats_module is not None and original_class is not None:
            if getattr(thermostats_module, "Thermostat", None) is patched_class:
                thermostats_module.Thermostat = original_class

    hass.data.pop(_RUNTIME_KEY, None)


def _async_import_homekit_modules() -> (
    tuple[ModuleType, ModuleType, ModuleType, ModuleType] | None
):
    try:
        accessories_module = import_module(
            "homeassistant.components.homekit.accessories"
        )
        thermostats_module = import_module(
            "homeassistant.components.homekit.type_thermostats"
        )
        const_module = import_module("homeassistant.components.homekit.const")
        util_module = import_module("homeassistant.components.homekit.util")
    except ModuleNotFoundError as err:
        _LOGGER.debug("HomeKit not available for Smart Airco patch: %s", err)
        return None

    return accessories_module, thermostats_module, const_module, util_module


def _build_smart_airco_homekit_thermostat(
    original_class: type,
    thermostats_module: ModuleType,
    const_module: ModuleType,
    util_module: ModuleType,
) -> type:
    heat_cool_off = thermostats_module.HC_HEAT_COOL_OFF
    char_configured_name = const_module.CHAR_CONFIGURED_NAME
    char_name = const_module.CHAR_NAME
    char_on = const_module.CHAR_ON
    serv_switch = const_module.SERV_SWITCH
    cleanup_name_for_homekit = util_module.cleanup_name_for_homekit

    class SmartAircoHomeKitThermostat(original_class):
        """HomeKit thermostat accessory with a linked solar automation switch."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._smart_airco_enabled = False
            self._char_solar = None
            super().__init__(*args, **kwargs)

            state = self.hass.states.get(self.entity_id)
            if not _is_smart_airco_state(state):
                return

            self._smart_airco_enabled = True
            solar_service = self.add_preload_service(
                serv_switch,
                [char_name, char_configured_name],
                unique_id=_SOLAR_SERVICE_UNIQUE_ID,
            )

            thermostat_service = _find_thermostat_service(self)
            if thermostat_service is not None and hasattr(
                thermostat_service, "add_linked_service"
            ):
                thermostat_service.add_linked_service(solar_service)

            solar_service.configure_char(
                char_name,
                value=cleanup_name_for_homekit(
                    f"{self.display_name} {_SOLAR_SERVICE_NAME}"
                ),
            )
            solar_service.configure_char(
                char_configured_name,
                value=cleanup_name_for_homekit(_SOLAR_SERVICE_NAME),
            )
            self._char_solar = solar_service.configure_char(
                char_on,
                value=_is_solar_automation_enabled(state),
                setter_callback=self._set_solar_automation,
            )
            if _should_present_thermostat_as_off(state):
                self.char_target_heat_cool.set_value(heat_cool_off)
                self.char_current_heat_cool.set_value(heat_cool_off)

        @callback
        def async_update_state(self, new_state: State) -> None:
            super().async_update_state(new_state)

            if _should_present_thermostat_as_off(new_state):
                self.char_target_heat_cool.set_value(heat_cool_off)
                self.char_current_heat_cool.set_value(heat_cool_off)

            if self._char_solar is None:
                return

            self._smart_airco_enabled = _is_smart_airco_state(new_state)
            self._char_solar.set_value(_is_solar_automation_enabled(new_state))

        def _set_solar_automation(self, enabled: int) -> None:
            if not self._smart_airco_enabled:
                return

            state = self.hass.states.get(self.entity_id)
            preset_mode = PRESET_SOLAR_BASED if enabled else _manual_preset_mode(state)
            self.async_call_service(
                CLIMATE_DOMAIN,
                SERVICE_SET_PRESET_MODE,
                {
                    ATTR_ENTITY_ID: self.entity_id,
                    ATTR_PRESET_MODE: preset_mode,
                },
                preset_mode,
            )

    SmartAircoHomeKitThermostat.__name__ = "SmartAircoHomeKitThermostat"
    SmartAircoHomeKitThermostat.__qualname__ = "SmartAircoHomeKitThermostat"

    return SmartAircoHomeKitThermostat


def _find_thermostat_service(accessory: Any) -> Any | None:
    services = getattr(accessory, "services", None)
    if not isinstance(services, list) or len(services) < 2:
        return None
    return services[1]


def _is_smart_airco_state(state: State | None) -> bool:
    return bool(state and state.attributes.get(ATTR_SMART_AIRCO_MANAGED))


def _is_solar_automation_enabled(state: State | None) -> bool:
    if state is None:
        return False

    enabled = state.attributes.get(ATTR_SMART_AIRCO_SOLAR_AUTOMATION_ENABLED)
    if isinstance(enabled, bool):
        return enabled

    return state.attributes.get(ATTR_SMART_AIRCO_PRESET_MODE) == PRESET_SOLAR_BASED


def _should_present_thermostat_as_off(state: State | None) -> bool:
    if state is None or not _is_solar_automation_enabled(state):
        return False

    hvac_action = state.attributes.get(ATTR_HVAC_ACTION)
    return hvac_action in (HVACAction.OFF, HVACAction.IDLE)


def _manual_preset_mode(state: State | None) -> str:
    if state is None:
        return PRESET_OFF

    preset_mode = state.attributes.get(ATTR_SMART_AIRCO_PRESET_MODE)
    if preset_mode == PRESET_OFF:
        return PRESET_OFF

    hvac_action = state.attributes.get(ATTR_HVAC_ACTION)
    if hvac_action in (
        HVACAction.HEATING,
        HVACAction.COOLING,
        HVACAction.DRYING,
        HVACAction.FAN,
    ):
        return PRESET_ON

    return PRESET_OFF
