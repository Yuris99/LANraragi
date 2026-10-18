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
changed=0;success=0;stage=;phase=locked
step() { phase=$1;printf 'connection_phase=%s\n' "$phase";if [ -n "$stage" ];then printf '%s\n' "$phase" > "$stage/phase";fi; }
cleanup() {
  result=$?
  trap - EXIT
  if [ -n "$stage" ];then rm -f "$stage/before.json" "$stage/after.json";fi
  if [ "$result" -ne 0 ];then printf 'connection_exit=%s phase=%s\n' "$result" "$phase" >&2;fi
  if [ "$changed" -eq 1 ] && [ "$success" -ne 1 ];then
    rm -f "$control/enabled"
    printf 'connection_failed phase=%s exit=%s; updates paused, overlay/backups preserved; no originals converted/deleted.\n' "$phase" "$result" >&2
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
step pending_check
if [ -e "$overlay" ] || [ -L "$overlay" ];then
  # Recover ONLY this exact unapplied proposal. Never replace a registered or
  # live connection, different source/settings, symlink, or unknown file.
  [ -f "$overlay" ] && [ ! -L "$overlay" ] && [ "$(stat -c '%u' "$overlay")" = 0 ] || exit 1
  [ "$was_enabled" -eq 0 ] || { printf 'Existing overlay with enabled updates; preserve and review.\n' >&2;exit 1; }
  if grep -F -- " $overlay" "$control/configs.sha256" >/dev/null;then printf 'Existing registered connection; preserve and review.\n' >&2;exit 1;fi
  [ "$(docker_local exec "$project-lanraragi-1" s6-setuidgid koyomi id -u)" = "$uid" ] || { printf 'Existing reader is not the unchanged nonroot reader; preserve and review.\n' >&2;exit 1; }
  live_mount=$(docker_local inspect --format "{{range .Mounts}}{{if eq .Destination \"$target\"}}present{{end}}{{end}}" "$project-lanraragi-1")
  [ -z "$live_mount" ] || { printf 'Source already attached; preserve and review.\n' >&2;exit 1; }
  docker_local run --rm -i --pull=never --network none --read-only --cap-drop ALL --env "SOURCE=$source" --env "TARGET=$target" --entrypoint python "$web" -B -c '
import json,os,sys
expected={"services":{"lanraragi":{"environment":{"LRR_UID":"0","LRR_GID":"0"},"volumes":[{"type":"bind","source":os.environ["SOURCE"],"target":os.environ["TARGET"],"read_only":True,"bind":{"create_host_path":False}}]}}}
assert json.load(sys.stdin)==expected,"Pending overlay differs; preserve and review"
print("pending_overlay=verified_unapplied")' < "$overlay"
  mv "$overlay" "$stage/compose.archive.unapplied.yaml"
  changed=1
  # Explicit NAS-local retry resumes the app-update workflow after success only.
  was_enabled=1
fi
compose_base() { docker_local compose --env-file "$root/.env.nas" -p "$project" -f "$root/compose.nas.yaml" -f "$root/compose.import.yaml" -f "$root/compose.pilot.yaml" -f "$root/compose.ui.yaml" "$@"; }
compose_archive() { compose_base -f "$overlay" "$@"; }
step render_base
compose_base config --format json > "$stage/before.json"
docker_local run --rm --pull=never --network none --read-only --cap-drop ALL --env "SOURCE=$source" --env "TARGET=$target" --entrypoint python "$web" -B -c '
import json,os
print(json.dumps({"services":{"lanraragi":{"environment":{"LRR_UID":"0","LRR_GID":"0"},"volumes":[{"type":"bind","source":os.environ["SOURCE"],"target":os.environ["TARGET"],"read_only":True,"bind":{"create_host_path":False}}]}}}))' > "$overlay"
changed=1
chmod 600 "$overlay"
step render_connection
compose_archive config --format json > "$stage/after.json"
# Credential-bearing configs stay NAS-local, private, and are removed after validation.
step verify_scope
(cat "$stage/before.json";cat "$stage/after.json") | docker_local run --rm -i --pull=never --network none --read-only --cap-drop ALL \
  --env "SOURCE=$source" --env "TARGET=$target" --env "WRITER=$writer" --env "WEB=$web" --env "LRR=$lrr" \
  --entrypoint python "$web" -B -c '
import copy,json,os,sys
raw=sys.stdin.read();decoder=json.JSONDecoder();before,pos=decoder.raw_decode(raw.lstrip())
remaining=raw.lstrip()[pos:].lstrip();after,end=decoder.raw_decode(remaining);assert not remaining[end:].strip()
def canonical(c):
 for s in c["services"].values():
  if "volumes" in s:s["volumes"].sort(key=lambda m:m["target"])
 return c
before=canonical(before);after=canonical(after)
assert before["services"]["studio"]["image"]==os.environ["WEB"],"studio_image_differs"
assert before["services"]["studio"]["user"]==os.environ["WRITER"],"studio_user_differs"
old=before["services"]["lanraragi"];new=after["services"]["lanraragi"]
assert old["image"]==os.environ["LRR"],"lrr_image_differs"
uid,gid=os.environ["WRITER"].split(":")
assert old["environment"]["LRR_UID"]==uid and old["environment"]["LRR_GID"]==gid,"lrr_uid_gid_differs"
assert str(old["environment"].get("LRR_AUTOFIX_PERMISSIONS"))=="0","lrr_permission_autofix_not_disabled"
assert str(old["environment"].get("LRR_WORKER_CONCURRENCY"))=="1","lrr_concurrency_not_one"
mount=[m for m in new["volumes"] if m["target"]==os.environ["TARGET"]]
assert len(mount)==1,"source_mount_count_differs"
m=mount[0];assert m["type"]=="bind" and m["source"]==os.environ["SOURCE"] and m["read_only"] and m.get("bind",{}).get("create_host_path",False) is False,"source_mount_not_expected_ro_bind"
expected=copy.deepcopy(before)
expected["services"]["lanraragi"]["environment"].update(LRR_UID="0",LRR_GID="0")
expected["services"]["lanraragi"]["volumes"].append(m)
assert canonical(expected)==after,"Unexpected Compose changes"
print("connection_scope=verified")'
rm -f "$stage/before.json" "$stage/after.json"
stamp=$(date -u +%Y%m%dT%H%M%SZ).$$
step backup_sqlite
docker_local run --rm --pull=never --user "$writer" --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true \
  --mount "type=volume,src=${project}_studio-data,dst=/data,volume-nocopy" --entrypoint python "$web" \
  /app/backup.py backup /data/studio.db "/data/before-archive-connection-$stamp.db" > "$stage/sqlite-backup.json"
studio_started=$(docker_local inspect --format '{{.State.StartedAt}}' "$project-studio-1")
step recreate_lanraragi
compose_archive up -d --no-deps lanraragi
step wait_health
ready=0
for attempt in $(seq 1 60);do
  if [ "$(docker_local inspect --format '{{.State.Health.Status}}' "$project-lanraragi-1")" = healthy ];then ready=1;break;fi
  sleep 2
done
[ "$ready" -eq 1 ] || { printf 'LANraragi health timed out; preserve for local review.\n' >&2;exit 1; }
step verify_runtime
[ "$(docker_local exec "$project-lanraragi-1" s6-setuidgid koyomi id -u)" = 0 ] || exit 1
docker_local exec "$project-lanraragi-1" s6-setuidgid koyomi test -r "$target"
identity=$(docker_local inspect --format "{{range .Mounts}}{{if eq .Destination \"$target\"}}{{.Type}}|{{.Source}}|{{.RW}}{{end}}{{end}}" "$project-lanraragi-1")
[ "$identity" = "bind|$source|false" ] || exit 1
[ "$(docker_local inspect --format '{{.State.StartedAt}}' "$project-studio-1")" = "$studio_started" ] || exit 1
# Explicit local re-review of this extra RO connection only; never adopt unrelated drift.
step freeze_connection
sha256sum -c "$stage/configs.before.sha256" >/dev/null
cp -p "$stage/configs.before.sha256" "$stage/configs.next.sha256"
sha256sum "$overlay" >> "$stage/configs.next.sha256"
mv "$stage/configs.next.sha256" "$control/configs.sha256"
success=1
printf 'connection=healthy\nlrr_reader_uid_gid=0:0\nsource_mount=read_only\nstudio_restarted=false\nnas_conversion=not_performed\n'

