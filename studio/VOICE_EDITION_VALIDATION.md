# Voice edition release candidate

The implementation is committed on the feature branch. `deploy/voice-editions-release.candidate.json` is an inactive candidate and is not the file consumed by the existing NAS updater. The existing `nas-release.json` remains unchanged. Neither publication nor a successful synthetic test confirms installation on a device.

The implementation passed 261 full unit/HTTP/deployment checks, generated H.264/AAC and WAV/PNG Chromium playback/search/upload checks, existing reader navigation regression, and an independent Docker/LANraragi CBZ+WAV restart/resume rehearsal. All media were generated fixtures. No external image search submission or actual NAS deployment was performed.

Subsequent small improvements add the voice page reload control, update last-opened time on media progress, force refreshed cover indexing and check oversized cover responses. The latest 13 catalog/storage tests, runtime manifest coverage and JavaScript syntax check pass, including the new cover replacement case. The revised whole-suite and browser reruns did not execute because execution approval review was unavailable. Do not describe the final 262-test suite as passed.

Before promoting this candidate to the actual app release, rerun:

- `python -B -m unittest discover -s studio/tests -v`
- `python -B studio/tests/editions_smoke.py` (includes initial page preparation failure and explicit reload)
- `python -B studio/tests/navigation_smoke.py`

The separate Docker rehearsal is `python -B studio/tests/editions_container_smoke.py`. Preserve the managed runtime's proxy/CA configuration; tests must stay isolated from personal services and use only generated data. Promotion requires verifying the pinned public runtime manifest/files and retaining the existing updater's backup, scope and health checks. Do not change media mounts or enable external uploads through the app-only update channel.
