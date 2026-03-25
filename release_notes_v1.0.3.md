# Smart Airco 1.0.3

Patch release focused on making the Smart Airco Controller more useful as a
real shared controller.

## Highlights

- Added a shared controller target temperature.
- Added controller-wide `heat` / `cool` mode selection.
- Reused the existing per-climate `enabled` toggle as the switch for whether
  Smart Airco may control that climate.
- Updated the panel so controller mode and shared temperature are visible and
  configurable from the setup UI.

## What changed

- When Smart Airco decides that an enabled climate should run, it now applies:
  - the controller HVAC mode (`cool` or `heat`)
  - the shared controller target temperature
- Disabled climates are left alone by Smart Airco.
- Sensor/status reporting now follows the active controller mode rather than
  assuming cooling only.

## Setup Notes

- Restart Home Assistant after updating.
- In the Smart Airco panel, choose:
  - controller mode
  - shared controller target temperature
  - forecast / production / net export sensors
- Use each climate's `enabled` toggle to decide whether Smart Airco may control
  that climate.

## Recommended Release Title

`Smart Airco 1.0.3`
