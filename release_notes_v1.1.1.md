# Smart Airco 1.1.1

Patch release focused on making the new HomeKit Smart Airco thermostat behave
more honestly when solar automation is armed but the physical airco is not yet
running.

## Highlights

- Solar-armed Smart Airco thermostats now appear off in HomeKit while idle.
- The linked `Solar` control stays on, so Apple Home still shows that solar
  automation is enabled.
- Active cooling/heating still appears normally once the airco actually starts.

## What changed

- The Smart Airco HomeKit thermostat patch now checks the climate
  `hvac_action` before presenting the thermostat as active.
- When Solar mode is enabled and the Smart Airco climate is `idle` or `off`,
  HomeKit now presents the thermostat itself as off.
- When the unit is actually cooling or heating, HomeKit restores the active
  thermostat presentation automatically.
- Added tests covering idle solar presentation and active solar behavior.

## Setup Notes

- Reload the Smart Airco integration after updating.
- If Apple Home still shows the old thermostat state, reload or re-pair the
  HomeKit bridge/accessories so the updated accessory state handling is picked
  up.

## Recommended Release Title

`Release Smart Airco 1.1.1`
