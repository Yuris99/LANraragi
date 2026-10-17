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
revision=90a3d73b8d6c45f6b16af9cf2c89cdd69f728c8c
manifest_sha=466c08aaac6edffc03d08c3c9a752a965ec7f8a1da16cdb2aea307ce2cb59bde
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
  [ -f "$overlay" ] && [ ! -L "$overlay" ] && grep -q '^# library-studio-reviewed-ui ' "$overlay" || { printf 'No reviewed UI overlay to roll back.\n' >&2;exit 1; }
  compose_base config --quiet
  compose_base up -d --no-deps studio
  mv "$overlay" "$root/compose.ui.rolled-back.$(date -u +%Y%m%dT%H%M%SZ).$$.yaml"
  printf 'Studio code rolled back; volumes, DB and runtime source preserved.\n'
  exit 0
fi
[ ! -e "$overlay" ] && [ ! -L "$overlay" ] || { printf 'UI overlay exists; inspect/rollback before another update.\n' >&2;exit 1; }
health=$(docker_local inspect --format '{{.State.Health.Status}}' "$project-studio-1")
[ "$health" = healthy ] || { printf 'Existing Studio must be healthy before update.\n' >&2;exit 1; }
app_mount=$(docker_local inspect --format '{{range .Mounts}}{{if eq .Destination "/app"}}{{.Type}}{{end}}{{end}}' "$project-studio-1")
[ -z "$app_mount" ] || { printf 'Unexpected existing app code mount; stop.\n' >&2;exit 1; }
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
docker_local run --rm --pull=never --user "$writer" --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true \
  --mount "type=volume,src=${project}_studio-data,dst=/data,volume-nocopy" --entrypoint python "$image" /app/backup.py backup /data/studio.db "/data/before-ui-$stamp.db" > "$backup/sqlite-backup.json"
printf '# library-studio-reviewed-ui %s\nservices:\n  studio:\n    volumes:\n      - type: bind\n        source: %s\n        target: /app\n        read_only: true\n        bind: {create_host_path: false}\n' "$revision" "$code" > "$overlay"
chmod 644 "$overlay"
changed=0
rollback_on_error() {
  result=$?
  trap - EXIT
  if [ "$result" -ne 0 ];then
    printf 'UI update failed; preserving files and restoring original Studio code when needed.\n' >&2
    if [ "$changed" -eq 1 ];then compose_base up -d --no-deps studio || true;fi
    mv "$overlay" "$backup/compose.ui.failed.yaml"
  fi
  exit "$result"
}
trap rollback_on_error EXIT
# Credential-bearing Compose JSON stays in this NAS-local pipe, never in logs.
compose_new config --format json | docker_local run --rm -i --pull=never --network none --read-only --cap-drop ALL \
  --env "EXPECTED_CODE=$code" --env "EXPECTED_USER=$writer" --env "EXPECTED_IMAGE=$image" --entrypoint python "$image" -c '
import json,os,sys
c=json.load(sys.stdin);s=c["services"]["studio"]
assert s["image"]==os.environ["EXPECTED_IMAGE"] and s["user"]==os.environ["EXPECTED_USER"]
p=s["ports"];assert len(p)==1 and p[0]["host_ip"]=="127.0.0.1" and str(p[0]["published"])=="43120" and p[0]["target"]==8090
m={v["target"]:v for v in s["volumes"]};assert m["/app"]["type"]=="bind" and m["/app"]["source"]==os.environ["EXPECTED_CODE"] and m["/app"]["read_only"]
for target,key in [("/data","studio-data"),("/uploads","studio-uploads")]:
 v=m[target];assert v["type"]=="volume" and c["volumes"][v["source"]]["name"]=="library-studio-nas-pilot_"+key
 assert not v.get("read_only",False)
print("compose_scope=verified")'
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
print(json.dumps({"studio_update":"complete","folder_archives":status["folder_archives"],"mosaic":"thumbnail-only-48-columns","detail_reader":"original","site_downloads":"not-verified"}))'
trap - EXIT
printf 'UI updated. Refresh the browser; this script rollback mode restores original code and preserves DB/uploads.\n'
