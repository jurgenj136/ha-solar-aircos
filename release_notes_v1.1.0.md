# Smart Airco 1.1.0

Minor release focused on making Smart Airco work as a single, usable HomeKit
accessory per airco instead of splitting automation state away from thermostat
control.

## Highlights

- Smart Airco climates now expose a proper thermostat `off` state to HomeKit.
- HomeKit can now show a linked `Solar` toggle on the same accessory for Smart
  Airco-managed climates.
- The integration installs and removes its HomeKit thermostat patch safely as
  Smart Airco entries are loaded and unloaded.

## What changed

- Smart Airco climate entities now report `HVACMode.OFF` when their preset is
  `off`, and include `off` in the exposed HVAC modes.
- Smart Airco climates now expose an explicit
  `smart_airco_solar_automation_enabled` attribute for HomeKit sync.
- A contained runtime HomeKit thermostat patch adds a linked `Solar` switch only
  for Smart Airco-managed climates.
- The linked `Solar` switch maps to Smart Airco presets:
  - `on` -> `solar_based`
  - `off` -> forced manual `on` when active
  - thermostat `off` -> Smart Airco `off` and Solar `off`
- Added focused tests for climate attributes, HomeKit patch registration,
  linked switch behavior, and setup/unload lifecycle.

## Setup Notes

- Reload the Smart Airco integration after updating.
- Reset or re-pair the HomeKit bridge/accessories if Apple Home does not show
  the new linked `Solar` control immediately.
- Verify each Smart Airco accessory in HomeKit now appears once, with the
  thermostat controls and the `Solar` toggle grouped together.

## Recommended Release Title

`Release Smart Airco 1.1.0`
