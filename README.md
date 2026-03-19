# Smart Airco

Smart Airco is a Home Assistant custom integration for coordinating multiple
air conditioners around available solar surplus.

It is designed as an orchestrator: you keep using your existing `climate`
entities, and Smart Airco decides which managed units are allowed to run based
on forecast data, current production, export surplus, priority, and safety
sensors.

## What it does

- Manages multiple AC units from one integration.
- Prioritizes rooms when there is not enough surplus for every unit.
- Supports optional per-AC power sensors or estimated wattage.
- Supports optional window and door sensors per AC.
- Exposes a controller climate plus supporting sensors and services.
- Uses a panel-first configuration flow for day-to-day setup and editing.
- Includes basic anti-chatter behavior with startup hysteresis and minimum run
  and off times.

## Current product shape

This integration currently uses a minimal config flow and a sidebar management
panel.

That means:

1. Install the integration.
2. Add the integration in Home Assistant.
3. Open the `Smart Airco` sidebar panel.
4. Configure global sensors and managed climate entities there.

The public docs in this repository describe the actual shipped flow. There is
not a full multi-step setup wizard yet.

## Supported inputs

### Officially supported forecast behavior

- Solcast-first.
- The integration currently expects Solcast-style forecast semantics.
- Other forecast sensors may work if they expose compatible data, but they are
  not yet part of the formal support contract.

### Required inputs

- Forecast sensor.
- Current solar production sensor.
- Net export sensor.
- At least one `climate` entity to manage.

Critical inputs must be configured, available, numeric where expected, and
fresh enough to trust. If Smart Airco cannot trust those inputs, it fails safe
and avoids running managed ACs automatically.

### Optional inputs

- Per-AC power sensors.
- Per-AC estimated wattage.
- Window or door sensors for safety blocking.

## Installation

### HACS

1. Open HACS.
2. Go to `Integrations`.
3. Open the 3-dot menu and choose `Custom repositories`.
4. Add `https://github.com/jurgenj136/smart-airco` as an `Integration`.
5. Install `Smart Airco`.
6. Restart Home Assistant.
7. Go to `Settings -> Devices & Services -> Add Integration`.
8. Add `Smart Airco`.
9. Open the `Smart Airco` sidebar item to finish configuration.

Direct install link:

[![Open your Home Assistant instance and open the HACS repository dialog for this repository.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jurgenj136&repository=smart-airco&category=integration)

### Manual installation

1. Copy `custom_components/smart_airco` into your Home Assistant
   `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration from `Settings -> Devices & Services`.
4. Open the `Smart Airco` sidebar panel to complete configuration.

## Setup

### Step 1 - Create the integration entry

Add `Smart Airco` from Home Assistant integrations.

The first config step creates the controller entry. Detailed setup currently
happens in the sidebar panel.

### Step 2 - Configure global sensors in the panel

Configure:

- forecast sensor,
- solar production sensor,
- net export sensor,
- update interval.

### Step 3 - Add managed AC units

For each managed AC, configure:

- target `climate` entity,
- display name,
- priority,
- whether power comes from a live sensor or an estimate,
- estimated wattage if needed,
- optional window or door sensors,
- whether automation is enabled for that AC.

## Manual override behavior

The intended product behavior is that Smart Airco should not fight the user.

If a managed AC is changed directly from Home Assistant, the device, or a
remote, automation for that AC should back off instead of silently taking
control back.

Current behavior:

- the affected AC is marked as manually overridden,
- automation for that AC is disabled,
- the AC is not forced back to the orchestrator decision,
- you can re-enable automation for that AC from the Smart Airco panel.

## Sensors and entities

Expected entities include:

- a Smart Airco controller climate entity,
- surplus and status sensors,
- per-AC monitoring sensors.

Exact names depend on your configured climates.

## Services

Smart Airco exposes services for evaluation, execution, and runtime
configuration. See `custom_components/smart_airco/services.yaml` for the current
service definitions.

The integration also exposes Home Assistant diagnostics for config-entry based
issue reporting.

## Troubleshooting

### If the controller appears but nothing runs

Check:

- the global sensors are configured in the sidebar panel,
- the forecast sensor is compatible with the documented Solcast-first behavior,
- the critical sensors are not stale or unavailable,
- managed climates are enabled,
- window sensors are not blocking operation,
- predicted surplus is actually positive.

### If the sidebar panel shows no controller

Check:

- the integration entry was created successfully,
- Home Assistant was restarted after installation,
- the integration loaded without startup errors.

### If behavior seems surprising

Check:

- per-AC priority,
- power sensor readings or estimated wattage,
- export and production sensor values,
- whether the AC was placed in manual override,
- whether startup or shutdown is being delayed by anti-chatter protection,
- status entities and controller attributes.

## HACS publication notes

This repository is being prepared for a stable-first HACS release.

Current focus areas are:

- honest docs,
- manual override safety,
- calmer anti-chatter behavior,
- stronger diagnostics,
- panel hardening.

## Development notes

- Integration code: `custom_components/smart_airco`
- Current HACS spec: `smart_airco_hacs_spec.md`
- Current execution plan: `smart_airco_hacs_execution_plan.md`

## License

MIT
