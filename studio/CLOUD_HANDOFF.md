# Cloud continuation checkpoint

Cloud continuation after `79f7dd70`: read `CLOUD_VALIDATION.md` first for fresh cloud evidence, changes and remaining blockers. The original checkpoint record below is historical.

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
