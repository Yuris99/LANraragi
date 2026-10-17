# Library Studio (work in progress)

> **Latest user-approved path (2026-10-17):** use the disposable root source reader described in [ROOT_FOLDER_PILOT.ko.md](deploy/ROOT_FOLDER_PILOT.ko.md). The user confirmed the existing NAS Stash runs as UID0/GID0 and approved this root-reading trial. Source stays RO; data/CBZ writes use the verified existing app UID. No new NAS account or existing-service restart is required for this one-folder test. Earlier mandatory service-account migration guidance is superseded for this scope. The user confirmed one88-page NAS root-pilot import with errors0 and a pre-registration DB backup; NAS indexing/reader/download are still pending.

**Account history:** the old helpers that inherited the operator’s groups are disabled. The later user-approved root reader supersedes mandatory account creation for source reading. Existing app outputs still use the installed UID1026/GID100; this does not migrate the main services to a dedicated account. [SERVICE_ACCOUNT.ko.md](deploy/SERVICE_ACCOUNT.ko.md) remains an optional future migration plan.

For the current deployment candidate, site-support matrix and operational procedures, read [NAS_READINESS.md](NAS_READINESS.md). The NAS pilot's healthy services, SSH tunnel and Studio login are user-confirmed. Actual NAS media flows, site downloads/comments and recovery rehearsal remain unverified.

A personal web library built on this LANraragi fork, with a separate small Python/SQLite service for cross-site identities, source-specific metadata and download routing. This is an initial implementation, not a finished release.

## Image display defaults

New browser visits apply a soft CSS **blur to library thumbnails only**. Pixelated canvases have been removed. Opening a work immediately shows its original cover and reader pages. **설정 → 목록 썸네일 블러** and the header toggle save the choice in that browser; refresh preserves it. The previous thumbnail-mosaic on/off preference is migrated. Legacy `/unsen` bookmarks start with thumbnails unblurred without replacing the saved preference unless a setting changes. Both routes require the same authentication.

Covers use `object-fit: contain` in both grid/list and detail views: the complete image keeps its original ratio and is centered, with background space when the frame ratio differs. There is no image zoom, stretch or crop to fill the frame. Original media and downloads retain their bytes. Blur is active from the initial HTML class; browsers without filter support keep affected thumbnails hidden. No canvas is required.

`python -B studio/tests/mosaic_smoke.py` checks default blur, saved settings/migration, original detail/reader, all three card sizes and desktop/mobile grid/list layouts. Generated portrait/wide/tall images have four colored edges; actual screenshot pixels verify all edges remain visible when blur is off. Pillow and Playwright are test-only dependencies.

## User tags

The detail screen's **내 태그 → 추가·삭제** edits a separate indexed SQLite relation. These tags survive LANraragi synchronization and never rewrite LANraragi or per-source original tags/comments. Click × to remove a user tag or its label for an exact user-tag filter. General search includes user tags; typing a new search clears that exact filter.

Select cards (or **현재 페이지 선택**) and use **선택 작품 태그 편집** to add/remove tags atomically for up to 120 works. Selection resets on page/filter/reload. **태그 관리** lists the top 100 matching user tags with work counts; inputs suggest existing user tags. Name changes/merges require an in-app review before applying globally. Names are case-sensitive, whitespace trimmed, maximum 120 characters, up to 100 user tags per work. Original source-only tags cannot be deleted or renamed by these controls. User tags are included in metadata export and SQLite backup/restore.

## Two import paths

1. **Browser**: choose files, choose a folder, or drop files onto the upload area. Folder selection uploads contained CBZ/ZIP/PDF files individually; loose image folders are not packaged and folder structure is not preserved. Dragging directories is not supported; use the folder picker. Up to 20 archives per batch, sequentially streamed. Optional common user tags are saved with each upload and applied when indexed. Pending upload tags are consumed once so later manual deletions survive resync.
2. **Dedicated inbox**: optionally combine either base Compose file with `-f studio/compose.import.yaml` and set `STUDIO_INBOX` to a verified **new dedicated existing directory**. It is mounted **read-only** at `/inbox`. Studio checks every ten seconds, waits at least 30 seconds since file modification, validates and copies supported archives into the upload volume, then links/indexes them automatically. A file still changing during copying is not published. Source files are never moved/deleted, links and hidden paths are skipped, successful size/mtime receipts survive restart, full-file hashes prevent duplicate storage. Keep sufficient space for source plus copied archive. Unchanged invalid files are skipped until modified or service restart; transient storage/busy errors retry. Scanning advances in batches of 1,000 directory entries. Copy to a `.part` name and rename to the final archive name only when complete. Folder names do not create library collections or tags.

For plain Python use `STUDIO_IMPORT_DIR` with a separate read-only source directory and `STUDIO_UPLOAD_DIR` for output. Imports use the same upload size/validation limits. No NAS inbox is enabled by default; actual paths, permissions and deployment require a reviewed plan. Existing file selection remains available without the optional overlay.

## Browser file transfer

For unpacked NAS image folders, see [NAS_FOLDERS.ko.md](deploy/NAS_FOLDERS.ko.md). The optional one-shot `folder-import` service reads only selected subdirectories through a read-only mount and creates CBZ reading copies in the dedicated upload volume. It defaults to a metadata-only plan, preserves originals, supports natural page order and persistent receipts/cursors, and has no network access. The reviewed module is mounted read-only into a tested pinned Studio image. One NAS root-pilot registration is user-confirmed (88 pages). That fixed pilot intentionally repeats the same book. The newer bounded `root-batch` path can continue through remaining folders, backing up first and registering at most 10 new folders per invocation. Run the metadata-only plan and review its estimated copy size first; see [ROOT_FOLDER_PILOT.ko.md](deploy/ROOT_FOLDER_PILOT.ko.md). NAS originals need no PC re-upload. Existing browser/inbox archive uploads remain available.

Use **↑ 파일 관리** to select CBZ, image ZIP or PDF files (up to 20 per batch). Files stream sequentially; the default per-file limit is 512 MiB, configurable with `STUDIO_MAX_UPLOAD_BYTES` (maximum 2 GiB). ZIPs are CRC checked with bounded entry/directory/expanded-size limits; encrypted, split, unsafe-path archives are rejected. PDFs receive header/end-marker checks, not a full parser validation. PDF rendering depends on the LANraragi image.

Completed files live in a **new dedicated `studio-uploads` volume**, writable by Studio and mounted read-only under LANraragi's `content/StudioUploads`. Temporary uploads are not indexed. Existing library files are never replaced. Full-file SHA-256 deduplicates uploads; equal filenames with different bytes remain separate. Partial upstream archive IDs alone never trigger a merge: existing candidates require a matching full-file hash. Conflicting upstream IDs are shown explicitly while the separately stored upload remains downloadable.

The file-management dialog lists the most recent 100 files with **↓ 받기** links. Original bytes and the first upload's filename are preserved; authenticated byte-range downloads are available immediately, including while LANraragi indexing is pending. While the dialog is open, completed files are matched to the catalog every five seconds; **열기** appears after indexing. Existing work detail downloads remain available. Both regular and `/unsen` routes use the same authentication; worker tokens cannot upload or download library files.

Both Compose files connect the shared volume. For direct Python runs set `STUDIO_UPLOAD_DIR` to a dedicated directory also exposed to LANraragi. Use the same verified UID/GID for both services. Back up **the upload volume separately together with the Studio database and LANraragi data**; the SQLite backup includes upload records but not archive bytes. Stop writers before a coordinated backup/restore. Do not remove volumes during upgrades. Interrupted transfers must be reselected; completed duplicate retries are safe. A killed process can leave unindexed `.staging/*.part` files; these are not automatically deleted.

`python -B studio/tests/upload_smoke.py` runs synthetic browser transfer/index/reader checks against the isolated loopback Compose service (default port 43126; override `STUDIO_SMOKE_PORT`). It reads the ignored development env file for authentication and never accesses external media.

## Number or URL entry

**↓ 번호·URL로 가져오기** selects a provider, accepts a number/full URL and routes to NAS/PC. **입력 확인** resolves locally without contacting the source or creating a work/job. Hitomi/nHentai numbers derive that provider's URL; first-time E-Hentai numbers require the complete URL including its gallery identifier. Previously saved qualified identities reuse their full original URL and host. A mismatched provider/URL is rejected. Existing catalog files open their detail instead of queuing another download; metadata-only entries retain their existing work link. Active jobs remain deduplicated by provider+ID, target and engine. Neither number resolution nor a queued job proves remote access/download success. The actual engine and any normal authenticated access are still required. The dialog explicitly says actual engine/site access is unverified. The existing NAS image does not contain this UI; the reviewed [source-only Studio update](deploy/NAS_UI_UPDATE.ko.md) prepares it without replacing the images. Source completion is not proof that the NAS update was run.

`python -B studio/tests/download_reference_smoke.py` verifies the local resolver, missing identifiers, source separation, existing-file handling and desktop/mobile UI with synthetic metadata only.

## Current implementation

- Korean thumbnail/list interface, title/artist/tag/source-ID search, pagination, eight sort modes, cover sizes and reading direction.
- Works with separately stored E-Hentai, Hitomi and nHentai identities and full original URLs. An identity already attached to another work is rejected rather than silently merged.
- Per-source tags, imported comment JSON and a bounded nHentai comment connector (synthetic response tests only); combined tag search; manual title locking; favorites, ratings and reading history.
- LANraragi catalog synchronization, authenticated thumbnail/archive/page proxy, browser reader and PC archive download.
- NAS URL-download queue using installed LANraragi download plugins. Missing plugins block the job explicitly.
- PC/NAS command-engine agent with target-specific claims, leases, heartbeats, output manifests and SHA-256 records. An engine that exits without producing supported files does not complete the job.
- Metadata JSON export. Original files and the upstream Redis schema are not rewritten by Studio.

## Run locally

Python 3.12+, Node.js for JS syntax checks, and Docker Compose are required for the full stack.

```sh
python studio/setup.py
docker compose --env-file studio/.env -f studio/compose.yaml up -d --build
```

Open `http://127.0.0.1:43120`. Login name: `admin`; the generated password is in the ignored local `studio/.env`. Do not commit or upload that file. The default library is an empty development directory. No personal media is imported automatically.

## Validation

```sh
python -B -m unittest discover -s studio/tests -v
node --check studio/web/app.js
```

The latest cloud continuation passes 130 unit/HTTP/deployment tests and the JS syntax check. Synthetic browser tests cover thumbnail-only blur, uncropped portrait/wide/tall covers, original detail/reader display, saved preferences and legacy-setting migration. A real isolated Docker rehearsal verifies the source-only NAS-style update, SQLite backup, unchanged LANraragi runtime, preserved download hashes and code rollback. Chromium verified real LANraragi 0.9.81 synchronization, a synthetic three-page CBZ reader, resume at page 2, thumbnails and a PC download with matching SHA-256 at desktop/mobile widths. The Studio image builds. The full fork image build is blocked by HTTP policy at Alpine package downloads; interoperability used the official 0.9.81 image with narrowly applied API-key/concurrency changes, not a successful full-fork build. See `CLOUD_VALIDATION.md` for exact boundaries and reproduction notes.

## DS718+ and cloud development

The Compose setup targets Linux amd64. NAS media directories, UID/GID and installed memory must be checked before deployment. Use managed cloud VPN settings for Tailscale; do not run a second Tailscale client or copy auth keys into the repo. Cloud development is separate from NAS deployment.

For NAS use, change `STUDIO_LIBRARY` to a dedicated prepared directory and bind Studio to the desired private interface. Keep the LANraragi service internal. Use a private HTTPS reverse proxy for access from other devices. Container resource caps are starting settings, not measured NAS performance guarantees. `LRR_WORKER_CONCURRENCY` accepts integers 1–32 on the Unix worker. Studio Compose defaults to 1 for DS718+; measure before raising to 2. Newly created LANraragi thumbnail/database volumes need UID/GID 9001 ownership before startup when automatic permission changes are disabled. Prepare only dedicated volumes; never recursively change an existing NAS media tree.

## External engines

Run `worker.py` on the actual destination device with `STUDIO_SERVER`, `STUDIO_WORKER_TOKEN` (use the server's separate PC or NAS token), `STUDIO_TARGET` (`pc` or `nas`), `STUDIO_OUTPUT`, and a `STUDIO_DOWNLOAD_COMMAND` JSON argv array containing `{url}` and `{output}`. Commands are configured by the operator, never through the web UI, and run without a shell. Output goes to a unique `<job-id>-<attempt-suffix>` folder on every attempt. Heartbeat failure stops the direct engine process; engines that detach subprocesses need operator inspection. Existing attempt files are preserved. The worker reports the output directory before execution and requires nonempty supported files for completion. A version-pinned gallery-dl worker image and conservative adapter are provided as an unverified site-integration candidate. It validates downloaded image signatures and creates a CBZ with source metadata. Actual site operation is not yet verified; ExHentai is disabled to prevent its automatic alternate-source fallback.

## Known incomplete areas

- Comments support JSON import and a bounded nHentai public JSON connector tested with synthetic responses only. E-Hentai/Hitomi comment collection is explicitly unsupported. No live-site success is claimed; login, rate limits and blocks are never bypassed. Refresh merges IDs within each source and preserves comments absent from later responses; up to 100 fetched comments per request, 1 MiB response limit and 60-second refresh interval.
- Cross-site matching is explicit/manual; no unverified title/number-only auto-merge.
- External tag fetching uses installed upstream metadata plugins; no live site test yet.
- Worker bearer tokens authorize only claim/report endpoints. New setups use separate `STUDIO_PC_WORKER_TOKEN` and `STUDIO_NAS_WORKER_TOKEN`; NAS Compose does not enable the legacy shared token. Expired jobs are blocked, never automatically duplicated. Explicit retry checks known upstream jobs first; an ambiguous submission without a remote ID stays blocked pending operator reconciliation. No detached-engine recovery or automatic remote-job adoption is implemented.
- SQLite backup/restore to new destinations is tested, including active WAL and lease revocation on restore. Full NAS Redis/media/secret backup and DS718+ restore rehearsal remain required.
- The user has deployed the isolated NAS pilot and registered one 88-page folder locally. Cloud tests use generated fixtures only. The new UI update/bounded batch and full NAS recovery rehearsal remain unconfirmed on the NAS; no public exposure or source move/delete is enabled.

The upstream MIT license in `COPYING` applies.
