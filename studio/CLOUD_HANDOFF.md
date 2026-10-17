# Cloud continuation checkpoint

Cloud continuation after `79f7dd70`: read `CLOUD_VALIDATION.md` first for fresh cloud evidence, changes and remaining blockers. The original checkpoint record below is historical.

## Latest continuation: 2026-10-17 (Korea time)

**Latest explicit authorization:** after user-provided inspect/top identified NAS Stash `PTestManager` as actual UID0/GID0 and Studio config1026:100, the user approved trying root execution. The supported next action is now the separate root-source-reader one-folder pilot, not mandatory account creation. Read `deploy/ROOT_FOLDER_PILOT.ko.md`. It preserves existing web/LANraragi identity/services, uses source RO/network-none, no inherited NAS groups, and switches effective IDs so only source access uses root while SQLite/CBZ writes retain the existing app UID. Legacy group-inheriting helpers stay disabled. User-confirmed NAS root-pilot now reports errors0/imported1/pages88/fixed_selection=true/root_source_reader=true/output1026:100 and a pre-registration SQLite backup. NAS indexing/browser reader/download/retry validation remains pending. A fresh cloud runtime restored this fork independently under work; no NMLO/Stash edit or NAS credential/media transfer.122 tests and synthetic root-reader/legacy-app integration passed; details in CLOUD_VALIDATION.md.

**Superseding user correction:** personal NAS account privileges must not be used. The running pilot was configured with personal UID1026/GID100; diagnostics also inherited administrator group101. This is identity reuse even without a password. Do not execute any earlier pinned personal-account helper/command. Latest versions of both helpers now refuse every mode; optional folder Compose no longer adds supplementary groups. New installation requires read-only verification of the named non-administrator `library-studio` account, refusing personal/root/admin/docker identities. Read `deploy/SERVICE_ACCOUNT.ko.md` for concrete rights and migration sequence. Dedicated account UID/GID, source ACL and existing-service migration remain unconfirmed/unperformed. The historical continuation below is not current execution guidance. No NAS service/account/ACL change was made by this correction.

- NAS pilot: user-confirmed LANraragi/Studio healthy after CFS quota recovery, Windows SSH tunnel and administrator login. Exact NAS media-flow success and backup restore are still pending; cloud has no NAS management credential/TCP grant.
- The selected NAS content is unpacked image folders. A separate, network-disabled, UID/GID 1026:100 one-shot folder worker preserves the read-only source and creates CBZ reading copies in the dedicated upload volume. Default plan is metadata-only; first import is bounded to one book. `manga` and `images` are configurable relative collections. It has persistent receipts/cursors, natural ordering, source-change and space guards, folder tags, no original deletion and no automatic whole-library watch. Read `deploy/NAS_FOLDERS.ko.md`. The user confirmed the absolute source path in chat (keep it NAS-local, do not publish private roots). Initial group100-only diagnostics failed; passing the ordinary account’s existing groups100/101 restored read access without NAS ACL/account/ownership changes. The latest read-only recursive plan reports417 directories,16896 pages,326 ready folders,0 errors,0 imports and no truncation. The first root-source pilot subsequently registered one88-page archive (errors0) with a prior SQLite backup; indexing/browser/download remain pending.
- The optional worker can reuse the exact NAS-loaded Studio image with the reviewed module mounted read-only. No large image transfer or existing service recreation is needed for that path. The new UI's number/URL entry is separate source work and is not deployed to the existing NAS web image.
- The number resolver never guesses E-Hentai gallery identifiers, never borrows another site's matching number, never silently merges works and does not claim that URL derivation proves a live download. E-Hentai/Hitomi live downloads and automated comments remain unverified/unsupported as documented.
- Latest NAS result: the group retry succeeded with UID1026/GID100/groups[100,101], errors0 and all three selected directories opened/read-only/mode0777. Existing supplementary group101 restored read access; no host ACL/group/ownership change was made. manga has two child directories/no direct images; images has no detected supported direct images/child directories. The optional folder Compose now requires verified `STUDIO_FOLDER_READ_GROUP=101`. The recursive plan subsequently passed. A guarded NAS-local one-folder pilot is now prepared: fixed selection across retries, exclusive lock, verified SQLite snapshot before migration/publication, source RO, generated CBZ limit128MiB and verification of existing dedicated project/container/mount/volume identities. It does not restart services or read deployment secrets. The exact installed NAS image passed a fresh synthetic PNG/JPEG/WebP reader/download/duplicate-preservation integration. Run `deploy/import-one-folder.sh preview|run` as the ordinary NAS account; outer sudo execution is refused. The helper’s module is pinned by commit/SHA256. The first NAS root-pilot import is now user-confirmed (one88-page archive); reader/download remain pending.
- Current source validation: 118 unit/HTTP/config tests, JS syntax and synthetic browser tests; detailed runtime evidence/limits in CLOUD_VALIDATION.md. Personal media, NAS DBs/passwords/cookies/keys and root paths are not transferred into the checkout.

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
