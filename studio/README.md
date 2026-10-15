# Library Studio (work in progress)

A personal web library built on this LANraragi fork, with a separate small Python/SQLite service for cross-site identities, source-specific metadata and download routing. This is an initial implementation, not a finished release.

## Current implementation

- Korean thumbnail/list interface, title/artist/tag/source-ID search, pagination, eight sort modes, cover sizes and reading direction.
- Works with separately stored E-Hentai, Hitomi and nHentai identities and full original URLs. An identity already attached to another work is rejected rather than silently merged.
- Per-source tags and imported comment JSON; combined tag search; manual title locking; favorites, ratings and reading history.
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

18 tests passed on Windows, including real loopback HTTP authentication, CSRF rejection, catalog synchronization against a controlled upstream fixture, namespaced identity conflicts and engine output verification. Both images built; LANraragi's real `/api/info` returned version 0.9.81. Browser interactions, actual reading/download against synthetic archives, external sites and NAS deployment are not yet verified. See `CLOUD_HANDOFF.md`.

## DS718+ and cloud development

The Compose setup targets Linux amd64. NAS media directories, UID/GID and installed memory must be checked before deployment. Use managed cloud VPN settings for Tailscale; do not run a second Tailscale client or copy auth keys into the repo. Cloud development is separate from NAS deployment.

For NAS use, change `STUDIO_LIBRARY` to a dedicated prepared directory and bind Studio to the desired private interface. Keep the LANraragi service internal. Use a private HTTPS reverse proxy for access from other devices. Container resource caps are starting settings, not measured NAS performance guarantees. The current upstream Minion concurrency follows host CPU count and still needs an explicit low-concurrency setting for this fork.

## External engines

Run `worker.py` on the actual destination device with `STUDIO_SERVER`, `STUDIO_WORKER_TOKEN`, `STUDIO_TARGET` (`pc` or `nas`), `STUDIO_OUTPUT`, and a `STUDIO_DOWNLOAD_COMMAND` JSON argv array containing `{url}` and `{output}`. Commands are configured by the operator, never through the web UI, and run without a shell. Output goes to a new job-specific folder. No specific desktop downloader is bundled or claimed to work headlessly on Linux.

## Known incomplete areas

- Comments support JSON import only; remote comment fetching is not implemented.
- Cross-site matching is explicit/manual; no unverified title/number-only auto-merge.
- External tag fetching uses installed upstream metadata plugins; no live site test yet.
- Worker token scope, resumable/retry output handling and upstream job restart recovery need tightening before deployment.
- SQLite export exists; a tested restore/migration workflow is still needed.
- No personal archive import, NAS deployment, public exposure or production data changes have occurred.

The upstream MIT license in `COPYING` applies.
