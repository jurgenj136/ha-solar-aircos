# Smart Airco 1.0.7

Patch release focused on making each managed Smart Airco climate behave the way
you described: with its own mode, temperature, and Smart Airco operating mode.

## Highlights

- Each managed Smart Airco climate now uses `preset_mode` values of:
  - `off`
  - `on`
  - `solar_based`
- Each managed Smart Airco climate keeps its own:
  - `heat` / `cool` mode
  - target temperature
- Manual climate changes now translate into Smart Airco behavior instead of only
  disabling automation.

## What changed

- `off` keeps that Smart Airco climate off.
- `on` force-runs that Smart Airco climate and ignores solar surplus plus
  window/door blocking.
- `solar_based` uses the normal Smart Airco priority and surplus logic.
- Manual on/off/mode/temperature changes now sync back into the Smart Airco
  preset/mode/temperature model.

## Setup Notes

- Restart Home Assistant after updating.
- Open each Smart Airco climate entity and verify:
  - `preset_mode`
  - `hvac_mode`
  - target temperature
- If needed, use the Smart Airco panel to review the same per-climate settings.

## Recommended Release Title

`Smart Airco 1.0.7`
