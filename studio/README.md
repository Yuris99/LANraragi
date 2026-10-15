# Library Studio (work in progress)

A personal web library built on this LANraragi fork, with a separate small Python/SQLite service for cross-site identities, source-specific metadata and download routing. This is an initial implementation, not a finished release.

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

The cloud continuation passes 32 tests and the JS syntax check. Chromium verified real LANraragi 0.9.81 synchronization, a synthetic three-page CBZ reader, resume at page 2, thumbnails and a PC download with matching SHA-256 at desktop/mobile widths. The Studio image builds. The full fork image build is blocked by HTTP policy at Alpine package downloads; interoperability used the official 0.9.81 image with narrowly applied API-key/concurrency changes, not a successful full-fork build. See `CLOUD_VALIDATION.md` for exact boundaries and reproduction notes.

## DS718+ and cloud development

The Compose setup targets Linux amd64. NAS media directories, UID/GID and installed memory must be checked before deployment. Use managed cloud VPN settings for Tailscale; do not run a second Tailscale client or copy auth keys into the repo. Cloud development is separate from NAS deployment.

For NAS use, change `STUDIO_LIBRARY` to a dedicated prepared directory and bind Studio to the desired private interface. Keep the LANraragi service internal. Use a private HTTPS reverse proxy for access from other devices. Container resource caps are starting settings, not measured NAS performance guarantees. `LRR_WORKER_CONCURRENCY` accepts integers 1–32 on the Unix worker. Studio Compose defaults to 1 for DS718+; measure before raising to 2. Newly created LANraragi thumbnail/database volumes need UID/GID 9001 ownership before startup when automatic permission changes are disabled. Prepare only dedicated volumes; never recursively change an existing NAS media tree.

## External engines

Run `worker.py` on the actual destination device with `STUDIO_SERVER`, `STUDIO_WORKER_TOKEN`, `STUDIO_TARGET` (`pc` or `nas`), `STUDIO_OUTPUT`, and a `STUDIO_DOWNLOAD_COMMAND` JSON argv array containing `{url}` and `{output}`. Commands are configured by the operator, never through the web UI, and run without a shell. Output goes to a unique `<job-id>-<attempt-suffix>` folder on every attempt. Heartbeat failure stops the direct engine process; engines that detach subprocesses need operator inspection. Existing attempt files are preserved. The worker reports the output directory before execution and requires nonempty supported files for completion. No specific desktop downloader is bundled or claimed to work headlessly on Linux.

## Known incomplete areas

- Comments support JSON import and a bounded nHentai public JSON connector tested with synthetic responses only. E-Hentai/Hitomi comment collection is explicitly unsupported. No live-site success is claimed; login, rate limits and blocks are never bypassed. Refresh merges IDs within each source and preserves comments absent from later responses; up to 100 fetched comments per request, 1 MiB response limit and 60-second refresh interval.
- Cross-site matching is explicit/manual; no unverified title/number-only auto-merge.
- External tag fetching uses installed upstream metadata plugins; no live site test yet.
- Worker bearer tokens authorize only claim/report endpoints. Expired jobs are blocked, never automatically duplicated. Explicit retry checks known upstream jobs first; an ambiguous submission without a remote ID stays blocked pending operator reconciliation. No detached-engine recovery or automatic remote-job adoption is implemented.
- SQLite export exists; a tested restore/migration workflow is still needed.
- No personal archive import, NAS deployment, public exposure or production data changes have occurred.

The upstream MIT license in `COPYING` applies.
