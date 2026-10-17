#!/bin/sh
# Explicit reviewed pilot only. Default is a read-only plan; never adopts old data.
set -eu
mode=${1:-plan}
root=${2:-/volume1/docker/library-studio}
runtime_uid=${3:-}
runtime_gid=${4:-}
case "$mode" in plan|install) ;; *) printf 'Use: sh install-pilot.sh plan|install /volumeN/docker/library-studio UID GID\n' >&2; exit 2;; esac
case "$root" in /volume*/docker/library-studio) ;; *) printf 'Refusing non-dedicated root\n' >&2; exit 2;; esac
volume=${root%/docker/library-studio};number=${volume#/volume}
case "$number" in ''|*[!0-9]*) printf 'Invalid volume root\n' >&2; exit 2;; esac
for identity in "$runtime_uid" "$runtime_gid"; do
  case "$identity" in ''|*[!0-9]*) printf 'Supply verified numeric UID/GID\n' >&2; exit 2;; esac
  [ "$identity" -gt 0 ] && [ "$identity" -le 2147483647 ] || exit 2
done
bundle=$(CDPATH='' cd "$(dirname "$0")" && pwd)
project=library-studio-nas-pilot
web_image=$(sed -n 's/^web=//p' "$bundle/images.ids")
lrr_image=$(sed -n 's/^lanraragi=//p' "$bundle/images.ids")
for image in "$web_image" "$lrr_image"; do
  printf '%s\n' "$image" | LC_ALL=C grep -Eq '^sha256:[0-9a-f]{64}$' || { printf 'Invalid bundled image identity\n' >&2; exit 2; }
done
printf 'PILOT: official LANraragi 0.9.81 compatibility runtime; full fork build is NOT verified.\n'
printf 'Project: %s\nNew root: %s\nRuntime UID/GID: %s:%s\nAccess: 127.0.0.1:43120 (SSH tunnel)\n' "$project" "$root" "$runtime_uid" "$runtime_gid"
printf 'Creates 5 new dedicated volumes, library/downloads/inbox; copies inbox files without deleting originals.\n'
printf 'External site worker: disabled. Existing NMLO/Stash services: unchanged.\n'
printf 'Install requires the dedicated non-administrator library-studio account; personal UID1026 is refused.\n'
[ "$mode" = install ] || { printf 'Plan only: no files, images or services changed.\n'; exit 0; }
[ "$(id -u)" -eq 0 ] || { printf 'Install requires sudo; do not change docker group/socket permissions.\n' >&2; exit 1; }
# Verify the named service account before Docker, mkdir, chown or secrets.
sh "$bundle/check-service-account.sh" check "$runtime_uid" "$runtime_gid"
[ "$(uname -m)" = x86_64 ] || { printf 'Only the reviewed amd64 pilot is bundled.\n' >&2; exit 1; }
[ -d "$volume/docker" ] && [ ! -L "$volume" ] && [ ! -L "$volume/docker" ] || { printf 'Verify existing volume/docker parent first.\n' >&2; exit 1; }
[ ! -e "$root" ] && [ ! -L "$root" ] || { printf 'Root already exists: refusing adoption or overwrite. Preserve it and inspect.\n' >&2; exit 1; }
docker_local() { (unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH; docker --host=unix:///var/run/docker.sock "$@"); }
docker_local version --format '{{.Server.Version}}' >/dev/null
docker_local compose version --short >/dev/null
[ -z "$(docker_local ps -aq --filter "label=com.docker.compose.project=$project")" ] || { printf 'Project already exists; refusing duplicate install.\n' >&2; exit 1; }
[ -z "$(docker_local volume ls -q --filter "label=com.docker.compose.project=$project")" ] || { printf 'Project volumes already exist; use reviewed recovery procedure.\n' >&2; exit 1; }
if command -v ss >/dev/null 2>&1; then
  [ -z "$(ss -ltnH 'sport = :43120' 2>/dev/null)" ] || { printf 'Port 43120 is already listening; stop and review.\n' >&2; exit 1; }
fi
(cd "$bundle" && sha256sum -c bundle.sha256)
docker_local load -i "$bundle/images.tar.gz"
for image in "$web_image" "$lrr_image"; do docker_local image inspect "$image" --format '{{.Id}}' | grep -Fx "$image" >/dev/null; done
# mkdir is exclusive: a concurrent/previous installation is never overwritten.
mkdir "$root"
mkdir "$root/library" "$root/library/downloads" "$root/inbox"
chown "$runtime_uid:$runtime_gid" "$root" "$root/library" "$root/library/downloads" "$root/inbox"
chmod 750 "$root" "$root/library" "$root/library/downloads" "$root/inbox"
cp "$bundle/compose.nas.yaml" "$bundle/compose.import.yaml" "$bundle/compose.pilot.yaml" "$root/"
chmod 644 "$root/compose.nas.yaml" "$root/compose.import.yaml" "$root/compose.pilot.yaml"
docker_local run --rm --user "$runtime_uid:$runtime_gid" --entrypoint python \
  --mount "type=bind,src=$root,dst=/nas" "$web_image" /app/prepare_nas.py \
  --output /nas/.env.nas --library "$root/library" --downloads "$root/library/downloads" \
  --uid "$runtime_uid" --gid "$runtime_gid" --lrr-image "$lrr_image" --web-image "$web_image"
printf 'STUDIO_INBOX=%s/inbox\n' "$root" >> "$root/.env.nas"
cd "$root"
docker_local compose --env-file .env.nas -p "$project" -f compose.nas.yaml -f compose.import.yaml -f compose.pilot.yaml config --quiet
docker_local compose --env-file .env.nas -p "$project" -f compose.nas.yaml -f compose.import.yaml -f compose.pilot.yaml up -d
printf 'Pilot started. Check health with the compose ps command in the included guide.\n'
printf 'Login admin; password is only in %s/.env.nas. Do not send this file to chat/cloud/GitHub.\n' "$root"
printf 'If startup fails, preserve new directories/volumes; do not run down -v or delete data.\n'
