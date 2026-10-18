#!/bin/sh
# One user-authorized NAS action: verify, preserve catalog/backups, unlink app copies.
set -eu
umask 077
mode=${1:-preview};source=${2:-}
[ "$#" -eq 2 ] || exit 2
case "$mode" in preview|apply) ;; *) exit 2;;esac
case "$source" in /volume[0-9]*/*) ;; *) exit 2;;esac
number=${source#/volume};number=${number%%/*};case "$number" in ''|*[!0-9]*) exit 2;;esac
cr=$(printf '\r')
case "$source" in */../*|*/..|*/./*|*/.|*//*|*,*|*'\'*|*'
'*|*"$cr"*) exit 2;;esac
printf 'Apply removes only verified app copies after catalog merge and private backups. Originals remain RO.\n'
printf 'Unmatched/ambiguous copies stay. Original folders, NAS ACL, Stash/NMLO and LRR service remain unchanged.\n'
[ "$mode" = apply ] || { printf 'Preview only: no network, Docker, files or services changed.\n';exit 0; }
[ "$(id -u)" -eq 0 ] || exit 1
[ -d "$source" ] && [ ! -L "$source" ] && [ "$(readlink -f "$source")" = "$source" ] || exit 1
root=/volume1/docker/library-studio
control=/volume1/docker/library-studio-deploy
[ -d "$root" ] && [ ! -L "$root" ] && [ "$(readlink -f "$root")" = "$root" ] || exit 1
[ -d "$control" ] && [ ! -L "$control" ] && [ "$(readlink -f "$control")" = "$control" ] || exit 1
revision=90bf17a6acb3f328b7dbdce5c27a286a73d93e79
manifest_sha=4db7ac71b2837ce7e9a94de8b19b45559c7b197281d50c220b9a190d6b745112
image=sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0
docker_local() { (unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH;docker --host=unix:///var/run/docker.sock "$@"); }
marker=$root/.copy-cleanup-maintenance
if [ -e "$marker" ] || [ -L "$marker" ];then
  [ -f "$marker" ] && [ ! -L "$marker" ] && [ "$(stat -c '%u:%a' "$marker")" = '0:600' ] || exit 1
  owner=$(cat "$marker");case "$owner" in ''|*[!0-9]*) exit 1;;esac
  if kill -0 "$owner" 2>/dev/null;then printf 'Cleanup owner still active; preserved.\n' >&2;exit 75;fi
  if docker_local inspect library-studio-copy-executor >/dev/null 2>&1;then printf 'Cleanup executor still present; preserved.\n' >&2;exit 75;fi
  identity=$(docker_local inspect --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.Image}}' library-studio-nas-pilot-studio-1)
  [ "$identity" = "library-studio-nas-pilot|studio|$image" ] || exit 1
  for lock in "$control/poll.lock" "$root/.studio-ui-update.lock";do
    if [ -d "$lock" ];then [ ! -L "$lock" ] && [ "$(cat "$lock/pid")" = "$owner" ] || exit 1;rm -f "$lock/pid";rmdir "$lock";fi
  done
  docker_local start library-studio-nas-pilot-studio-1 >/dev/null
  rm -f "$marker"
fi
(cd "$control" && sha256sum -c controller.sha256 configs.sha256)
printf 'cleanup_stage=ensure_alias_runtime\n'
current_mount=$(docker_local inspect --format '{{range .Mounts}}{{if eq .Destination "/app"}}{{.Source}}|{{.Type}}|{{.RW}}{{end}}{{end}}' library-studio-nas-pilot-studio-1)
current_hash=
case "$current_mount" in "$root/studio-runtime."*"|bind|false")
  current_code=${current_mount%%|*}
  if [ -f "$current_code/runtime-manifest.sha256" ] && [ ! -L "$current_code" ] && [ "$(readlink -f "$current_code")" = "$current_code" ];then
    current_hash=$(sha256sum "$current_code/runtime-manifest.sha256");current_hash=${current_hash%% *}
  fi;;
esac
if [ "$current_hash" != "$manifest_sha" ];then
  # Explicit one-time local apply; never enable/disable or replace the controller.
  sh "$control/update-studio-ui.sh" apply-release "$root" "$revision" "$manifest_sha"
fi
runtime_mount=$(docker_local inspect --format '{{range .Mounts}}{{if eq .Destination "/app"}}{{.Source}}|{{.Type}}|{{.RW}}{{end}}{{end}}' library-studio-nas-pilot-studio-1)
case "$runtime_mount" in "$root/studio-runtime."*"|bind|false") runtime=${runtime_mount%%|*};; *) exit 1;;esac
[ -d "$runtime" ] && [ ! -L "$runtime" ] && [ "$(readlink -f "$runtime")" = "$runtime" ] || exit 1
actual=$(sha256sum "$runtime/runtime-manifest.sha256");actual=${actual%% *}
[ "$actual" = "$manifest_sha" ] || { printf 'Required alias-aware app update is not active; no cleanup performed.\n' >&2;exit 1; }
identity=$(docker_local inspect --type container --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.Image}}' library-studio-nas-pilot-studio-1)
[ "$identity" = "library-studio-nas-pilot|studio|$image" ] || exit 1
writer=$(docker_local inspect --format '{{.Config.User}}' library-studio-nas-pilot-studio-1)
case "$writer" in *:*) uid=${writer%:*};gid=${writer#*:};; *) exit 1;;esac
for value in "$uid" "$gid";do case "$value" in ''|*[!0-9]*) exit 1;;esac;[ "$value" -gt 0 ] && [ "$value" -le 2147483647 ] || exit 1;done
for tuple in 'studio-data /data' 'studio-uploads /uploads';do
  set -- $tuple
  mount=$(docker_local inspect --format "{{range .Mounts}}{{if eq .Destination \"$2\"}}{{.Name}}|{{.Type}}|{{.RW}}{{end}}{{end}}" library-studio-nas-pilot-studio-1)
  [ "$mount" = "library-studio-nas-pilot_$1|volume|true" ] || exit 1
done
mount=$(docker_local inspect --format '{{range .Mounts}}{{if eq .Destination "/home/koyomi/lanraragi/content/NASOriginals"}}{{.Source}}|{{.Type}}|{{.RW}}{{end}}{{end}}' library-studio-nas-pilot-lanraragi-1)
[ "$mount" = "$source|bind|false" ] || exit 1
poll_lock=$control/poll.lock;ui_lock=$root/.studio-ui-update.lock
mkdir "$poll_lock" || exit 75
printf '%s\n' "$$" > "$poll_lock/pid"
if ! mkdir "$ui_lock";then rm -f "$poll_lock/pid";rmdir "$poll_lock";exit 75;fi
printf '%s\n' "$$" > "$ui_lock/pid"
stopped=0
cleanup() { result=$?;trap - EXIT
  if [ "$stopped" -eq 1 ];then
    if docker_local start library-studio-nas-pilot-studio-1 >/dev/null;then rm -f "$marker";else printf 'Studio restart needs local recovery; backups/journal preserved.\n' >&2;fi
  fi
  rm -f "$ui_lock/pid" "$poll_lock/pid";rmdir "$ui_lock" "$poll_lock";exit "$result"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
actual=$(sha256sum "$runtime/runtime-manifest.sha256");actual=${actual%% *}
[ "$actual" = "$manifest_sha" ] || exit 1
(cd "$runtime" && sha256sum -c runtime-manifest.sha256)
stage=$(mktemp -d /tmp/library-studio-copy-apply.XXXXXX)
mkdir "$stage/web" "$stage/deploy"
base=https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio
curl -fsSL --connect-timeout 15 --max-time 60 "$base/deploy/runtime-manifest.sha256" -o "$stage/runtime-manifest.sha256"
printf '%s  %s\n' "$manifest_sha" "$stage/runtime-manifest.sha256" | sha256sum -c -
while read -r digest relative;do
  printf '%s\n' "$digest" | LC_ALL=C grep -Eq '^[0-9a-f]{64}$' || exit 1
  case "$relative" in web/app.js|web/index.html|web/style.css) ;; *.py) case "$relative" in */*|*..*|*[!A-Za-z0-9_.]*) exit 1;;esac;; *) exit 1;;esac
  curl -fsSL --connect-timeout 15 --max-time 60 "$base/$relative" -o "$stage/$relative"
done < "$stage/runtime-manifest.sha256"
(cd "$stage" && sha256sum -c runtime-manifest.sha256)
for relative in execute-copy-cleanup.py plan-copy-cleanup.py review-library-storage.py archive_in_place.py;do
  curl -fsSL --connect-timeout 15 --max-time 60 "$base/deploy/$relative" -o "$stage/deploy/$relative"
done
cat > "$stage/deploy-checksums" <<'HASHES'
4411ad593b05b62a364b85588db13b97ff0da99631bcfa3437e73015ef547433  deploy/execute-copy-cleanup.py
e06081fc58e4501a926eb24beee077469aaf05d7952da4c8a37468c2633c890f  deploy/plan-copy-cleanup.py
767bf44e82fe39d27b242e0f1eab99727ec3c57b438cbdba0c2a116d24d5e155  deploy/review-library-storage.py
18ec6094fb0bae2840ae351c3e6dbfb1b46944dc121e9c1c56d7c80f58e4f304  deploy/archive_in_place.py
HASHES
(cd "$stage" && sha256sum -c deploy-checksums)
reports=$root/review-reports
[ -d "$reports" ] && [ ! -L "$reports" ] && [ "$(stat -c '%u:%a' "$reports")" = '0:700' ] || exit 1
workspace=$reports/cleanup-execution
[ -d "$workspace" ] || mkdir -m 700 "$workspace"
[ ! -L "$workspace" ] && [ "$(stat -c '%u:%a' "$workspace")" = '0:700' ] || exit 1
stamp=run-$(date -u +%Y%m%dT%H%M%SZ)-$$
run_executor() {
  docker_local run --rm --pull=never --name library-studio-copy-executor --label studio.copy-cleanup=1 --user 0:0 --network none --read-only --memory 256m \
    --cap-drop ALL --cap-add DAC_OVERRIDE --cap-add SETUID --cap-add SETGID --security-opt no-new-privileges:true \
    --mount "type=bind,src=$source,dst=/nas-library,readonly" \
    --mount 'type=volume,src=library-studio-nas-pilot_studio-uploads,dst=/copies' \
    --mount 'type=volume,src=library-studio-nas-pilot_studio-data,dst=/data' \
    --mount "type=bind,src=$stage,dst=/tools,readonly" \
    --mount "type=bind,src=$reports,dst=/prior-reports,readonly" \
    --mount "type=bind,src=$workspace,dst=/reports" \
    --entrypoint python "$image" -B /tools/deploy/execute-copy-cleanup.py "$1" \
    --database /data/studio.db --library-root /nas-library --copies-root /copies --workspace /reports \
    --manifest "/reports/$stamp.json" --prior-report latest --proof "/reports/$stamp.proof.json" --writer-uid "$uid" --writer-gid "$gid"
}
printf 'cleanup_stage=refresh_catalog\n'
docker_local exec library-studio-nas-pilot-studio-1 python -B -c '
import os,json
from server import Studio,LRR
from store import Store
app=Studio(Store(os.environ["STUDIO_DATABASE"]),LRR(os.environ["LRR_URL"],os.environ["LRR_API_KEY"]))
print(json.dumps({"cleanup_catalog_synced":app.sync()["synced"]}))'
printf 'cleanup_stage=prepare_verified_execution\n'
run_executor prepare
printf 'cleanup_stage=verify_backend_downloads\n'
(set -C;cat "$workspace/$stamp.request.json" | docker_local exec -i library-studio-nas-pilot-studio-1 python -B -c '
import os,json,sys
from server import LRR,verify_cleanup_downloads
print(json.dumps(verify_cleanup_downloads(LRR(os.environ["LRR_URL"],os.environ["LRR_API_KEY"]),json.load(sys.stdin))))' > "$workspace/$stamp.proof.json")
printf 'cleanup_stage=brief_studio_maintenance\n'
docker_local exec library-studio-nas-pilot-studio-1 python -B -c '
import os
from store import Store
s=Store(os.environ["STUDIO_DATABASE"])
with s.db() as db:
 assert db.execute("SELECT count(*) FROM jobs WHERE state IN (\"queued\",\"running\")").fetchone()[0]==0,"active_downloads_preserved"
 assert db.execute("SELECT count(*) FROM folder_jobs WHERE state IN (\"queued\",\"running\")").fetchone()[0]==0,"active_folder_jobs_preserved"'
(set -C;printf '%s\n' "$$" > "$marker")
stopped=1
docker_local stop --time 30 library-studio-nas-pilot-studio-1 >/dev/null
printf 'cleanup_stage=merge_backup_and_delete_copies\n'
run_executor apply
printf 'cleanup_stage=restart_studio\n'
docker_local start library-studio-nas-pilot-studio-1 >/dev/null
stopped=0;rm -f "$marker"
ready=0
for attempt in $(seq 1 45);do
  if [ "$(docker_local inspect --format '{{.State.Health.Status}}' library-studio-nas-pilot-studio-1)" = healthy ];then ready=1;break;fi
  sleep 1
done
[ "$ready" -eq 1 ] || { printf 'Studio health not ready; files/backups/journal preserved.\n' >&2;exit 1; }
printf 'cleanup_stage=verify_app_catalog\n'
docker_local exec library-studio-nas-pilot-studio-1 python -B -c '
import os,json
from store import Store
s=Store(os.environ["STUDIO_DATABASE"]);s.list_works()
print(json.dumps({"studio_catalog_accessible":True}))'
printf 'cleanup=complete; verified app copies removed; unmatched copies and originals retained; private rollback backups retained.\n'
