# Smart Airco 1.1.3

Patch release focused on restoring normal thermostat behavior in HomeKit after
solar automation has been turned off.

## Highlights

- After turning `Solar` off in HomeKit, you can now turn the airco on again from
  the thermostat controls.
- Setting a non-off HVAC mode now correctly switches Smart Airco into manual-on
  mode when it was previously off.
- HomeKit solar-toggle behavior from earlier fixes remains intact.

## What changed

- Updated the Smart Airco climate entity so `set_hvac_mode(cool/heat/...)`
  automatically switches the Smart Airco preset from `off` to manual `on`.
- This restores standard thermostat behavior after disabling solar automation in
  HomeKit.
- Added a regression test covering the HomeKit flow where Solar is off and the
  user then turns the thermostat back on manually.

## Setup Notes

- Reload the Smart Airco integration after updating.
- If Apple Home still shows stale accessory behavior, reload or re-pair the
  HomeKit bridge/accessories.

## Recommended Release Title

`Release Smart Airco 1.1.3`
