# Smart Airco 1.1.2

Patch release focused on fixing the HomeKit `Solar` switch behavior so it no
longer wakes up an idle airco when you disable solar automation.

## Highlights

- Turning `Solar` off in HomeKit no longer starts an idle airco.
- If the airco is already actively running, turning `Solar` off keeps it
  running manually as expected.
- The HomeKit switch behavior now matches the physical state much better.

## What changed

- Updated the Smart Airco HomeKit patch so `Solar off` maps to:
  - `off` when the airco is idle or already off
  - manual `on` only when the airco is actively heating, cooling, drying, or
    running fan-only
- Added tests covering both idle and actively running solar-mode behavior.

## Setup Notes

- Reload the Smart Airco integration after updating.
- If Apple Home still shows stale accessory behavior, reload or re-pair the
  HomeKit bridge/accessories.

## Recommended Release Title

`Release Smart Airco 1.1.2`
