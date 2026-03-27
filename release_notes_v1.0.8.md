# Smart Airco 1.0.8

Patch release focused on making Smart Airco match the real capabilities of each
airco while also making the user-facing Smart Airco state clearer.

## Highlights

- Smart Airco now uses each airco's own supported non-off HVAC modes.
- The Smart Airco preset is shown more clearly as `State` in English and `Mode`
  in Dutch.
- Dutch translations are now included for Smart Airco state labels.

## What changed

- Per-airco Smart Airco mode selectors now show modes like `auto`, `heat`,
  `cool`, `dry`, `fan_only`, and `heat_cool` when the underlying climate entity
  supports them.
- `off` remains controlled separately through the Smart Airco state selector.
- Manual non-off mode changes now sync back into Smart Airco correctly.
- Panel status text and runtime status reporting now handle more than just
  heating and cooling.

## Setup Notes

- Reload the integration or restart Home Assistant after updating.
- Open the Smart Airco panel and verify that each managed airco shows the modes
  it actually supports.
- In Dutch, the Smart Airco state selector is now labeled `Mode` with `Aan`,
  `Uit`, and `Zonne-energie`.

## Recommended Release Title

`Smart Airco 1.0.8`
