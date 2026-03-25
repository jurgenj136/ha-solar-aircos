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

## [Unreleased]

- No unreleased changes yet.
