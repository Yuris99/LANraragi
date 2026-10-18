#!/bin/sh
# Fixed NAS-local catalog preservation planning; never deletes/moves media.
set -eu
umask 077
mode=${1:-preview}
source=${2:-}
[ "$#" -eq 2 ] || exit 2
case "$mode" in preview|plan) ;; *) exit 2;;esac
case "$source" in /volume[0-9]*/*) ;; *) exit 2;;esac
number=${source#/volume};number=${number%%/*}
case "$number" in ''|*[!0-9]*) exit 2;;esac
cr=$(printf '\r')
case "$source" in */../*|*/..|*/./*|*/.|*//*|*,*|*'\'*|*'
'*|*"$cr"*) exit 2;;esac
printf 'Catalog-aware plan; candidate files, catalog and prior reports RO, network none.\n'
printf 'Only a new private local report; no media/DB deletion, rename, service restart or ACL change.\n'
[ "$mode" = plan ] || { printf 'Preview only; no network, Docker or filesystem changes.\n';exit 0; }
[ "$(id -u)" -eq 0 ] || { printf 'NAS-local sudo is needed to read both RO inputs.\n' >&2;exit 1; }
[ -d "$source" ] && [ ! -L "$source" ] && [ "$(readlink -f "$source")" = "$source" ] || exit 1
root=/volume1/docker/library-studio
[ -d "$root" ] && [ ! -L "$root" ] && [ "$(readlink -f "$root")" = "$root" ] || exit 1
revision=70885d7f338bd28ee29cded57a4ff38521ef9e0f
image=sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0
docker_local() { (unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH;docker --host=unix:///var/run/docker.sock "$@"); }
identity=$(docker_local inspect --type container --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.Image}}' library-studio-nas-pilot-studio-1)
[ "$identity" = "library-studio-nas-pilot|studio|$image" ] || exit 1
mount=$(docker_local inspect --format '{{range .Mounts}}{{if eq .Destination "/uploads"}}{{.Name}}|{{.Type}}{{end}}{{end}}' library-studio-nas-pilot-studio-1)
[ "$mount" = 'library-studio-nas-pilot_studio-uploads|volume' ] || exit 1
mount=$(docker_local inspect --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}|{{.Type}}{{end}}{{end}}' library-studio-nas-pilot-studio-1)
[ "$mount" = 'library-studio-nas-pilot_studio-data|volume' ] || exit 1
reports=$root/review-reports
[ -d "$reports" ] && [ ! -L "$reports" ] && [ "$(stat -c '%u:%a' "$reports")" = '0:700' ] || exit 1
stage=$(mktemp -d /tmp/library-studio-copy-plan.XXXXXX)
trap 'rm -f "$stage/deploy/plan-copy-cleanup.py" "$stage/deploy/review-library-storage.py" "$stage/deploy/archive_in_place.py" "$stage/sources.py" "$stage/checksums";rmdir "$stage/deploy" "$stage"' EXIT
mkdir "$stage/deploy"
base=https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio
for relative in deploy/plan-copy-cleanup.py deploy/review-library-storage.py deploy/archive_in_place.py sources.py;do
  curl -fsSL --connect-timeout 15 --max-time 60 "$base/$relative" -o "$stage/$relative"
done
cat > "$stage/checksums" <<'HASHES'
eb9e69601454b00dd46526432a645db0e2d13e856e857ef86f84bac64306db36  deploy/plan-copy-cleanup.py
767bf44e82fe39d27b242e0f1eab99727ec3c57b438cbdba0c2a116d24d5e155  deploy/review-library-storage.py
18ec6094fb0bae2840ae351c3e6dbfb1b46944dc121e9c1c56d7c80f58e4f304  deploy/archive_in_place.py
17cf1e2e8bbf06dbc3695d1a8f61f242a10aa40762018a93530fdb55f7d007ed  sources.py
HASHES
(cd "$stage" && sha256sum -c checksums)
plans=$reports/cleanup-plans
[ -d "$plans" ] || mkdir -m 700 "$plans"
[ ! -L "$plans" ] && [ "$(stat -c '%u:%a' "$plans")" = '0:700' ] || exit 1
report=cleanup-plan-$(date -u +%Y%m%dT%H%M%SZ)-$$.json
printf 'Rechecking only reported candidates and reading local catalog; no full library rescan.\n'
docker_local run --rm --pull=never --user 0:0 --network none --read-only --memory 256m \
  --cap-drop ALL --cap-add DAC_OVERRIDE --security-opt no-new-privileges:true \
  --mount "type=bind,src=$source,dst=/nas-library,readonly" \
  --mount 'type=volume,src=library-studio-nas-pilot_studio-uploads,dst=/copies,readonly' \
  --mount "type=bind,src=$stage,dst=/tools,readonly" \
  --mount "type=bind,src=$reports,dst=/prior-reports,readonly" \
  --mount 'type=volume,src=library-studio-nas-pilot_studio-data,dst=/catalog,readonly' \
  --mount "type=bind,src=$plans,dst=/reports" \
  --entrypoint python "$image" -B /tools/deploy/plan-copy-cleanup.py \
  --prior-report latest --database /catalog/studio.db \
  --library-root /nas-library --copies-root /copies --output "/reports/$report"
printf 'Private plan saved under own app review-reports/cleanup-plans; paste only the summary.\n'
