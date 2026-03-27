from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.climate import ATTR_HVAC_ACTION, HVACAction

from custom_components.smart_airco import async_setup_entry, async_unload_entry
from custom_components.smart_airco.const import (
    ATTR_SMART_AIRCO_MANAGED,
    ATTR_SMART_AIRCO_PRESET_MODE,
    ATTR_SMART_AIRCO_SOLAR_AUTOMATION_ENABLED,
    PRESET_OFF,
    PRESET_ON,
    PRESET_SOLAR_BASED,
)
from custom_components.smart_airco.homekit_patch import (
    async_acquire_homekit_patch,
    async_release_homekit_patch,
)
from custom_components.smart_airco.coordinator import SmartAircoCoordinator


class _FakeChar:
    def __init__(self, name: str, value=None, setter_callback=None) -> None:
        self.name = name
        self.value = value
        self.setter_callback = setter_callback

    def set_value(self, value) -> None:
        self.value = value


class _FakeService:
    def __init__(self, service_type: str) -> None:
        self.service_type = service_type
        self.linked_services: list[_FakeService] = []
        self.chars: dict[str, _FakeChar] = {}
        self.unique_id = None

    def configure_char(self, name: str, value=None, setter_callback=None) -> _FakeChar:
        char = _FakeChar(name, value=value, setter_callback=setter_callback)
        self.chars[name] = char
        return char

    def add_linked_service(self, service: _FakeService) -> None:
        self.linked_services.append(service)


class _FakeThermostat:
    def __init__(self, hass, driver, name, entity_id, aid, config) -> None:
        self.hass = hass
        self.driver = driver
        self.display_name = name
        self.entity_id = entity_id
        self.aid = aid
        self.config = config
        self.calls: list[tuple[str, str, dict, str | None]] = []
        self.services = [
            _FakeService("AccessoryInformation"),
            _FakeService("Thermostat"),
        ]
        self.char_target_heat_cool = _FakeChar("TargetHeatingCoolingState", value=2)
        self.char_current_heat_cool = _FakeChar("CurrentHeatingCoolingState", value=2)

    def add_preload_service(self, service_type, chars=None, unique_id=None):
        service = _FakeService(service_type)
        service.unique_id = unique_id
        self.services.append(service)
        return service

    def async_call_service(self, domain, service, service_data, value=None) -> None:
        self.calls.append((domain, service, service_data, value))

    def async_update_state(self, new_state) -> None:
        self.last_state = new_state
        self.char_target_heat_cool.set_value(0 if new_state.state == "off" else 2)
        hvac_action = new_state.attributes.get(ATTR_HVAC_ACTION)
        self.char_current_heat_cool.set_value(
            0 if hvac_action in (HVACAction.OFF, HVACAction.IDLE) else 2
        )


def _mock_homekit_modules(monkeypatch):
    accessories_module = SimpleNamespace(TYPES={"Thermostat": _FakeThermostat})
    thermostats_module = SimpleNamespace(
        Thermostat=_FakeThermostat,
        HC_HEAT_COOL_OFF=0,
    )
    const_module = SimpleNamespace(
        CHAR_CONFIGURED_NAME="ConfiguredName",
        CHAR_NAME="Name",
        CHAR_ON="On",
        SERV_SWITCH="Switch",
    )
    util_module = SimpleNamespace(cleanup_name_for_homekit=lambda value: value)
    modules = {
        "homeassistant.components.homekit.accessories": accessories_module,
        "homeassistant.components.homekit.type_thermostats": thermostats_module,
        "homeassistant.components.homekit.const": const_module,
        "homeassistant.components.homekit.util": util_module,
    }

    monkeypatch.setattr(
        "custom_components.smart_airco.homekit_patch.import_module",
        lambda name: modules[name],
    )
    return accessories_module, thermostats_module, const_module


def test_homekit_patch_adds_linked_solar_switch(hass, monkeypatch) -> None:
    accessories_module, thermostats_module, const_module = _mock_homekit_modules(
        monkeypatch
    )
    entity_id = "climate.smart_airco_living_room"
    hass.states.async_set(
        entity_id,
        "cool",
        {
            ATTR_SMART_AIRCO_MANAGED: True,
            ATTR_SMART_AIRCO_PRESET_MODE: PRESET_SOLAR_BASED,
            ATTR_SMART_AIRCO_SOLAR_AUTOMATION_ENABLED: True,
            ATTR_HVAC_ACTION: HVACAction.IDLE,
        },
    )

    assert async_acquire_homekit_patch(hass) is True
    patched_class = accessories_module.TYPES["Thermostat"]
    assert patched_class is thermostats_module.Thermostat
    assert patched_class is not _FakeThermostat

    accessory = patched_class(hass, object(), "Living Room", entity_id, 1, {})

    assert len(accessory.services) == 3
    solar_service = accessory.services[2]
    assert solar_service.unique_id == "smart_airco_solar"
    assert solar_service in accessory.services[1].linked_services
    assert solar_service.chars[const_module.CHAR_ON].value is True
    assert accessory.char_target_heat_cool.value == 0
    assert accessory.char_current_heat_cool.value == 0

    hass.states.async_set(
        entity_id,
        "off",
        {
            ATTR_SMART_AIRCO_MANAGED: True,
            ATTR_SMART_AIRCO_PRESET_MODE: PRESET_OFF,
            ATTR_SMART_AIRCO_SOLAR_AUTOMATION_ENABLED: False,
            ATTR_HVAC_ACTION: HVACAction.OFF,
        },
    )
    accessory.async_update_state(hass.states.get(entity_id))

    assert solar_service.chars[const_module.CHAR_ON].value is False
    solar_service.chars[const_module.CHAR_ON].setter_callback(0)
    assert accessory.calls[0][2]["preset_mode"] == PRESET_OFF

    hass.states.async_set(
        entity_id,
        "cool",
        {
            ATTR_SMART_AIRCO_MANAGED: True,
            ATTR_SMART_AIRCO_PRESET_MODE: PRESET_SOLAR_BASED,
            ATTR_SMART_AIRCO_SOLAR_AUTOMATION_ENABLED: True,
            ATTR_HVAC_ACTION: HVACAction.COOLING,
        },
    )
    accessory.async_update_state(hass.states.get(entity_id))
    assert accessory.char_target_heat_cool.value == 2
    accessory._char_solar.setter_callback(0)
    accessory._char_solar.setter_callback(1)

    assert accessory.calls[1][2]["preset_mode"] == PRESET_ON
    assert accessory.calls[2][2]["preset_mode"] == PRESET_SOLAR_BASED

    async_release_homekit_patch(hass)
    assert accessories_module.TYPES["Thermostat"] is _FakeThermostat
    assert thermostats_module.Thermostat is _FakeThermostat


def test_homekit_patch_leaves_regular_thermostats_unchanged(hass, monkeypatch) -> None:
    accessories_module, _, _ = _mock_homekit_modules(monkeypatch)
    entity_id = "climate.regular_thermostat"
    hass.states.async_set(entity_id, "cool", {})

    assert async_acquire_homekit_patch(hass) is True
    accessory = accessories_module.TYPES["Thermostat"](
        hass, object(), "Regular", entity_id, 2, {}
    )

    assert len(accessory.services) == 2
    assert accessory._char_solar is None

    async_release_homekit_patch(hass)


def test_homekit_patch_reference_counts(hass, monkeypatch) -> None:
    accessories_module, thermostats_module, _ = _mock_homekit_modules(monkeypatch)

    assert async_acquire_homekit_patch(hass) is True
    patched_class = accessories_module.TYPES["Thermostat"]
    assert async_acquire_homekit_patch(hass) is True

    async_release_homekit_patch(hass)
    assert accessories_module.TYPES["Thermostat"] is patched_class
    assert thermostats_module.Thermostat is patched_class

    async_release_homekit_patch(hass)
    assert accessories_module.TYPES["Thermostat"] is _FakeThermostat
    assert thermostats_module.Thermostat is _FakeThermostat


@pytest.mark.asyncio
async def test_setup_and_unload_manage_homekit_patch_lifecycle(
    hass, mock_config_entry, seed_states, panel_patches
) -> None:
    mock_config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.smart_airco.async_acquire_homekit_patch"
        ) as mock_acquire,
        patch(
            "custom_components.smart_airco.async_release_homekit_patch"
        ) as mock_release,
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
        patch.object(
            SmartAircoCoordinator,
            "async_config_entry_first_refresh",
            AsyncMock(return_value=None),
        ),
    ):
        assert await async_setup_entry(hass, mock_config_entry)
        mock_acquire.assert_called_once_with(hass)

        assert await async_unload_entry(hass, mock_config_entry)
        mock_release.assert_called_once_with(hass)
