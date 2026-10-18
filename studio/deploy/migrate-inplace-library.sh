#!/bin/sh
# One-time explicit migration. Plan is default; apply connects LRR then converts
# in place and removes ONLY source folders whose published CBZ fully verifies.
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
[ "$(id -u)" -eq 0 ] || { printf 'Use NAS-local sudo.\n' >&2;exit 1; }
[ -d "$source" ] && [ ! -L "$source" ] && [ "$(readlink -f "$source")" = "$source" ] || exit 1
revision=6daa6671a408b126742f0daef8147eb6ac9a2d25
module_sha=18ec6094fb0bae2840ae351c3e6dbfb1b46944dc121e9c1c56d7c80f58e4f304
connector_sha=ed7ad36b144f8b34af56a2f32b3eaeae17268905d1ba043b96422b42783f3274
image=sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0
project=library-studio-nas-pilot
docker_local() { (unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH;docker --host=unix:///var/run/docker.sock "$@"); }
identity=$(docker_local inspect --type container --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.Image}}|{{.State.Health.Status}}' "$project-studio-1")
[ "$identity" = "$project|studio|$image|healthy" ] || exit 1
stage=$(mktemp -d /tmp/library-studio-migrate.XXXXXX)
phase=download
cleanup() {
  result=$?
  trap - EXIT
  if [ "$result" -ne 0 ];then printf 'migration_exit=%s phase=%s\n' "$result" "$phase" >&2;fi
  rm -f "$stage/archive_in_place.py" "$stage/connect-inplace-library.sh";rmdir "$stage"
  exit "$result"
}
trap cleanup EXIT
base=https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio/deploy
curl -fsSL --connect-timeout 15 --max-time 60 "$base/archive_in_place.py" -o "$stage/archive_in_place.py"
curl -fsSL --connect-timeout 15 --max-time 60 "$base/connect-inplace-library.sh" -o "$stage/connect-inplace-library.sh"
printf '%s  %s\n%s  %s\n' "$module_sha" "$stage/archive_in_place.py" "$connector_sha" "$stage/connect-inplace-library.sh" | sha256sum -c -
printf 'Preflight only: both collections, originals RO, NAS metadata preserved in nested ZIP.\n'
phase=preflight
# Refuse to start any service/file changes if this complete bounded plan fails.
docker_local run --rm --pull=never --user 0:0 --network none --read-only --memory 256m --cap-drop ALL --cap-add DAC_OVERRIDE --security-opt no-new-privileges:true \
  --mount "type=bind,src=$source,dst=/nas-library,readonly" \
  --mount "type=bind,src=$stage/archive_in_place.py,dst=/tools/archive_in_place.py,readonly" \
  --entrypoint python "$image" -B /tools/archive_in_place.py --root /nas-library --collection manga --collection images --preserve-nas-metadata
[ "$mode" = apply ] || { printf 'Plan only; no conversion/deletion/service changes.\n';exit 0; }
printf 'Apply: own LRR root reader + RO source, then sibling CBZ verification and exact source-folder removal.\n'
phase=connect
sh "$stage/connect-inplace-library.sh" apply "$source"
phase=convert
docker_local run --rm --pull=never --name library-studio-inplace-convert --user 0:0 --network none --read-only --memory 256m \
  --cap-drop ALL --cap-add DAC_OVERRIDE --cap-add FOWNER --cap-add CHOWN --security-opt no-new-privileges:true \
  --mount "type=bind,src=$source,dst=/nas-library" \
  --mount "type=bind,src=$stage/archive_in_place.py,dst=/tools/archive_in_place.py,readonly" \
  --mount "type=volume,src=${project}_studio-data,dst=/data,volume-nocopy" \
  --entrypoint python "$image" -B /tools/archive_in_place.py --root /nas-library --collection manga --collection images \
  --database /data/studio.db --preserve-nas-metadata --progress --apply --delete-source
printf 'migration=complete; new CBZs will be indexed in place; existing app copies/DB are retained.\n'
