# Smart Airco 1.1.4

Patch release focused on making solar-mode state changes feel immediate and
making the Smart Airco entity reflect denied solar runs more honestly.

## Highlights

- Turning `Solar` on now immediately evaluates whether the airco is allowed to
  run.
- When solar mode is armed but surplus conditions do not allow a run, the Smart
  Airco entity now presents as off.
- Solar automation metadata stays intact, so the unit still shows as armed for
  solar control.

## What changed

- Smart Airco now executes controller decisions immediately after the initial
  refresh during setup and reload, so HomeKit-triggered solar changes take
  effect right away.
- Solar-based Smart Airco climates now report `off` for `hvac_mode` and
  `hvac_action` when the latest controller decision says they should not run.
- Added regressions for immediate decision execution and denied-solar state
  presentation.

## Setup Notes

- Reload the Smart Airco integration after updating.
- If Apple Home still shows stale accessory state, reopen HomeKit or re-pair
  the bridge/accessories.

## Recommended Release Title

`Release Smart Airco 1.1.4`
