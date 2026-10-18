#!/bin/sh
# Explicit operator action, not part of the app-only automatic deployment channel.
set -eu
umask 077
mode=${1:-preview};source=${2:-};root=${3:-};project=${4:-}
[ "$#" -eq 4 ] || exit 2
case "$root" in /volume[0-9]*/docker/*) ;; *) exit 2;;esac
case "$root" in */../*|*/..|*/./*|*/.|*//*|*,*|*'\'*|*'
'*) exit 2;;esac
case "$project" in ''|*[!a-z0-9_-]*|[_-]*) exit 2;;esac
[ "${#project}" -le 63 ] || exit 2
case "$mode" in preview|apply|rollback) ;; *) exit 2;;esac
case "$source" in /volume[0-9]*/*) ;; *) exit 2;;esac
number=${source#/volume};number=${number%%/*};case "$number" in ''|*[!0-9]*) exit 2;;esac
cr=$(printf '\r')
case "$root" in *"$cr"*) exit 2;;esac
case "$source" in */../*|*/..|*/./*|*/.|*//*|*,*|*'\'*|*'
'*|*"$cr"*) exit 2;;esac
printf 'Same-folder CBZ names only; collection boundaries, bytes, ownership and ACL remain unchanged.\n'
printf 'Apply registers empty filename artists first; unknown artists and ambiguous files are held.\n'
printf 'The temporary isolated helper needs the approved source RW for rename only; long-running mounts stay RO.\n'
[ "$mode" != preview ] || { printf 'Preview only: no network, Docker, files or services changed.\n';exit 0; }
[ "$(id -u)" -eq 0 ] || exit 1
[ -d "$source" ] && [ ! -L "$source" ] && [ "$(readlink -f "$source")" = "$source" ] || exit 1
control=$root-deploy
for path in "$root" "$control";do [ -d "$path" ] && [ ! -L "$path" ] && [ "$(readlink -f "$path")" = "$path" ] || exit 1;done
revision=a38708ca59e1497a1e092a9714890cd84e477c38
manifest_sha=0e7bafa0b7c5118a19106628f24e7b54f868ca84ec2d39509cd857f6e6a9be05
helper_sha=e30a92beadf64d0b1be6633d44d3afca3082584ee8d8ff82449a014479f21522
sources_sha=eda5f8d87d7e9310619baf97ea71527078195f9c268fe102cb9025ebae62306f
image=sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0
studio=$project-studio-1
executor=$project-name-executor
lrr=$project-lanraragi-1
docker_local() { (unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH;docker --host=unix:///var/run/docker.sock "$@"); }
identity=$(docker_local inspect --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.Image}}' "$studio")
[ "$identity" = "$project|studio|$image" ] || exit 1
identity=$(docker_local inspect --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.Image}}' "$lrr")
[ "$identity" = "$project|lanraragi|sha256:b76c792a43846f0755d0dadf98c8dd46123e8d244045e2f9b6834d9b45988957" ] || exit 1
mount=$(docker_local inspect --format '{{range .Mounts}}{{if eq .Destination "/home/koyomi/lanraragi/content/NASOriginals"}}{{.Source}}|{{.Type}}|{{.RW}}{{end}}{{end}}' "$lrr")
[ "$mount" = "$source|bind|false" ] || exit 1
mount=$(docker_local inspect --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}|{{.Type}}|{{.RW}}{{end}}{{end}}' "$studio")
[ "$mount" = "${project}_studio-data|volume|true" ] || exit 1
writer=$(docker_local inspect --format '{{.Config.User}}' "$studio")
case "$writer" in *:*) uid=${writer%:*};gid=${writer#*:};; *) exit 1;;esac
for value in "$uid" "$gid";do case "$value" in ''|*[!0-9]*) exit 1;;esac;[ "$value" -gt 0 ] && [ "$value" -le 2147483647 ] || exit 1;done
marker=$root/.name-normalization-maintenance
if [ -e "$marker" ] || [ -L "$marker" ];then
  [ -f "$marker" ] && [ ! -L "$marker" ] && [ "$(stat -c '%u:%a' "$marker")" = '0:600' ] || exit 1
  owner=$(cat "$marker");case "$owner" in ''|*[!0-9]*) exit 1;;esac
  if kill -0 "$owner" 2>/dev/null;then printf 'Normalization owner active; preserved.\n';exit 75;fi
  if docker_local inspect "$executor" >/dev/null 2>&1;then printf 'Normalization executor present; preserved.\n';exit 75;fi
  for lock in "$control/poll.lock" "$root/.studio-ui-update.lock";do
    if [ -d "$lock" ];then [ ! -L "$lock" ] && [ "$(cat "$lock/pid")" = "$owner" ] || exit 1;rm -f "$lock/pid";rmdir "$lock";fi
  done
  docker_local start "$studio" >/dev/null;rm -f "$marker"
fi
(cd "$control" && sha256sum -c controller.sha256 configs.sha256)
current=$(docker_local inspect --format '{{range .Mounts}}{{if eq .Destination "/app"}}{{.Source}}|{{.Type}}|{{.RW}}{{end}}{{end}}' "$studio")
actual=
case "$current" in "$root/studio-runtime."*"|bind|false")
  code=${current%%|*}
  if [ -d "$code" ] && [ ! -L "$code" ] && [ "$(readlink -f "$code")" = "$code" ] && [ -f "$code/runtime-manifest.sha256" ];then
    actual=$(sha256sum "$code/runtime-manifest.sha256");actual=${actual%% *}
  fi;;
esac
if [ "$actual" != "$manifest_sha" ];then
  sh "$control/update-studio-ui.sh" apply-release "$root" "$revision" "$manifest_sha"
fi
current=$(docker_local inspect --format '{{range .Mounts}}{{if eq .Destination "/app"}}{{.Source}}|{{.Type}}|{{.RW}}{{end}}{{end}}' "$studio")
case "$current" in "$root/studio-runtime."*"|bind|false") code=${current%%|*};; *) exit 1;;esac
[ -d "$code" ] && [ ! -L "$code" ] && [ "$(readlink -f "$code")" = "$code" ] || exit 1
actual=$(sha256sum "$code/runtime-manifest.sha256");actual=${actual%% *}
[ "$actual" = "$manifest_sha" ] || exit 1
(cd "$code" && sha256sum -c runtime-manifest.sha256)
poll_lock=$control/poll.lock;ui_lock=$root/.studio-ui-update.lock
mkdir "$poll_lock" || exit 75;printf '%s\n' "$$" > "$poll_lock/pid"
if ! mkdir "$ui_lock";then rm -f "$poll_lock/pid";rmdir "$poll_lock";exit 75;fi
printf '%s\n' "$$" > "$ui_lock/pid"
stopped=0
cleanup() { result=$?;trap - EXIT
  if [ "$stopped" -eq 1 ];then
    if docker_local inspect "$executor" >/dev/null 2>&1;then
      helper_owner=$(docker_local inspect --format '{{index .Config.Labels "studio.name-normalization.owner"}}' "$executor")
      if [ "$helper_owner" != "$$" ] || ! docker_local stop --time 10 "$executor" >/dev/null;then
        printf 'Executor needs local recovery; Studio/marker/locks preserved.\n' >&2;exit 1
      fi
    fi
    if ! docker_local start "$studio" >/dev/null;then printf 'Studio restart requires local recovery; marker/locks preserved.\n' >&2;exit 1;fi
  fi
  rm -f "$marker" "$ui_lock/pid" "$poll_lock/pid";rmdir "$ui_lock" "$poll_lock";exit "$result"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
(set -C;printf '%s\n' "$$" > "$marker")
reports=$root/review-reports
[ -d "$reports" ] && [ ! -L "$reports" ] && [ "$(stat -c '%u:%a' "$reports")" = '0:700' ] || exit 1
workspace=$reports/name-normalization
[ -d "$workspace" ] || mkdir -m 700 "$workspace"
[ ! -L "$workspace" ] && [ "$(stat -c '%u:%a' "$workspace")" = '0:700' ] || exit 1
stage=$(mktemp -d /tmp/library-studio-names.XXXXXX);mkdir "$stage/deploy"
base=https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio
for file in sources.py deploy/normalize-library-names.py;do curl -fsSL --connect-timeout 15 --max-time 60 "$base/$file" -o "$stage/$file";done
printf '%s  %s\n%s  %s\n' "$helper_sha" "$stage/deploy/normalize-library-names.py" "$sources_sha" "$stage/sources.py" | sha256sum -c -
run_tool() {
  suffix=;[ "$1" != prepare ] || suffix=,readonly
  docker_local run --rm --pull=never --name "$executor" --label studio.name-normalization=1 --label "studio.name-normalization.owner=$$" --user 0:0 --network none --read-only --memory 256m \
    --cap-drop ALL --cap-add DAC_OVERRIDE --security-opt no-new-privileges:true \
    --mount "type=bind,src=$source,dst=/nas-library$suffix" \
    --mount "type=bind,src=$stage,dst=/tools,readonly" \
    --mount "type=bind,src=$workspace,dst=/reports" \
    --entrypoint python "$image" -B /tools/deploy/normalize-library-names.py "$1" --root /nas-library --workspace /reports
}
check_jobs() {
  docker_local exec "$studio" python -B -c 'import os;from store import Store
s=Store(os.environ["STUDIO_DATABASE"])
with s.db() as db:
 assert db.execute("SELECT count(*) FROM jobs WHERE state IN (\"queued\",\"running\")").fetchone()[0]==0,"active_downloads"
 assert db.execute("SELECT count(*) FROM folder_jobs WHERE state IN (\"queued\",\"running\")").fetchone()[0]==0,"active_folder_jobs"'
}
export_catalog() {
  docker_local exec "$studio" python -B -c 'import os,json;from store import Store
s=Store(os.environ["STUDIO_DATABASE"]);items=[];page=1
while True:
 r=s.list_works(page=page,limit=120,sort="title",descending=False)
 if r["total"]>10000:raise ValueError("catalog_limit")
 for w in r["items"]:
  items.append({k:w[k] for k in ("id","lrr_id","archive_filename","title","artist","local_number")} | {"sources":[{k:x[k] for k in ("provider","external_id")} for x in w["sources"]]})
 if page*120>=r["total"]:break
 page+=1
print(json.dumps(items,sort_keys=True))'
}
if docker_local inspect "$executor" >/dev/null 2>&1;then printf 'Existing executor preserved; no names changed.\n';exit 75;fi
check_jobs
if [ ! -f "$workspace/plan.json" ];then
  [ "$mode" = apply ] || { printf 'No local rename plan to roll back.\n' >&2;exit 1; }
  printf 'names_stage=backup_and_register_empty_artists\n'
  docker_local exec "$studio" python -B -c 'import os,time,uuid;from pathlib import Path;from backup import copy_database;from store import Store
p=Path(os.environ["STUDIO_DATABASE"]);d=p.parent/"name-normalization-backups";d.mkdir(mode=0o700,exist_ok=True)
assert not d.is_symlink()
copy_database(p,d/(str(time.time_ns())+"-"+uuid.uuid4().hex+".db"))
print("database_backup=created")
from server import Studio,LRR
s=Store(p);Studio(s,LRR(os.environ["LRR_URL"],os.environ["LRR_API_KEY"])).sync()
print(__import__("json").dumps(s.apply_all_filename_artists()))'
  export_catalog > "$workspace/catalog.json"
fi
printf 'names_stage=prepare_current_catalog\n';run_tool prepare
# Batched backend proof uses only fixed own-LRR archive IDs; no public sites.
if [ ! -f "$workspace/proof.json" ];then
  printf 'names_stage=verify_backend_bytes\n'
  cat "$workspace/request.json" | docker_local exec -i "$studio" python -B -c 'import os,json,sys;from server import LRR,verify_cleanup_downloads
r=json.load(sys.stdin);lrr=LRR(os.environ["LRR_URL"],os.environ["LRR_API_KEY"]);proof={"operation_id":r["operation_id"],"verified":{}}
for offset in range(0,len(r["items"]),100):
 p=verify_cleanup_downloads(lrr,{"operation_id":r["operation_id"],"items":r["items"][offset:offset+100]});proof["verified"].update(p["verified"])
print(json.dumps(proof))' > "$workspace/proof.pending"
  mv "$workspace/proof.pending" "$workspace/proof.json"
fi
# Reject stale metadata before the first move, without exposing private names.
if [ ! -f "$workspace/journal.json" ];then
  export_catalog > "$workspace/catalog.current"
  if ! cmp -s "$workspace/catalog.json" "$workspace/catalog.current";then
    mv "$workspace" "$workspace-stale-$(date -u +%Y%m%dT%H%M%SZ)-$$"
    printf 'Catalog changed; no names changed; stale reports retained. Retry the same command.\n' >&2;exit 1
  fi
fi
check_jobs
printf 'names_stage=brief_studio_maintenance\n'
stopped=1;docker_local stop --time 30 "$studio" >/dev/null
printf 'names_stage=%s\n' "$mode";run_tool "$mode"
docker_local start "$studio" >/dev/null;stopped=0
ready=0
for attempt in $(seq 1 45);do
  if [ "$(docker_local inspect --format '{{.State.Health.Status}}' "$studio")" = healthy ];then ready=1;break;fi
  sleep 1
done
[ "$ready" -eq 1 ] || { printf 'Studio not healthy yet; private journal preserved.\n' >&2;exit 1; }
printf 'names_stage=verify_existing_links_and_downloads\n'
cat "$workspace/plan.json" | docker_local exec -e "STUDIO_NORMALIZE_MODE=$mode" -i "$studio" python -B -c 'import os,json,sys,time;from pathlib import Path;from server import Studio,LRR,verify_cleanup_downloads;from store import Store
p=json.load(sys.stdin);l=LRR(os.environ["LRR_URL"],os.environ["LRR_API_KEY"]);s=Store(os.environ["STUDIO_DATABASE"]);app=Studio(s,l)
# Watcher updates run without restarting LANraragi. Both directions preserve ID.
for i in p["items"]:
 found=False
 for attempt in range(90):
  try:
   m=l.json("/api/archives/"+i["lrr_id"]+"/metadata")
   expected=Path(i["old"] if os.environ["STUDIO_NORMALIZE_MODE"]=="rollback" else i["new"]);names={expected.name,expected.stem}
   if m.get("filename") in names:
    verify_cleanup_downloads(l,{"operation_id":p["operation_id"],"items":[{k:i[k] for k in ("lrr_id","sha256","bytes")}]});found=True;break
  except Exception:pass
  time.sleep(1)
 if not found:raise ValueError("backend_reconciliation_pending")
 assert s.get_work(i["work_id"])["lrr_id"]==i["lrr_id"]
app.sync();print(json.dumps({"catalog_and_downloads_verified":len(p["items"])}))'
printf 'names=complete; collections and CBZ bytes preserved; private journal/DB backup retained; unmatched files held.\n'
