#!/bin/sh
# Fixed NAS-local source reader. No host commands or paths come from web jobs.
set -eu
umask 077
[ "$#" -eq 0 ] || exit 2
[ "$(id -u)" -eq 0 ] || exit 1
control=$(CDPATH='' cd "$(dirname "$0")" && pwd -P)
case "$control" in /volume*/docker/library-studio-folders) ;; *) exit 1;;esac
[ "$(stat -c '%u:%a' "$control")" = 0:700 ] || exit 1
cd "$control"
sha256sum -c controller.sha256 >/dev/null
(cd code && sha256sum -c runtime-manifest.sha256 >/dev/null)
source=$(cat source.path)
[ -d "$source" ] && [ ! -L "$source" ] && [ "$(readlink -f "$source")" = "$source" ] || exit 1
writer=$(cat writer)
case "$writer" in *:*) uid=${writer%:*};gid=${writer#*:};; *) exit 1;;esac
for value in "$uid" "$gid";do case "$value" in ''|*[!0-9]*) exit 1;;esac;[ "$value" -gt 0 ] && [ "$value" -le 2147483647 ] || exit 1;done
project=library-studio-nas-pilot
image=sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0
docker_local() { (unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH;docker --host=unix:///var/run/docker.sock "$@"); }
identity=$(docker_local inspect --type container --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.Image}}|{{.Config.User}}|{{.State.Health.Status}}' "$project-studio-1")
[ "$identity" = "$project|studio|$image|$writer|healthy" ] || { printf 'Studio identity/health differs; no source access.\n' >&2;exit 1; }
for pair in '/data:studio-data' '/uploads:studio-uploads';do
  target=${pair%:*};name=${pair#*:}
  identity=$(docker_local volume inspect --format '{{.Driver}}|{{index .Labels "com.docker.compose.project"}}|{{index .Labels "com.docker.compose.volume"}}' "${project}_$name")
  [ "$identity" = "local|$project|$name" ] || exit 1
  identity=$(docker_local inspect --format "{{range .Mounts}}{{if eq .Destination \"$target\"}}{{.Name}}|{{.Type}}|{{.RW}}{{end}}{{end}}" "$project-studio-1")
  [ "$identity" = "${project}_$name|volume|true" ] || exit 1
done
if existing=$(docker_local inspect --type container --format '{{.Image}}|{{index .Config.Labels "studio.folder-queue"}}|{{.State.Running}}' library-studio-folder-queue 2>/dev/null);then
  [ "$existing" = "$image|1|true" ] || { printf 'Unexpected queue container; preserve and inspect.\n' >&2;exit 1; }
  printf '{"worker":"busy"}\n';exit 0
fi
docker_local run --rm --pull=never --name library-studio-folder-queue --label studio.folder-queue=1 --user 0:0 --network none --read-only --memory 256m \
  --cap-drop ALL --cap-add DAC_OVERRIDE --cap-add SETUID --cap-add SETGID --security-opt no-new-privileges:true \
  --mount "type=bind,src=$source,dst=/nas-library,readonly" \
  --mount "type=bind,src=$control/code,dst=/app,readonly" \
  --mount "type=volume,src=${project}_studio-data,dst=/data,volume-nocopy" \
  --mount "type=volume,src=${project}_studio-uploads,dst=/uploads,volume-nocopy" \
  --env STUDIO_DATABASE=/data/studio.db --env STUDIO_UPLOAD_DIR=/uploads \
  --env "STUDIO_FOLDER_OUTPUT_UID=$uid" --env "STUDIO_FOLDER_OUTPUT_GID=$gid" \
  --entrypoint python "$image" /app/folder_importer.py --operation root-queue --collections '["manga","images"]'
