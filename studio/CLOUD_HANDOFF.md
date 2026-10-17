# Cloud continuation checkpoint

Cloud continuation after `79f7dd70`: read `CLOUD_VALIDATION.md` first for fresh cloud evidence, changes and remaining blockers. The original checkpoint record below is historical.

## Latest continuation: 2026-10-18 (Korea time)

- User-confirmed NAS: Studio/LANraragi healthy, SSH tunnel and login; root-pilot registered exactly one88-page archive with errors0 and a prior SQLite backup, output UID1026/GID100. The older read-only plan counted417 directories/16896 pages/326 candidate folders without truncation. Private roots/titles/media/DB/secrets stay NAS-local. Detailed NAS reader/download/retry evidence remains unconfirmed; “looks working” is not proof of each flow.
- Latest request (2026-10-18): give detail and each reader page their own URL/history. Implemented /#/works/<id> and /#/works/<id>/read/<page>, browser Back/Forward6↔7, exact reload/deep links, page jump input, saved list query/filter/sort/page/scroll, bounded page canonicalization and stale-response cancellation. Reader page turns reuse the extracted file list; progress writes are serialized. Reader close/Escape navigates to detail; detail close/Escape to remembered library. These controls add their destination to history, while browser Back follows actual visits. Seven-page browser fixture passed; actual LRR/update rehearsal is recorded in CLOUD_VALIDATION.md. NAS application is separate.
- Latest UI correction: replace square mosaic with soft thumbnail-only blur and show the full cover at its original ratio. Implemented CSS blur10px, object-fit contain/center, no canvas/zoom/crop, original detail/reader and saved on/off with migration from thumbnailMosaic. Original files are unchanged. Browser validation uses portrait/wide/tall synthetic images and actual pixels at all four edges in grid/list, desktop/mobile and three card sizes.
- The source-only updater in deploy/update-studio-ui.sh now supports both the original installed image and an earlier reviewed /app overlay. It verifies current project/image/user/volumes/loopback/RO-code binding, pins hashes, snapshots SQLite and recreates only Studio. A prior overlay is saved; rollback restores the immediate previous version, including older overlays without history metadata. Read deploy/NAS_UI_UPDATE.ko.md. Actual NAS application of this correction is pending user execution.
- deploy/manage-folders-root.sh adds metadata-only root-plan (source/estimated copy bytes) and root-batch (max10 new folders,512MiB/archive). It backs up SQLite first, shares the fixed pilot’s exclusive lock, retains receipts/cursor and skips prior copies. Read deploy/ROOT_FOLDER_PILOT.ko.md. No automatic whole-library loop/watch is enabled. A plan’s total estimate includes previously registered candidates; scanning is bounded and may need smaller selected collections for larger trees.
- Latest root authorization: user identified existing Stash PTestManager as actual UID0/GID0 and approved root source reading. The disposable worker elevates effective IDs only for source access; outputs use existing app UID1026/GID100 with groups cleared. Source remains RO/network-none. No mandatory new NAS account for this path. Main app identities are not migrated. Old group-inheriting helpers remain disabled. No NMLO/Stash/ACL/source changes.
- 130 unit/HTTP/deployment tests passed, JS/shell checks passed, synthetic browser blur/cover-ratio/resolver tests passed. Real Docker source-update/rollback rehearsal preserves download hash and never restarts LRR. Root-reader integration uses actual LRR0.9.81 and a legacy Studio-source image with generated PNG/JPEG/WebP. Full-fork image build and actual website downloads/comments remain blocked/unverified as recorded in CLOUD_VALIDATION.md.
- Cloud runtime/network policy current and enforced; VPN configured but no NAS management credential/TCP grant. Do not run Tailscale, inspect auth keys, bypass proxy policy or copy personal data. The current checkout remains independent under work; NMLO sources are untouched.

The user requested moving ongoing development to a managed cloud environment with Tailscale, following their existing NMLO cloud workflow. Continue this fork in its own checkout; do not edit NMLO.

## Product goal

A web-first, fast NAS library with Stash-like organization but its own visual design. Store multiple source identities and full links for each work; preserve source tags and comments; expose configurable thumbnail views, sorting and reading history; route downloads to NAS or PC. Target NAS: Synology DS718+. Keep original files and games intact.

## Repository and branch

- Fork: `https://github.com/Yuris99/LANraragi`
- Upstream: `https://github.com/Difegue/LANraragi`
- Working branch: `feature/library-studio`
- Upstream base: `adfe9e75cbb8dd4db0fef2c2e35698d557c5a59b`
- Application additions: `studio/`; single upstream change so far: `LRR_API_KEY` environment override in `Model/Config.pm`.

Read `studio/README.md`, then the actual code before continuing. This is intentionally a WIP checkpoint. Do not describe the product as finished.

## Verified before transfer

- `python -B -X utf8 -m unittest discover -s studio/tests -q`: 18 passed.
- `node --check studio/web/app.js`: passed.
- Both Docker images built successfully.
- New isolated LANraragi container healthy; actual `/api/info` returned 0.9.81.
- Studio container started at a loopback-only local port with generated credentials.
- No user media, personal filenames, DB, NAS credentials, VPN keys, or runtime `.env` are in this checkpoint.

## What is NOT verified

- No browser visual or interaction verification was completed before handoff.
- No real-library import, real-site tag/comment fetch, real-site engine integration or NAS deployment.
- No synthetic CBZ reading / thumbnail / browser download smoke test yet.
- No speed claims have been measured.
- No NAS filesystem was mounted or modified. A previous NMLO task's Stash version query does not prove this app is deployed.

## Next work, in order

1. Read the provided cloud runtime and VPN skill. Check current environment/network policy using non-secret status fields. Use managed HTTP/HTTPS proxy and VPN only. Do not read VPN auth keys, run Tailscale manually or bypass network restrictions.
2. Clone this fork/branch into a separate directory in the cloud workspace; verify the checkpoint commit and branch. Leave NMLO untouched.
3. Re-run 18 tests and JS syntax check; build/start an isolated stack with synthetic media only.
4. Tighten worker-token authorization to worker endpoints, scrub leases from all non-worker responses, fix retry output directories without overwriting earlier files, make expired upstream jobs/restarts inspectable and safe, validate worker outputs and heartbeat failures. Add meaningful regression tests.
5. Add an explicit validated Minion worker-concurrency setting (start at 1–2 for DS718+); current upstream used 24 parallel jobs on the development PC despite container CPU limits.
6. Verify actual LANraragi sync, thumbnails, reading, progress tracking and PC archive download using synthetic CBZs. Check desktop and mobile UI in a browser and fix any errors.
7. Inspect actual installed plugin capabilities before promising site support. Upstream first-start registry refresh logged an invalid registry entry (`download-chaika` key/inner-namespace mismatch); built-in plugin files exist, but registry refresh success must not be assumed.
8. Implement and test source-specific comment collectors with provenance, limits, update behavior and explicit unsupported states; currently only JSON import exists.
9. Add measured performance checks and backup/restore documentation. Real-site tests require the normal permitted access path; respect login, rate limits and blocks. The official desktop Hitomi-Downloader GitHub page returned HTTP 451 during research; no bypass or alternate binary was used.
10. Prepare DS718+ deployment and download-worker configuration for review. Confirm actual NAS paths and UID/GID before any deployment or media migration. Do not expose services publicly, delete originals, reconfigure existing Stash/NMLO, or upload personal media to GitHub/cloud.

## Handoff boundary

The currently verified state is source implementation + tests + local image build + upstream health. Cloud task startup/VPN verification and any continued development must be reported from fresh evidence in the destination task. Continue autonomous code fixes and synthetic testing there; report any genuinely required missing access clearly.
