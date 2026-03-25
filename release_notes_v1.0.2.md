# Smart Airco 1.0.2

Patch release focused on making the Smart Airco sidepanel genuinely usable for
day-to-day setup and editing.

## Highlights

- Reworked the panel into clearer sections for setup, system status, actions,
  adding climates, and managed climates.
- Replaced the old cramped editing table with climate cards and a focused editor
  for one climate at a time.
- Added better setup guidance for forecast, production, net export, and update
  interval fields.
- Improved decision text and visual state badges so it is easier to understand
  why a climate is running, blocked, or waiting.

## What changed

- Managed climates are now easier to scan at a glance.
- Per-climate settings are edited in a cleaner dedicated section instead of
  exploding rows inside the list.
- The panel preserves local draft state more reliably while you edit.
- Multi-instance controller selection behaves more predictably.

## Setup Notes

- Refresh the Home Assistant frontend after updating if the old panel layout is
  still cached in your browser.
- Review your global sensors in the Setup section and verify the climate cards
  show the expected priorities, power settings, and window sensors.

## Recommended Release Title

`Smart Airco 1.0.2`
