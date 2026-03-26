# Smart Airco 1.0.4

Patch release focused on moving Smart Airco to a cleaner per-managed-climate
control model.

## Highlights

- Smart Airco now exposes one companion climate entity per managed climate.
- Each managed climate has its own Smart Airco `active` / `inactive` state via
  `preset_mode`.
- Each managed climate can choose its own Smart Airco `heat` / `cool` mode.
- Each managed climate can choose its own Smart Airco target temperature.

## What changed

- Removed reliance on one shared Smart Airco controller climate entity.
- Smart Airco runtime execution now uses per-climate mode and target
  temperature settings.
- The panel now edits the per-climate Smart Airco model directly.

## Setup Notes

- Restart Home Assistant after updating.
- Existing managed climates should migrate automatically to the new per-climate
  model.
- Open the Smart Airco panel and verify each managed climate has the expected:
  - active state
  - heat/cool mode
  - target temperature

## Recommended Release Title

`Smart Airco 1.0.4`
