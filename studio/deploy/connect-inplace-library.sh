#!/bin/sh
# NAS-local reviewed LRR root reader + RO source connection; no conversion/deletion.
set -eu
umask 077
mode=${1:-plan}
source=${2:-}
case "$mode" in plan|apply) ;; *) exit 2;;esac
[ "$#" -eq 2 ] || exit 2
case "$source" in /volume[0-9]*/*) ;; *) exit 2;;esac
number=${source#/volume};number=${number%%/*}
case "$number" in ''|*[!0-9]*) exit 2;;esac
cr=$(printf '\r')
case "$source" in */../*|*/..|*/./*|*/.|*//*|*,*|*'\'*|*'
'*|*"$cr"*) exit 2;;esac
printf 'Connect only own LANraragi: LRR_UID/GID=0:0, approved source RO at content/NASOriginals.\n'
printf 'Studio UID, secrets, base Compose, originals, NAS ACL, Stash/NMLO unchanged; no conversion/deletion.\n'
[ "$mode" = apply ] || exit 0
[ "$(id -u)" -eq 0 ] || exit 1
root=/volume1/docker/library-studio
control=$root-deploy
project=library-studio-nas-pilot
web=sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0
lrr=sha256:b76c792a43846f0755d0dadf98c8dd46123e8d244045e2f9b6834d9b45988957
target=/home/koyomi/lanraragi/content/NASOriginals
overlay=$root/compose.archive.yaml
[ -d "$source" ] && [ ! -L "$source" ] && [ "$(readlink -f "$source")" = "$source" ] || exit 1
[ "$(readlink -f "$root")" = "$root" ] && [ "$(stat -c '%u:%a' "$control")" = 0:700 ] || exit 1
[ ! -L "$control" ] && [ "$(readlink -f "$control")" = "$control" ] || exit 1
case "$source/" in "$root/"*) exit 1;;esac
case "$root/" in "$source/"*) exit 1;;esac
[ ! -e "$overlay" ] && [ ! -L "$overlay" ] || { printf 'Connection overlay exists; preserve and review.\n' >&2;exit 1; }
for file in compose.nas.yaml compose.import.yaml compose.pilot.yaml .env.nas compose.ui.yaml;do
  [ -f "$root/$file" ] && [ ! -L "$root/$file" ] || exit 1
done
[ -f "$control/configs.sha256" ] && [ ! -L "$control/configs.sha256" ] || exit 1
(cd "$control" && sha256sum -c controller.sha256 >/dev/null && sha256sum -c configs.sha256 >/dev/null)
docker_local() { (unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH;docker --host=unix:///var/run/docker.sock "$@"); }
identity=$(docker_local inspect --type container --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.Image}}|{{.State.Health.Status}}' "$project-lanraragi-1")
[ "$identity" = "$project|lanraragi|$lrr|healthy" ] || exit 1
identity=$(docker_local inspect --type container --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.Image}}|{{.State.Health.Status}}' "$project-studio-1")
[ "$identity" = "$project|studio|$web|healthy" ] || exit 1
for logical in studio-data lrr-database lrr-thumbnails lrr-plugins;do
  identity=$(docker_local volume inspect --format '{{.Driver}}|{{index .Labels "com.docker.compose.project"}}|{{index .Labels "com.docker.compose.volume"}}' "${project}_$logical")
  [ "$identity" = "local|$project|$logical" ] || exit 1
done
writer=$(docker_local inspect --format '{{.Config.User}}' "$project-studio-1")
case "$writer" in *:*) uid=${writer%:*};gid=${writer#*:};; *) exit 1;;esac
for value in "$uid" "$gid";do case "$value" in ''|*[!0-9]*) exit 1;;esac;[ "$value" -gt 0 ] && [ "$value" -le 2147483647 ] || exit 1;done
poll_lock=$control/poll.lock
ui_lock=$root/.studio-ui-update.lock
mkdir "$poll_lock" || { printf 'Deployment task active; retry when finished.\n' >&2;exit 75; }
printf '%s\n' "$$" > "$poll_lock/pid"
if ! mkdir "$ui_lock";then rm -f "$poll_lock/pid";rmdir "$poll_lock";exit 75;fi
printf '%s\n' "$$" > "$ui_lock/pid"
was_enabled=0;[ ! -f "$control/enabled" ] || was_enabled=1
changed=0;success=0;stage=
cleanup() {
  result=$?
  trap - EXIT
  if [ -n "$stage" ];then rm -f "$stage/before.json" "$stage/after.json";fi
  if [ "$changed" -eq 1 ] && [ "$success" -ne 1 ];then
    rm -f "$control/enabled"
    printf 'Connection incomplete. Updates paused; overlay/backups preserved. No originals converted/deleted.\n' >&2
  elif [ "$was_enabled" -eq 1 ];then : > "$control/enabled";fi
  rm -f "$ui_lock/pid" "$poll_lock/pid";rmdir "$ui_lock" "$poll_lock"
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
rm -f "$control/enabled"
stage=$(mktemp -d "$root/archive-connection.XXXXXX")
cp -p "$control/configs.sha256" "$stage/configs.before.sha256"
compose_base() { docker_local compose --env-file "$root/.env.nas" -p "$project" -f "$root/compose.nas.yaml" -f "$root/compose.import.yaml" -f "$root/compose.pilot.yaml" -f "$root/compose.ui.yaml" "$@"; }
compose_archive() { compose_base -f "$overlay" "$@"; }
compose_base config --format json > "$stage/before.json"
docker_local run --rm --pull=never --network none --read-only --cap-drop ALL --env "SOURCE=$source" --env "TARGET=$target" --entrypoint python "$web" -B -c '
import json,os
print(json.dumps({"services":{"lanraragi":{"environment":{"LRR_UID":"0","LRR_GID":"0"},"volumes":[{"type":"bind","source":os.environ["SOURCE"],"target":os.environ["TARGET"],"read_only":True,"bind":{"create_host_path":False}}]}}}))' > "$overlay"
changed=1
compose_archive config --format json > "$stage/after.json"
# Credential-bearing configs stay NAS-local, private, and are removed after validation.
docker_local run --rm --pull=never --network none --read-only --cap-drop ALL \
  --env "SOURCE=$source" --env "TARGET=$target" --env "WRITER=$writer" --env "WEB=$web" --env "LRR=$lrr" \
  --mount "type=bind,src=$stage,dst=/review,readonly" --entrypoint python "$web" -B -c '
import copy,json,os
before=json.load(open("/review/before.json"));after=json.load(open("/review/after.json"))
def canonical(c):
 for s in c["services"].values():
  if "volumes" in s:s["volumes"].sort(key=lambda m:m["target"])
 return c
before=canonical(before);after=canonical(after)
assert before["services"]["studio"]["image"]==os.environ["WEB"]
assert before["services"]["studio"]["user"]==os.environ["WRITER"]
old=before["services"]["lanraragi"];new=after["services"]["lanraragi"]
assert old["image"]==os.environ["LRR"]
uid,gid=os.environ["WRITER"].split(":")
assert old["environment"]["LRR_UID"]==uid and old["environment"]["LRR_GID"]==gid
assert str(old["environment"]["LRR_AUTOFIX_PERMISSIONS"])=="0" and str(old["environment"]["LRR_WORKER_CONCURRENCY"])=="1"
mount=[m for m in new["volumes"] if m["target"]==os.environ["TARGET"]]
assert len(mount)==1
m=mount[0];assert m["type"]=="bind" and m["source"]==os.environ["SOURCE"] and m["read_only"] and m.get("bind",{}).get("create_host_path",False) is False
expected=copy.deepcopy(before)
expected["services"]["lanraragi"]["environment"].update(LRR_UID="0",LRR_GID="0")
expected["services"]["lanraragi"]["volumes"].append(m)
assert canonical(expected)==after,"Unexpected Compose changes"
print("connection_scope=verified")'
rm -f "$stage/before.json" "$stage/after.json"
stamp=$(date -u +%Y%m%dT%H%M%SZ).$$
docker_local run --rm --pull=never --user "$writer" --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true \
  --mount "type=volume,src=${project}_studio-data,dst=/data,volume-nocopy" --entrypoint python "$web" \
  /app/backup.py backup /data/studio.db "/data/before-archive-connection-$stamp.db" > "$stage/sqlite-backup.json"
studio_started=$(docker_local inspect --format '{{.State.StartedAt}}' "$project-studio-1")
compose_archive up -d --no-deps lanraragi
ready=0
for attempt in $(seq 1 60);do
  if [ "$(docker_local inspect --format '{{.State.Health.Status}}' "$project-lanraragi-1")" = healthy ];then ready=1;break;fi
  sleep 2
done
[ "$ready" -eq 1 ] || { printf 'LANraragi health timed out; preserve for local review.\n' >&2;exit 1; }
[ "$(docker_local exec "$project-lanraragi-1" s6-setuidgid koyomi id -u)" = 0 ] || exit 1
docker_local exec "$project-lanraragi-1" s6-setuidgid koyomi test -r "$target"
identity=$(docker_local inspect --format "{{range .Mounts}}{{if eq .Destination \"$target\"}}{{.Type}}|{{.Source}}|{{.RW}}{{end}}{{end}}" "$project-lanraragi-1")
[ "$identity" = "bind|$source|false" ] || exit 1
[ "$(docker_local inspect --format '{{.State.StartedAt}}' "$project-studio-1")" = "$studio_started" ] || exit 1
# Explicit local re-review of this extra RO connection only; never adopt unrelated drift.
sha256sum -c "$stage/configs.before.sha256" >/dev/null
cp -p "$stage/configs.before.sha256" "$stage/configs.next.sha256"
sha256sum "$overlay" >> "$stage/configs.next.sha256"
mv "$stage/configs.next.sha256" "$control/configs.sha256"
success=1
printf 'connection=healthy\nlrr_reader_uid_gid=0:0\nsource_mount=read_only\nstudio_restarted=false\nnas_conversion=not_performed\n'

