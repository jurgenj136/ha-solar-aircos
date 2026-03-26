# Changelog

All notable changes to Smart Airco should be documented in this file.

The format is based on Keep a Changelog, and this project aims to use stable
version tags for public HACS releases.

## [1.0.0] - 2026-03-19

### Added

- HACS-ready repository files with root `README.md`, `hacs.json`, `LICENSE`,
  brand assets, and validation workflow.
- Manual override protection that disables automation for an AC when direct user
  control is detected.
- Diagnostics support for config entries.
- Panel support for multi-instance selection, success and error notices, and
  clearer status visibility.
- Anti-chatter protections including startup hysteresis and minimum run and off
  times.
- Critical sensor validation and fail-safe behavior for missing, invalid, or
  stale required inputs.

### Changed

- Public documentation now matches the actual panel-first setup flow.
- Runtime status reporting now reflects actual HVAC state instead of only
  desired decisions.
- Controller enabled or disabled state now persists across reloads and restarts.
- Panel climate rows are now backed by structured data keyed by entity ID rather
  than name-derived keys.

### Fixed

- Multi-instance service and panel targeting so actions can be scoped to a
  specific Smart Airco config entry.
- Diagnostics redaction so configured entity IDs and names are not exposed in
  exported diagnostics.
- Repository hygiene issues caused by generated cache and Finder files.

## [1.0.1] - 2026-03-19

### Changed

- Replaced the experimental iframe sidebar with a native `panel_custom` Smart
  Airco sidebar panel that uses Home Assistant's `hass` object directly.

### Fixed

- Smart Airco sidepanel actions now use native panel integration instead of the
  brittle `/local` + `window.parent.hass` approach.

## [1.0.2] - 2026-03-19

### Changed

- Reworked the Smart Airco panel layout into clearer setup, status, actions,
  add-climate, and managed-climate sections.
- Replaced the cramped climate table editing flow with climate cards and a
  focused single-climate editor.
- Added clearer setup guidance for forecast, production, net export, and update
  interval fields directly in the panel.

### Fixed

- Improved panel usability on both desktop and mobile by removing the tall,
  overlapping inline edit layout.
- Made climate state badges and decision text more readable so users can see
  why a climate is blocked or idle without parsing internal reason strings.
- Preserved frontend draft state more reliably while editing and fixed
  multi-instance switching in the panel.

## [1.0.3] - 2026-03-25

### Added

- Shared controller target temperature support so the Smart Airco Controller can
  apply one setpoint to climates it is allowed to control.
- Controller-wide `heat` and `cool` strategy selection for managed climates.

### Changed

- Reused the existing per-climate `enabled` toggle as the controller's
  selection gate for which climates Smart Airco may control.
- Updated the panel setup and status UI to show controller mode and shared
  target temperature more clearly.

### Fixed

- Coordinator-driven temperature changes no longer falsely trigger manual
  override handling.
- Running-count, power, and status sensors now respect the controller's active
  HVAC mode.
- Added `.gitignore` coverage for generated checklist files.

## [1.0.4] - 2026-03-25

### Changed

- Replaced the single shared Smart Airco controller climate entity model with
  one Smart Airco companion climate entity per managed climate.
- Each managed climate now owns its own Smart Airco HVAC mode and target
  temperature instead of inheriting one shared controller setting.
- The panel now edits per-climate Smart Airco behavior and uses the system
  status sensor as the panel anchor instead of the removed controller climate.

### Added

- One Smart Airco climate entity per managed climate, exposing normal climate
  controls plus Smart Airco participation via `preset_mode`.
- Per-climate Smart Airco mode and target temperature settings.

### Fixed

- Smart Airco runtime execution now applies the correct mode and target
  temperature per managed climate.
- The panel no longer depends on the removed shared controller entity.

## [1.0.5] - 2026-03-26

### Fixed

- Fixed a Smart Airco panel render regression where the frontend still called
  the removed `_getControllers()` helper after the panel-anchor refactor.
- Restored panel loading so the Smart Airco sidebar opens correctly again after
  the per-managed-climate entity release.

## [Unreleased]

- No unreleased changes yet.
