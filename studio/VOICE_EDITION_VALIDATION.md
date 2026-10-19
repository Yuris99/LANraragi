# Voice edition release validation

The canonical `deploy/nas-release.json` activates app-only release generation 9, pinned to the verified implementation and its runtime manifest. The earlier inactive candidate file is retained as historical preparation and is not consumed by the updater. Publishing the release does not confirm installation on a device; the existing NAS-local task must apply it and report its own health result.

The final implementation passed all 262 unit/HTTP/deployment checks. Generated H.264/AAC MP4, WAV and PNG Chromium checks passed for video-only playback, voice page preparation failure and reload, audio/page synchronization, playback rate, resume after reload, explicit translation grouping/ungrouping, real upload, local cover fingerprint search and desktop/mobile layout. Existing comic reader browser Back/Forward, deep links, page bounds and list context regression passed.

The independent Docker/LANraragi rehearsal passed real generated CBZ+WAV playback, source read-only preservation, unchanged content, existing work IDs, exact streamed download hashes and service restart preservation of groups, cues and resume position. No personal media or actual NAS service was used in these tests. Latest local code matches the published pinned runtime; all 17 runtime files and manifest were verified from the public fixed commit before activation.

External reverse-image search remains a user-operated link/upload flow. No image was submitted to an external search service and successful live search results are not claimed. Browser codec coverage is limited to the generated H.264/AAC and PCM WAV cases; other allowed formats still depend on browser codec support.

Reproduce with:

- `python -B -m unittest discover -s studio/tests -v`
- `python -B studio/tests/editions_smoke.py`
- `python -B studio/tests/navigation_smoke.py`
- `python -B studio/tests/editions_container_smoke.py`

Keep managed-runtime proxy/CA configuration for isolated Docker tests. The existing app updater retains its own SQLite backup, immutable runtime hash checks, scoped code mount and health-based rollback behavior. This release does not change host media mounts, other services or the NAS-local automatic-update enabled flag. Media asset bytes require upload-volume backups in addition to SQLite; see `VOICE_EDITIONS.md`.
