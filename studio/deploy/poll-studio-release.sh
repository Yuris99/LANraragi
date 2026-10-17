#!/bin/sh
# NAS-local, fixed controller. Never download/execute a deployment shell script.
set -eu
umask 077
mode=${1:-status}
case "$mode" in tick|status|enable|disable|recover-locks|rollback) ;; *) printf 'Use: poll.sh tick|status|enable|disable|recover-locks|rollback\n' >&2;exit 2;;esac
[ "$#" -le 1 ] || exit 2
[ "$(id -u)" -eq 0 ] || { printf 'NAS-local root task required.\n' >&2;exit 1; }
control=$(CDPATH='' cd "$(dirname "$0")" && pwd -P)
case "$control" in /volume*/docker/library-studio-deploy) ;; *) printf 'Not an installed Studio deployment controller\n' >&2;exit 1;;esac
root=${control%-deploy}
volume=${root%/docker/library-studio};number=${volume#/volume}
case "$number" in ''|*[!0-9]*) exit 2;;esac
[ ! -L "$control" ] && [ "$(readlink -f "$control")" = "$control" ] || exit 1
[ "$(stat -c '%u:%a' "$control")" = 0:700 ] || { printf 'Controller must be root-owned mode0700.\n' >&2;exit 1; }
cd "$control"
case "$mode" in
  status)
    if [ -f enabled ];then printf 'local_updates=enabled\n';else printf 'local_updates=disabled\n';fi
    if [ -f result ];then cat result;else printf 'deployment=not_attempted\n';fi
    exit 0;;
  disable) rm -f enabled;printf 'local_updates=disabled; any in-flight update may finish\n';exit 0;;
  enable) : > enabled;printf 'local_updates=enabled\n';exit 0;;
  recover-locks)
    # NAS-local only. A release cannot invoke recovery or remove a live lock.
    for path in "$control/poll.lock" "$root/.studio-ui-update.lock";do
      [ -e "$path" ] || [ -L "$path" ] || continue
      [ -d "$path" ] && [ ! -L "$path" ] && [ -f "$path/pid" ] && [ ! -L "$path/pid" ] || exit 1
      owner=$(cat "$path/pid")
      case "$owner" in ''|*[!0-9]*) exit 1;;esac
      [ "$owner" -gt 1 ] || exit 1
      if kill -0 "$owner" 2>/dev/null;then printf 'Active/unknown task; lock preserved.\n' >&2;exit 1;fi
      # These are this controller's own bounded temporary files, never media.
      if [ "$path" = "$control/poll.lock" ];then rm -f "$path/request.json" "$path/parsed";fi
      rm -f "$path/pid";rmdir "$path"
    done
    printf 'Stale locks cleared; failed release remains quarantined. Review local status/log before retry.\n';exit 0;;
esac
if [ "$mode" = rollback ];then
  sha256sum -c controller.sha256 >/dev/null
  sha256sum -c configs.sha256 >/dev/null
  sh ./update-studio-ui.sh rollback "$root"
  exit 0
fi
[ -f enabled ] || { printf 'local_updates=disabled\n';exit 0; }
# Docker name/path/Compose/credentials cannot be supplied by a release request.
# Changed local configuration requires local re-review; no automatic adoption.
sha256sum -c controller.sha256 >/dev/null
sha256sum -c configs.sha256 >/dev/null || { printf 'Local configuration changed; deployment paused.\n' >&2;exit 1; }
lock=$control/poll.lock
mkdir "$lock" 2>/dev/null || { printf 'Deployment poll already locked.\n' >&2;exit 75; }
printf '%s\n' "$$" > "$lock/pid"
cleanup() { rm -f "$lock/request.json" "$lock/parsed" "$lock/pid";rmdir "$lock"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
url=https://raw.githubusercontent.com/Yuris99/LANraragi/refs/heads/feature/library-studio/studio/deploy/nas-release.json
curl -fsSL --connect-timeout 15 --max-time 60 --max-filesize 4096 "$url" -o "$lock/request.json"
[ "$(wc -c < "$lock/request.json")" -le 4096 ] || exit 1
docker_local() { (unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH; docker --host=unix:///var/run/docker.sock "$@"); }
image=sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0
# Use the already loaded immutable Python image: DSM Python is not assumed.
# This parser has no host mounts, credentials, network or elevated privileges.
docker_local run --rm -i --pull=never --user 65534:65534 --network none \
  --read-only --memory 64m --cap-drop ALL --security-opt no-new-privileges:true \
  --entrypoint python "$image" -c '
import json,re,sys
def unique(pairs):
 result={}
 for key,value in pairs:
  if key in result:raise ValueError("duplicate release field")
  result[key]=value
 return result
r=json.load(sys.stdin,object_pairs_hook=unique)
assert type(r) is dict and set(r)=={"schema","enabled","generation","revision","manifest_sha256"}
assert type(r["schema"]) is int and r["schema"]==1 and type(r["enabled"]) is bool
assert type(r["generation"]) is int and 1<=r["generation"]<=2147483647
for key,length in [("revision",40),("manifest_sha256",64)]:
 assert type(r[key]) is str and re.fullmatch("[0-9a-f]{%d}"%length,r[key])
print("enabled" if r["enabled"] else "disabled")
print(r["generation"]);print(r["revision"]);print(r["manifest_sha256"])
' < "$lock/request.json" > "$lock/parsed"
{
  read -r enabled
  read -r generation
  read -r revision
  read -r manifest_sha
} < "$lock/parsed"
[ "$enabled" = enabled ] || { printf 'release=disabled; no Studio changes\n';exit 0; }
request=$generation:$revision:$manifest_sha
if [ -f attempted ];then
  previous_generation=$(cut -d : -f 1 attempted)
  case "$previous_generation" in ''|*[!0-9]*) exit 1;;esac
  if [ "$generation" -le "$previous_generation" ];then
    printf 'release=already_attempted; no duplicate/older update (see local status/result)\n';exit 0
  fi
fi
# Mark before invoking the updater. A failed/interrupted release is quarantined,
# preventing endless DB backups/restarts. A new reviewed generation permits retry.
printf '%s\n' "$request" > attempted.new
mv attempted.new attempted
printf 'generation=%s\nrevision=%s\ndeployment=in_progress\n' "$generation" "$revision" > result.new
mv result.new result
if sh ./update-studio-ui.sh apply-release "$root" "$revision" "$manifest_sha" > last.log 2>&1;then
  outcome=healthy
else
  outcome=failed_or_interrupted
fi
printf 'generation=%s\nrevision=%s\ndeployment=%s\n' "$generation" "$revision" "$outcome" > result.new
mv result.new result
cat result
[ "$outcome" = healthy ]
