#!/bin/sh
# Existing pilot only: update code, retain images/volumes/secrets.
set -eu
umask 077
mode=${1:-plan}
root=${2:-/volume1/docker/library-studio}
case "$mode" in plan|apply|rollback) ;; *) printf 'Use: update-studio-ui.sh plan|apply|rollback /volumeN/docker/library-studio\n' >&2;exit 2;;esac
case "$root" in /volume*/docker/library-studio) ;; *) printf 'Refusing unrelated app root\n' >&2;exit 2;;esac
volume=${root%/docker/library-studio};number=${volume#/volume}
case "$number" in ''|*[!0-9]*) printf 'Invalid volume root\n' >&2;exit 2;;esac
project=library-studio-nas-pilot
image=sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0
revision=4daad4703a9ba0164f5c94149fb0310fc5337d7f
manifest_sha=e1a6b52df282fc2de2cd32494e2f8825deda913b9aeed5fe83790b7322a7dcf8
printf 'Project: %s; update only Studio code with original image and existing volumes.\n' "$project"
printf 'Apply: verify public code, back up SQLite, mount code read-only, recreate only Studio.\n'
printf 'Preserves media, LANraragi, Stash/NMLO, secrets and loopback access.\n'
[ "$mode" != plan ] || { printf 'Plan only: no files, Docker calls or NAS changes.\n';exit 0; }
[ "$(id -u)" -eq 0 ] || { printf 'Use sudo for apply/rollback.\n' >&2;exit 1; }
[ -d "$root" ] && [ ! -L "$root" ] && [ "$(readlink -f "$root")" = "$root" ] || { printf 'Verify canonical existing app root first.\n' >&2;exit 1; }
for file in compose.nas.yaml compose.import.yaml compose.pilot.yaml .env.nas;do
  [ -f "$root/$file" ] && [ ! -L "$root/$file" ] || { printf 'Missing/unsafe pilot config: %s\n' "$file" >&2;exit 1; }
done
docker_local() { (unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH; docker --host=unix:///var/run/docker.sock "$@"); }
compose_base() { docker_local compose --env-file "$root/.env.nas" -p "$project" -f "$root/compose.nas.yaml" -f "$root/compose.import.yaml" -f "$root/compose.pilot.yaml" "$@"; }
compose_new() { docker_local compose --env-file "$root/.env.nas" -p "$project" -f "$root/compose.nas.yaml" -f "$root/compose.import.yaml" -f "$root/compose.pilot.yaml" -f "$root/compose.ui.yaml" "$@"; }
verify_compose() {
# Credential-bearing Compose JSON stays in this NAS-local pipe, never in logs.
docker_local run --rm -i --pull=never --network none --read-only --cap-drop ALL \
  --env "EXPECTED_CODE=$1" --env "EXPECTED_USER=$writer" --env "EXPECTED_IMAGE=$image" --entrypoint python "$image" -c '
import json,os,sys
c=json.load(sys.stdin);s=c["services"]["studio"]
assert s["image"]==os.environ["EXPECTED_IMAGE"] and s["user"]==os.environ["EXPECTED_USER"]
p=s["ports"];assert len(p)==1 and p[0]["host_ip"]=="127.0.0.1" and str(p[0]["published"])=="43120" and p[0]["target"]==8090
m={v["target"]:v for v in s["volumes"]};assert m["/app"]["type"]=="bind" and m["/app"]["source"]==os.environ["EXPECTED_CODE"] and m["/app"]["read_only"]
for target,key in [("/data","studio-data"),("/uploads","studio-uploads")]:
 v=m[target];assert v["type"]=="volume" and c["volumes"][v["source"]]["name"]=="library-studio-nas-pilot_"+key
 assert not v.get("read_only",False)
print("compose_scope=verified")'
}
reviewed_overlay() {
  [ -f "$1" ] && [ ! -L "$1" ] && grep -Eq '^# library-studio-reviewed-ui [0-9a-f]{40}$' "$1"
}
previous_file=
compose_previous() {
  if [ -n "$previous_file" ];then
    docker_local compose --env-file "$root/.env.nas" -p "$project" -f "$root/compose.nas.yaml" -f "$root/compose.import.yaml" -f "$root/compose.pilot.yaml" -f "$previous_file" "$@"
  else compose_base "$@";fi
}
writer=$(docker_local inspect --type container --format '{{.Config.User}}' "$project-studio-1")
case "$writer" in *:*) uid=${writer%:*};gid=${writer#*:};; *) printf 'Expected numeric app UID:GID\n' >&2;exit 1;;esac
for value in "$uid" "$gid";do
  case "$value" in ''|*[!0-9]*) exit 1;;esac
  [ "$value" -gt 0 ] && [ "$value" -le 2147483647 ] || exit 1
done
identity=$(docker_local inspect --type container --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.Image}}' "$project-studio-1")
[ "$identity" = "$project|studio|$image" ] || { printf 'Existing Studio identity differs; stop.\n' >&2;exit 1; }
overlay=$root/compose.ui.yaml
if [ "$mode" = rollback ];then
  reviewed_overlay "$overlay" || { printf 'No reviewed UI overlay to roll back.\n' >&2;exit 1; }
  relative=$(sed -n 's/^# previous-ui-overlay //p' "$overlay")
  if [ -n "$relative" ];then
    name=${relative%/compose.ui.previous.yaml}
    case "$name" in ui-update-backup.*) ;; *) printf 'Invalid prior overlay record\n' >&2;exit 1;;esac
    case "$name" in *[!A-Za-z0-9._-]*) exit 1;;esac
    [ "$relative" = "$name/compose.ui.previous.yaml" ] || exit 1
    previous_file=$root/$relative
    [ "$(readlink -f "$previous_file")" = "$previous_file" ] && reviewed_overlay "$previous_file" || { printf 'Prior reviewed overlay unavailable\n' >&2;exit 1; }
  fi
  compose_previous config --quiet
  compose_previous up -d --no-deps studio
  mv "$overlay" "$root/compose.ui.rolled-back.$(date -u +%Y%m%dT%H%M%SZ).$$.yaml"
  if [ -n "$previous_file" ];then cp -p "$previous_file" "$overlay";fi
  printf 'Studio code rolled back one version; volumes, DB and runtime source preserved.\n'
  exit 0
fi
health=$(docker_local inspect --format '{{.State.Health.Status}}' "$project-studio-1")
[ "$health" = healthy ] || { printf 'Existing Studio must be healthy before update.\n' >&2;exit 1; }
app_mount=$(docker_local inspect --format '{{range .Mounts}}{{if eq .Destination "/app"}}{{.Type}}|{{.Source}}|{{.RW}}{{end}}{{end}}' "$project-studio-1")
if [ -e "$overlay" ] || [ -L "$overlay" ];then
  reviewed_overlay "$overlay" || { printf 'Unrecognized UI overlay; stop.\n' >&2;exit 1; }
  case "$app_mount" in "bind|$root/studio-runtime."*"|false") ;; *) printf 'Existing reviewed code mount differs; stop.\n' >&2;exit 1;;esac
  app_source=${app_mount#bind|};app_source=${app_source%|false}
  [ -d "$app_source" ] && [ ! -L "$app_source" ] && [ "$(readlink -f "$app_source")" = "$app_source" ] || exit 1
  compose_new config --format json | verify_compose "$app_source"
else
  [ -z "$app_mount" ] || { printf 'Unexpected existing app code mount; stop.\n' >&2;exit 1; }
fi
for logical in studio-data studio-uploads;do
  found=$(docker_local volume inspect --format '{{.Driver}}|{{index .Labels "com.docker.compose.project"}}|{{index .Labels "com.docker.compose.volume"}}' "${project}_$logical")
  [ "$found" = "local|$project|$logical" ] || { printf 'Dedicated volume identity differs.\n' >&2;exit 1; }
done
for pair in '/data:studio-data' '/uploads:studio-uploads';do
  target=${pair%:*};logical=${pair#*:}
  found=$(docker_local inspect --format "{{range .Mounts}}{{if eq .Destination \"$target\"}}{{.Name}}|{{.Type}}|{{.RW}}{{end}}{{end}}" "$project-studio-1")
  [ "$found" = "${project}_$logical|volume|true" ] || { printf 'Existing output mount differs.\n' >&2;exit 1; }
done
code=$(mktemp -d "$root/studio-runtime.XXXXXX")
chmod 755 "$code"
mkdir "$code/web";chmod 755 "$code/web"
curl -fsSL --connect-timeout 15 --max-time 60 "https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio/deploy/runtime-manifest.sha256" -o "$code/runtime-manifest.sha256"
printf '%s  %s\n' "$manifest_sha" "$code/runtime-manifest.sha256" | sha256sum -c -
while read -r digest relative;do
  [ "${#digest}" -eq 64 ] || exit 1
  case "$digest" in *[!0-9a-f]*) exit 1;;esac
  case "$relative" in web/index.html|web/app.js|web/style.css) ;;
    *.py) case "$relative" in */*|*..*|*[!A-Za-z0-9_.]*) exit 1;;esac;;
    *) printf 'Unexpected runtime manifest path\n' >&2;exit 1;;
  esac
  curl -fsSL --connect-timeout 15 --max-time 60 "https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio/$relative" -o "$code/$relative"
  chmod 644 "$code/$relative"
done < "$code/runtime-manifest.sha256"
(cd "$code" && sha256sum -c runtime-manifest.sha256)
docker_local run --rm --pull=never --user "$writer" --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true \
  --mount "type=bind,src=$code,dst=/app,readonly" --entrypoint python "$image" -B -c 'import server,store,folder_importer;assert hasattr(folder_importer,"root_batch_import");print("runtime_import=ok")'
stamp=$(date -u +%Y%m%dT%H%M%SZ).$$
backup=$root/ui-update-backup.$stamp
mkdir "$backup";chmod 700 "$backup"
cp -p "$root/compose.nas.yaml" "$root/compose.import.yaml" "$root/compose.pilot.yaml" "$backup/"
if [ -f "$overlay" ];then previous_file=$backup/compose.ui.previous.yaml;cp -p "$overlay" "$previous_file";fi
docker_local run --rm --pull=never --user "$writer" --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true \
  --mount "type=volume,src=${project}_studio-data,dst=/data,volume-nocopy" --entrypoint python "$image" /app/backup.py backup /data/studio.db "/data/before-ui-$stamp.db" > "$backup/sqlite-backup.json"
printf '# library-studio-reviewed-ui %s\n# previous-ui-overlay %s\nservices:\n  studio:\n    volumes:\n      - type: bind\n        source: %s\n        target: /app\n        read_only: true\n        bind: {create_host_path: false}\n' "$revision" "${previous_file#"$root"/}" "$code" > "$overlay"
chmod 644 "$overlay"
changed=0
rollback_on_error() {
  result=$?
  trap - EXIT
  if [ "$result" -ne 0 ];then
    printf 'UI update failed; preserving files and restoring the previous Studio code when needed.\n' >&2
    if [ "$changed" -eq 1 ];then compose_previous up -d --no-deps studio || true;fi
    mv "$overlay" "$backup/compose.ui.failed.yaml"
    if [ -n "$previous_file" ];then cp -p "$previous_file" "$overlay";fi
  fi
  exit "$result"
}
trap rollback_on_error EXIT
compose_new config --format json | verify_compose "$code"
changed=1
compose_new up -d --no-deps studio
ready=0
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20;do
  health=$(docker_local inspect --format '{{.State.Health.Status}}' "$project-studio-1")
  if [ "$health" = healthy ];then ready=1;break;fi
  sleep 2
done
[ "$ready" -eq 1 ] || { printf 'Updated Studio health check timed out.\n' >&2;exit 1; }
docker_local exec "$project-studio-1" python -c '
import base64,json,os,urllib.request
auth=base64.b64encode(("admin:"+os.environ["STUDIO_PASSWORD"]).encode()).decode()
req=urllib.request.Request("http://127.0.0.1:8090/api/library/status",headers={"Authorization":"Basic "+auth})
with urllib.request.urlopen(req,timeout=10) as response:status=json.load(response)
print(json.dumps({"studio_update":"complete","folder_archives":status["folder_archives"],"thumbnail_blur":"10px","cover_fit":"contain","detail_reader":"original","site_downloads":"not-verified"}))'
trap - EXIT
printf 'UI updated. Refresh the browser; this script rollback mode restores the previous code and preserves DB/uploads.\n'
