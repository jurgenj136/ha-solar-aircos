# Smart Airco 1.0.5

Patch release focused on fixing the Smart Airco panel after the `1.0.4`
per-managed-climate refactor.

## Highlights

- Fixed the sidebar panel crash caused by a stale `_getControllers()` frontend
  call.
- Restored normal Smart Airco panel loading after upgrade.

## What changed

- The frontend now uses the correct panel-anchor lookup path consistently.
- No behavior changes were made to the per-managed-climate entity model beyond
  restoring panel usability.

## Recommended Release Title

`Smart Airco 1.0.5`
