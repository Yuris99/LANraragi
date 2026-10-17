#!/bin/sh
# One pinned NAS-local folder pilot. Never restarts services or changes originals.
set -eu
umask 077
mode=${1:-preview}
source=${2:-}
case "$mode" in preview|run) ;; *) printf 'Use: import-one-folder.sh preview|run /volumeN/SHARE/ROOT\n' >&2;exit 2;;esac
case "$source" in /volume[0-9]*/*) ;; *) printf 'Use the verified absolute NAS source path\n' >&2;exit 2;;esac
case "$source" in */../*|*/..|*/./*|*/.|*//*|*,*|*'\'*|*'
'*|*'
'*) printf 'Use a canonical source path\n' >&2;exit 2;;esac
number=${source#/volume};number=${number%%/*}
case "$number" in ''|*[!0-9]*) printf 'Invalid NAS volume\n' >&2;exit 2;;esac
runtime_uid=$(id -u);runtime_gid=$(id -g);groups=$(id -G)
[ "$runtime_uid:$runtime_gid" = 1026:100 ] || { printf 'Run as the approved ordinary account UID1026/GID100, not sudo sh.\n' >&2;exit 1; }
set --
for group in $groups;do
  case "$group" in ''|*[!0-9]*) printf 'Invalid numeric group identity\n' >&2;exit 2;;esac
  [ "$group" -le 2147483647 ] || exit 2
  set -- "$@" --group-add "$group"
done
[ "$#" -gt 0 ] || { printf 'Cannot determine current account groups\n' >&2;exit 1; }
project=library-studio-nas-pilot
web_image=sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0
lrr_image=sha256:b76c792a43846f0755d0dadf98c8dd46123e8d244045e2f9b6834d9b45988957
data_volume=${project}_studio-data
upload_volume=${project}_studio-uploads
printf 'One-folder pilot: project=%s UID/GID=%s:%s existing groups=%s\n' "$project" "$runtime_uid" "$runtime_gid" "$groups"
printf 'Source: %s (read-only); collection=manga; at most one generated CBZ, 128 MiB limit.\n' "$source"
printf 'First back up Studio SQLite in its own data volume; pin the selected folder for retries.\n'
printf 'Writes only own Studio data/uploads volumes. No network, ACL/ownership changes or service restart.\n'
[ "$mode" != preview ] || { printf 'Preview only: no downloads, containers or NAS changes.\n';exit 0; }
[ -d "$source" ] && [ ! -L "$source" ] && [ "$(readlink -f "$source")" = "$source" ] || { printf 'Verify the existing canonical source path first.\n' >&2;exit 1; }
docker_local() { sudo sh -c 'unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH; exec docker --host=unix:///var/run/docker.sock "$@"' library-studio-folder-pilot "$@"; }
verify_pilot() {
  metadata=$(docker_local inspect --type container --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.Image}}|{{.Config.User}}|{{.State.Status}}|{{.State.Health.Status}}' "$project-studio-1")
  [ "$metadata" = "$project|studio|$web_image|1026:100|running|healthy" ] || { printf 'Studio identity/health differs; no import.\n' >&2;exit 1; }
  metadata=$(docker_local inspect --type container --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.Image}}|{{.State.Status}}|{{.State.Health.Status}}' "$project-lanraragi-1")
  [ "$metadata" = "$project|lanraragi|$lrr_image|running|healthy" ] || { printf 'LANraragi identity/health differs; no import.\n' >&2;exit 1; }
  for name in studio-data studio-uploads;do
    metadata=$(docker_local volume inspect --format '{{.Driver}}|{{index .Labels "com.docker.compose.project"}}|{{index .Labels "com.docker.compose.volume"}}' "${project}_$name")
    [ "$metadata" = "local|$project|$name" ] || { printf 'Dedicated volume identity differs; no import.\n' >&2;exit 1; }
  done
  metadata=$(docker_local inspect --type container --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}|{{.Type}}|{{.RW}}{{end}}{{end}}' "$project-studio-1")
  [ "$metadata" = "$data_volume|volume|true" ] || { printf 'Studio data mount differs; no import.\n' >&2;exit 1; }
  metadata=$(docker_local inspect --type container --format '{{range .Mounts}}{{if eq .Destination "/uploads"}}{{.Name}}|{{.Type}}|{{.RW}}{{end}}{{end}}' "$project-studio-1")
  [ "$metadata" = "$upload_volume|volume|true" ] || { printf 'Studio upload mount differs; no import.\n' >&2;exit 1; }
  metadata=$(docker_local inspect --type container --format '{{range .Mounts}}{{if eq .Destination "/home/koyomi/lanraragi/content/StudioUploads"}}{{.Name}}|{{.Type}}|{{.RW}}{{end}}{{end}}' "$project-lanraragi-1")
  [ "$metadata" = "$upload_volume|volume|false" ] || { printf 'LANraragi upload mount differs; no import.\n' >&2;exit 1; }
}
verify_pilot
work=$(mktemp -d /tmp/library-studio-folder-pilot.XXXXXX)
revision=4589148e68efffbe712abb52c1e0c6bece8b92b4
digest=a2125ce3ac91dbe55c5b5a408f35e91235f75960b703a8e5409f297edae611c1
curl -fsSL --connect-timeout 15 --max-time 60 \
  "https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio/folder_importer.py" -o "$work/folder_importer.py"
printf '%s  %s\n' "$digest" "$work/folder_importer.py" | sha256sum -c -
chmod 644 "$work/folder_importer.py"
verify_pilot
docker_local run --rm --pull=never --user "$runtime_uid:$runtime_gid" "$@" \
  --network none --read-only --memory 256m --cap-drop ALL --security-opt no-new-privileges:true \
  --env STUDIO_DATABASE=/data/studio.db --env STUDIO_UPLOAD_DIR=/uploads \
  --mount "type=bind,src=$source,dst=/nas-library,readonly" \
  --mount "type=bind,src=$work/folder_importer.py,dst=/app/folder_importer.py,readonly" \
  --mount "type=volume,src=$data_volume,dst=/data,volume-nocopy" \
  --mount "type=volume,src=$upload_volume,dst=/uploads,volume-nocopy" \
  --entrypoint python "$web_image" /app/folder_importer.py --operation pilot --collections '["manga"]'
