# Smart Airco HACS Publish Checklist

## Current Result

Status: almost ready for a first stable HACS publish.

All required in-repo HACS integration items are present.
The remaining work is mostly GitHub-side release and presentation work.

## HACS Integration Requirements

### Required repository structure

- [x] One integration per repository.
- [x] Integration lives under `custom_components/smart_airco/`.
- [x] Root `README.md` exists.
- [x] Root `hacs.json` exists.

### Required integration metadata

- [x] `custom_components/smart_airco/manifest.json` exists.
- [x] `domain` is defined.
- [x] `documentation` is defined.
- [x] `issue_tracker` is defined.
- [x] `codeowners` is defined.
- [x] `name` is defined.
- [x] `version` is defined.

### Brand assets

- [x] `brand/icon.png` exists.

### Runtime/docs alignment

- [x] Root docs describe the real panel-first setup path.
- [x] Docs do not pretend there is a full onboarding wizard.
- [x] Manual override behavior is documented.
- [x] Critical sensor fail-safe behavior is documented.
- [x] Diagnostics support exists.

## Publish Readiness Review

### Product safety

- [x] Manual override disables automation for the affected AC.
- [x] Critical inputs fail safe when invalid, stale, or missing.
- [x] Anti-chatter protections exist.
- [x] Runtime counters now reflect actual HVAC state.

### UI and supportability

- [x] Panel shows critical-input and manual-override state.
- [x] Panel actions are scoped to the selected config entry.
- [x] Multi-instance service registration issues were fixed.
- [x] Diagnostics redact configured entity identifiers and names.

### Repo hygiene

- [x] Generated `__pycache__` artifacts removed.
- [x] Finder `.DS_Store` files removed.
- [x] CI validation workflow exists in `.github/workflows/validate.yml`.

## Verification Completed

- [x] `pytest tests/components/smart_airco -q`
- [x] `python -m compileall custom_components/smart_airco`
- [x] `python -m json.tool hacs.json`
- [x] `python -m json.tool custom_components/smart_airco/manifest.json`

## Remaining Before Public Publish

### Strongly recommended GitHub-side tasks

- [ ] Add GitHub repository description.
- [ ] Add GitHub repository topics.
- [ ] Create the first stable GitHub release.
- [ ] Tag the release with the integration version from `manifest.json`.
- [ ] Add release notes describing panel-first setup, Solcast-first support, and current limitations.

### Optional but useful

- [x] Add `CHANGELOG.md`.
- [ ] Add screenshots or short demo images to the root README.
- [ ] Do one clean install test from a separate Home Assistant instance before announcing it publicly.

## Final Recommendation

If you want a quiet first stable HACS publish, the repository is in good shape.

The main blockers left are not code blockers:

1. create a real GitHub release,
2. make the GitHub repo presentation clean,
3. do one final install-from-scratch smoke test.
