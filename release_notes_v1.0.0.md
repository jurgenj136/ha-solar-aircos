# Smart Airco 1.0.0

First stable HACS-ready release of Smart Airco.

## Highlights

- Panel-first setup flow documented and aligned with the shipped integration.
- Solar-aware multi-AC orchestration with Solcast-first forecast assumptions.
- Manual override protection: direct user control disables automation for that
  AC until explicitly re-enabled.
- Fail-safe critical-input validation for missing, stale, or invalid required
  sensors.
- Calmer behavior with startup hysteresis and minimum run and off times.
- Diagnostics support and improved panel feedback.

## Setup Notes

- Install through HACS or copy `custom_components/smart_airco` manually.
- Add the integration from `Settings -> Devices & Services`.
- Open the `Smart Airco` sidebar panel to finish configuration.
- Configure the forecast, production, and net export sensors in the panel.

## Current Support Scope

- Solcast-first forecast behavior.
- Existing Home Assistant `climate` entities are orchestrated; Smart Airco does
  not provide vendor-specific AC integrations.
- Panel-first management remains the primary setup and editing surface.

## Known Limitations

- Broader forecast-provider normalization is not part of this release yet.
- GitHub-side polish such as screenshots may still improve after the initial
  stable release.

## Recommended Release Title

`Smart Airco 1.0.0`
