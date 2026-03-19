# Smart Airco 1.0.1

Patch release focused on fixing the Smart Airco sidebar so the panel-first setup
flow works reliably in Home Assistant.

## Highlights

- Replaced the old iframe `/local` sidebar with a native Home Assistant
  `panel_custom` Smart Airco panel.
- Removed the brittle `window.parent.hass` dependency from the sidebar.
- Kept the same panel-first management model while making actions work through
  native Home Assistant panel integration.
- Added panel lifecycle coverage so setup and unload behavior are tested.

## What changed

- Smart Airco now registers its sidebar the same way robust custom panels like
  Alarmo do: as a real custom panel asset served by the integration.
- The frontend panel now talks to Home Assistant directly using the native
  `hass` object.
- Panel registration failures now fail setup cleanly instead of leaving a
  broken panel-first install behind.

## Setup Notes

- Restart Home Assistant after updating so the new `panel_custom` and `http`
  manifest dependencies are loaded.
- Open the `Smart Airco` sidebar after restart and verify your global settings
  and climate actions work normally.

## Recommended Release Title

`Smart Airco 1.0.1`
