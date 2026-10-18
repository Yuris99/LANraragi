#!/bin/sh
# Read-only NAS-local plan. This does NOT convert/delete, alter mounts or deploy.
set -eu
umask 077
source=${1:-}
[ "$#" -eq 1 ] || exit 2
case "$source" in /volume[0-9]*/*) ;; *) exit 2;;esac
number=${source#/volume};number=${number%%/*}
case "$number" in ''|*[!0-9]*) exit 2;;esac
cr=$(printf '\r')
case "$source" in */../*|*/..|*/./*|*/.|*//*|*,*|*'\'*|*'
'*|*"$cr"*) exit 2;;esac
[ "$(id -u)" -eq 0 ] || { printf 'Run this read-only plan with NAS-local sudo.\n' >&2;exit 1; }
[ -d "$source" ] && [ ! -L "$source" ] && [ "$(readlink -f "$source")" = "$source" ] || exit 1
revision=486de9ea54da52aa5643f5d9831873b8e15be697
module_sha=18ec6094fb0bae2840ae351c3e6dbfb1b46944dc121e9c1c56d7c80f58e4f304
image=sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0
docker_local() { (unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH;docker --host=unix:///var/run/docker.sock "$@"); }
identity=$(docker_local inspect --type container --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.Image}}' library-studio-nas-pilot-studio-1)
[ "$identity" = "library-studio-nas-pilot|studio|$image" ] || exit 1
writer=$(docker_local inspect --format '{{.Config.User}}' library-studio-nas-pilot-studio-1)
case "$writer" in *:*) uid=${writer%:*};gid=${writer#*:};; *) exit 1;;esac
for value in "$uid" "$gid";do case "$value" in ''|*[!0-9]*) exit 1;;esac;[ "$value" -gt 0 ] && [ "$value" -le 2147483647 ] || exit 1;done
stage=$(mktemp -d /tmp/library-studio-inplace-plan.XXXXXX)
# Only this newly created scratch directory is cleaned; never source/data files.
trap 'rm -f "$stage/archive_in_place.py";rmdir "$stage"' EXIT
curl -fsSL --connect-timeout 15 --max-time 60 "https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio/deploy/archive_in_place.py" -o "$stage/archive_in_place.py"
printf '%s  %s\n' "$module_sha" "$stage/archive_in_place.py" | sha256sum -c -
printf 'Read-only plan; no originals, DB, service, ACL or deployment-controller changes.\n'
plan_status=0
docker_local run --rm --pull=never --user 0:0 --network none --read-only --memory 256m --cap-drop ALL --cap-add DAC_OVERRIDE --security-opt no-new-privileges:true \
  --mount "type=bind,src=$source,dst=/nas-library,readonly" \
  --mount "type=bind,src=$stage/archive_in_place.py,dst=/tools/archive_in_place.py,readonly" \
  --entrypoint python "$image" -B /tools/archive_in_place.py --root /nas-library --collection manga --collection images --preserve-nas-metadata || plan_status=$?
docker_local run --rm --pull=never --user "$writer" --network none --read-only --memory 64m --cap-drop ALL --security-opt no-new-privileges:true \
  --mount "type=bind,src=$source,dst=/nas-library,readonly" --entrypoint python "$image" -B -c '
import json,os
result={"probe_uid_gid":str(os.getuid())+":"+str(os.getgid()),"readonly_path_access":{}}
for name in ("root","manga","images"):
    try:
        fd=os.open("/nas-library"+("" if name=="root" else "/"+name),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.listdir(fd)
        finally:os.close(fd)
        result["readonly_path_access"][name]=True
    except OSError:result["readonly_path_access"][name]=False
print(json.dumps(result))'
printf 'nas_conversion=not_performed\nnew_library_mount=not_performed\n'
exit "$plan_status"
