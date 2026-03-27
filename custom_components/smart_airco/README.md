# Smart Airco integration notes

The primary public documentation for this project now lives in the repository
root `README.md`.

Use that document for:

- installation,
- HACS setup,
- panel-first configuration guidance,
- supported sensor expectations,
- troubleshooting,
- current release posture.

## Integration package contents

This directory contains the Home Assistant integration code shipped into
`custom_components/smart_airco`.

Key files:

- `manifest.json`
- `config_flow.py`
- `coordinator.py`
- `climate.py`
- `sensor.py`
- `services.yaml`
- `translations/en.json`
- `panel.py`
- `frontend/smart-airco-panel.js`

## Runtime model

Smart Airco is a multi-AC orchestrator.

- A minimal config flow creates the integration entry.
- A native Home Assistant custom sidebar panel is the main management surface.
- Each managed climate gets its own Smart Airco climate entity with:
  - `hvac_mode` (the supported non-off modes of that airco, such as `auto`, `heat`, `cool`, `dry`, or `fan_only`)
  - `target_temperature`
  - `preset_mode` (`off` / `on` / `solar_based`)
- Runtime services support evaluation, execution, and configuration changes.

## Support

- Issues: `https://github.com/jurgenj136/smart-airco/issues`
- Public docs: `https://github.com/jurgenj136/smart-airco#readme`
