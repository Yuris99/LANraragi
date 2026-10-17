#!/bin/sh
# Bounded NAS-local folder continuation. Never restarts services or changes originals.
set -eu
umask 077
mode=${1:-preview}
source=${2:-}
case "$mode" in preview|plan|batch) ;; *) printf 'Use: manage-folders-root.sh preview|plan|batch /volumeN/SHARE/ROOT\n' >&2;exit 2;;esac
case "$source" in /volume[0-9]*/*) ;; *) printf 'Use the verified absolute NAS source path\n' >&2;exit 2;;esac
cr=$(printf '\r')
case "$source" in */../*|*/..|*/./*|*/.|*//*|*,*|*'\'*|*'
'*|*"$cr"*) printf 'Use a canonical source path\n' >&2;exit 2;;esac
number=${source#/volume};number=${number%%/*}
case "$number" in ''|*[!0-9]*) printf 'Invalid NAS volume\n' >&2;exit 2;;esac
project=library-studio-nas-pilot
web_image=sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0
lrr_image=sha256:b76c792a43846f0755d0dadf98c8dd46123e8d244045e2f9b6834d9b45988957
data_volume=${project}_studio-data
upload_volume=${project}_studio-uploads
printf 'Bounded folder registration: project=%s; source reader=root (0:0), no inherited account groups.\n' "$project"
printf 'Source: %s (read-only); collections=manga,images; plan counts metadata only; batch registers at most 10 new folders, 512 MiB per archive.\n' "$source"
printf 'Batch backs up Studio SQLite first; receipts skip existing copies and a cursor resumes later folders.\n'
printf 'Writes only own Studio data/uploads volumes. No network, ACL/ownership changes or service restart.\n'
[ "$mode" != preview ] || { printf 'Preview only: no downloads, containers or NAS changes.\n';exit 0; }
[ -d "$source" ] && [ ! -L "$source" ] && [ "$(readlink -f "$source")" = "$source" ] || { printf 'Verify the existing canonical source path first.\n' >&2;exit 1; }
docker_local() { sudo sh -c 'unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH; exec docker --host=unix:///var/run/docker.sock "$@"' library-studio-root-folder-pilot "$@"; }
writer=$(docker_local inspect --type container --format '{{.Config.User}}' "$project-studio-1")
case "$writer" in *:*) output_uid=${writer%:*};output_gid=${writer#*:};; *) printf 'Expected numeric non-root app UID:GID; no import.\n' >&2;exit 1;;esac
for identity in "$output_uid" "$output_gid";do
  case "$identity" in ''|*[!0-9]*) printf 'Invalid app writer identity\n' >&2;exit 1;;esac
  [ "$identity" -gt 0 ] && [ "$identity" -le 2147483647 ] || exit 1
done
printf 'Dedicated app outputs use UID/GID=%s:%s; original files remain read-only.\n' "$output_uid" "$output_gid"
verify_pilot() {
  metadata=$(docker_local inspect --type container --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.Image}}|{{.Config.User}}|{{.State.Status}}|{{.State.Health.Status}}' "$project-studio-1")
  [ "$metadata" = "$project|studio|$web_image|$writer|running|healthy" ] || { printf 'Studio identity/health differs; no import.\n' >&2;exit 1; }
  metadata=$(docker_local inspect --type container --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.Image}}|{{.State.Status}}|{{.State.Health.Status}}' "$project-lanraragi-1")
  [ "$metadata" = "$project|lanraragi|$lrr_image|running|healthy" ] || { printf 'LANraragi identity/health differs; no import.\n' >&2;exit 1; }
  identities=$(docker_local inspect --type container --format "{{range .Config.Env}}{{if eq . \"LRR_UID=$output_uid\"}}uid-ok{{end}}{{if eq . \"LRR_GID=$output_gid\"}}gid-ok{{end}}{{end}}" "$project-lanraragi-1")
  case "$identities" in uid-okgid-ok|gid-okuid-ok) ;; *) printf 'LANraragi app UID/GID does not match Studio; no import.\n' >&2;exit 1;;esac
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
work=$(mktemp -d /tmp/library-studio-root-folder-pilot.XXXXXX)
revision=90a3d73b8d6c45f6b16af9cf2c89cdd69f728c8c
digest=c8231ca764601763e290cf1416faef048272145703cf984595c111262c8bebc2
curl -fsSL --connect-timeout 15 --max-time 60 \
  "https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio/folder_importer.py" -o "$work/folder_importer.py"
printf '%s  %s\n' "$digest" "$work/folder_importer.py" | sha256sum -c -
chmod 644 "$work/folder_importer.py"
verify_pilot
set -- run --rm --pull=never --user 0:0 --network none --read-only --memory 256m \
  --cap-drop ALL --cap-add DAC_OVERRIDE --cap-add SETUID --cap-add SETGID --security-opt no-new-privileges:true \
  --mount "type=bind,src=$source,dst=/nas-library,readonly" \
  --mount "type=bind,src=$work/folder_importer.py,dst=/app/folder_importer.py,readonly"
operation=root-plan
if [ "$mode" = batch ];then
  operation=root-batch
  set -- "$@" --env STUDIO_DATABASE=/data/studio.db --env STUDIO_UPLOAD_DIR=/uploads \
    --env "STUDIO_FOLDER_OUTPUT_UID=$output_uid" --env "STUDIO_FOLDER_OUTPUT_GID=$output_gid" \
    --mount "type=volume,src=$data_volume,dst=/data,volume-nocopy" \
    --mount "type=volume,src=$upload_volume,dst=/uploads,volume-nocopy"
fi
docker_local "$@" --entrypoint python "$web_image" /app/folder_importer.py --operation "$operation" --limit 10 --collections '["manga","images"]'
