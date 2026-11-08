#!/bin/sh
# Separate NAS-local opt-in. App code updates cannot grant original write access.
set -eu
umask 077
mode=${1:-preview};revision=${2:-};code_sha=${3:-}
case "$mode" in preview|install) ;; *) exit 2;;esac
[ "$#" -le 3 ] || exit 2
printf 'Install one fixed, network-none single-file deletion worker. No existing service restart.\n'
printf 'RW: existing NAS manga/images only, own Studio data/uploads. No socket, ports or host privilege.\n'
printf 'Compatibility v2: permanently non-root DAC worker, kernel nproc32, CPU0/shares128/nice19, hash pacing target half CPU.\n'
printf 'Only an authenticated, explicitly confirmed work/file hash can be deleted. No recursive deletion.\n'
[ "$mode" = install ] || { printf 'Preview only: no Docker, network or files changed.\n';exit 0; }
printf '%s\n' "$revision" | LC_ALL=C grep -Eq '^[0-9a-f]{40}$' || exit 2
printf '%s\n' "$code_sha" | LC_ALL=C grep -Eq '^[0-9a-f]{64}$' || exit 2
[ "$(id -u)" -eq 0 ] || { printf 'NAS-local root installation required.\n' >&2;exit 1; }
control=/volume1/docker/library-studio-deletions
project=library-studio-nas-pilot
container=library-studio-file-deletion
docker_local() { (unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH;docker --host=unix:///var/run/docker.sock "$@"); }
[ "$(readlink -f /volume1/docker)" = /volume1/docker ] || exit 1
[ ! -e "$control" ] && [ ! -L "$control" ] || { printf 'Installation exists; preserve and inspect.\n' >&2;exit 1; }
if docker_local inspect --type container "$container" >/dev/null 2>&1;then printf 'Worker already exists; preserve and inspect.\n' >&2;exit 1;fi
identity=$(docker_local inspect --type container --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.State.Health.Status}}' "$project-studio-1")
[ "$identity" = "$project|studio|healthy" ] || exit 1
limits=$(docker_local info --format '{{.MemoryLimit}}|{{.SwapLimit}}|{{.CpuShares}}|{{.Cpuset}}')
[ "$limits" = 'true|true|true|true' ] || { printf 'Required compatibility limits unavailable; no installation.\n' >&2;exit 1; }
image=$(docker_local inspect --type container --format '{{.Image}}' "$project-studio-1")
printf '%s\n' "$image" | LC_ALL=C grep -Eq '^sha256:[0-9a-f]{64}$' || exit 1
writer=$(docker_local inspect --type container --format '{{.Config.User}}' "$project-studio-1")
case "$writer" in *:*) uid=${writer%:*};gid=${writer#*:};; *) exit 1;;esac
case "$uid" in ''|*[!0-9]*|0) exit 1;;esac
case "$gid" in ''|*[!0-9]*|0) exit 1;;esac
identity=$(docker_local inspect --type container --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}' "$project-lanraragi-1")
[ "$identity" = "$project|lanraragi" ] || exit 1
source=$(docker_local inspect --type container --format '{{range .Mounts}}{{if eq .Destination "/home/koyomi/lanraragi/content/NASOriginals"}}{{.Source}}{{end}}{{end}}' "$project-lanraragi-1")
mount=$(docker_local inspect --type container --format '{{range .Mounts}}{{if eq .Destination "/home/koyomi/lanraragi/content/NASOriginals"}}{{.Type}}|{{.RW}}{{end}}{{end}}' "$project-lanraragi-1")
[ "$mount" = 'bind|false' ] || exit 1
case "$source" in /volume[0-9]*/*) ;; *) exit 1;;esac
case "$source" in *,*|*'\'*|*'
'*|*/../*|*/..|*/./*|*/.|*//*) exit 1;;esac
[ "$(readlink -f "$source")" = "$source" ] || exit 1
for collection in manga images;do
  [ -d "$source/$collection" ] && [ ! -L "$source/$collection" ] && [ "$(readlink -f "$source/$collection")" = "$source/$collection" ] || exit 1
done
for name in studio-data studio-uploads;do
  identity=$(docker_local volume inspect --format '{{.Driver}}|{{index .Labels "com.docker.compose.project"}}|{{index .Labels "com.docker.compose.volume"}}' "${project}_$name")
  [ "$identity" = "local|$project|$name" ] || exit 1
  case "$name" in studio-data) target=/data;; studio-uploads) target=/uploads;;esac
  identity=$(docker_local inspect --format "{{range .Mounts}}{{if eq .Destination \"$target\"}}{{.Name}}|{{.Type}}|{{.RW}}{{end}}{{end}}" "$project-studio-1")
  [ "$identity" = "${project}_$name|volume|true" ] || exit 1
done
docker_local exec "$project-studio-1" python -B -c '
import os,sqlite3,sys,hashlib
from pathlib import Path
import file_deletion
from server import STUDIO_UPDATE
assert STUDIO_UPDATE>=43
assert hashlib.sha256(Path(file_deletion.__file__).read_bytes()).hexdigest()==sys.argv[1]
db=sqlite3.connect(os.environ["STUDIO_DATABASE"])
assert db.execute("SELECT count(*) FROM file_deletions WHERE state IN (?,?)",("queued","deleting")).fetchone()[0]==0
db.close()
print("catalog_ready_no_pending_deletions=true")' "$code_sha"
mkdir -m 700 "$control"
curl -fsSL --connect-timeout 15 --max-time 60 "https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio/file_deletion.py" -o "$control/file_deletion.py.part"
printf '%s  %s\n' "$code_sha" "$control/file_deletion.py.part" | sha256sum -c - >/dev/null
mv "$control/file_deletion.py.part" "$control/file_deletion.py"
chmod 400 "$control/file_deletion.py"
printf '%s\n' "$revision" > "$control/revision"
printf '%s\n' "$code_sha" > "$control/code.sha256"
check=library-studio-file-deletion-check
if docker_local inspect --type container "$check" >/dev/null 2>&1;then printf 'Existing compatibility probe; preserve and inspect.\n' >&2;exit 1;fi
docker_local run --rm --pull=never --name "$check" --label studio.file-deletion-check=1 \
  --user 0:0 --network none --read-only --no-healthcheck --memory 256m --memory-swap 256m \
  --cpuset-cpus 0 --cpu-shares 128 --ulimit nproc=32:32 \
  --cap-drop ALL --cap-add DAC_OVERRIDE --cap-add SETUID --cap-add SETGID --security-opt no-new-privileges:true \
  --tmpfs /tmp:rw,nosuid,noexec,size=32m \
  --mount "type=bind,src=$control,dst=/tools,readonly" \
  --entrypoint python "$image" -B /tools/file_deletion.py --probe-limits --writer-uid "$uid" --writer-gid "$gid" > "$control/compatibility.json"
python_code='import json,sys
v=json.load(sys.stdin)
assert v["mode"]=="nonroot-rlimit-v2" and v["kernel_nproc_block_observed"]
assert v["root_recovery_blocked"] and v["database_dac_disabled"] and v["database_owner_preserved"]'
# Validate only generated probe flags in the existing app's non-root context.
docker_local exec -i "$project-studio-1" python -B -c "$python_code" < "$control/compatibility.json"
docker_local run -d --pull=never --name "$container" --label studio.file-deletion=1 --label studio.file-deletion-profile=nonroot-rlimit-v2 --restart unless-stopped \
  --user 0:0 --network none --read-only --no-healthcheck --memory 256m --memory-swap 256m \
  --cpuset-cpus 0 --cpu-shares 128 --ulimit nproc=32:32 \
  --cap-drop ALL --cap-add DAC_OVERRIDE --cap-add SETUID --cap-add SETGID --security-opt no-new-privileges:true \
  --mount "type=bind,src=$source/manga,dst=/originals/manga" \
  --mount "type=bind,src=$source/images,dst=/originals/images" \
  --mount "type=volume,src=${project}_studio-data,dst=/data,volume-nocopy" \
  --mount "type=volume,src=${project}_studio-uploads,dst=/uploads,volume-nocopy" \
  --mount "type=bind,src=$control,dst=/tools,readonly" \
  --entrypoint python "$image" -B /tools/file_deletion.py --database /data/studio.db \
  --originals /originals --uploads /uploads --writer-uid "$uid" --writer-gid "$gid" >/dev/null
printf 'Worker started. Verify its heartbeat in Studio before confirming any file deletion.\n'
