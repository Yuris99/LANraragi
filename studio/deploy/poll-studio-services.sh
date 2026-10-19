#!/bin/sh
# Frozen NAS-local capability: build only two reviewed recipes and own services.
set -eu
umask 077
control=$(CDPATH='' cd "$(dirname "$0")" && pwd -P)
cd "$control"
[ "$(id -u)" -eq 0 ] && [ "$(stat -c '%u:%a' "$control")" = 0:700 ] || exit 1
root=${control%-deploy}
case "$root" in /volume*/docker/library-studio) ;; *) exit 2;;esac
sha256sum -c controller.sha256 >/dev/null
sha256sum -c configs.sha256 >/dev/null
[ -f enabled ] || exit 0
lock=$control/services.lock
mkdir "$lock" 2>/dev/null || exit 75
printf '%s\n' "$$" > "$lock/pid"
started=no
cache=
keep_cache=no
cleanup() {
  code=$?
  if [ "$started" = yes ];then
    printf 'generation=%s\nrevision=%s\nservices=failed_or_interrupted\n' "$generation" "$revision" > services.result.new
    mv services.result.new services.result
  fi
  if [ "$keep_cache" = no ] && [ -n "$cache" ];then rm -rf "$cache";fi
  rm -f "$lock/request" "$lock/parsed" "$lock/pid";rmdir "$lock"
  exit "$code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
docker_local() { (unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH;docker --host=unix:///var/run/docker.sock "$@"); }
base=https://raw.githubusercontent.com/Yuris99/LANraragi
curl -fsSL --connect-timeout 15 --max-time 60 --max-filesize 4096 "$base/refs/heads/feature/library-studio/studio/deploy/nas-services.json" -o "$lock/request"
image=sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0
parser=$(cat "$control/service-release.py")
docker_local run --rm -i --pull=never --user 65534:65534 --network none --read-only --memory 64m --cap-drop ALL --security-opt no-new-privileges:true --entrypoint python "$image" -c "$parser" < "$lock/request" > "$lock/parsed"
{
  read -r enabled
  read -r generation
  read -r revision
  read -r worker
} < "$lock/parsed"
[ "$enabled" = enabled ] || { printf 'services_release=disabled\n';exit 0; }
if [ -f services.attempted ];then
  previous=$(cat services.attempted)
  case "$previous" in ''|*[!0-9]*) exit 1;;esac
  [ "$generation" -gt "$previous" ] || { printf 'services_release=already_attempted\n';exit 0; }
fi
# Persistent source cache is private. A failed generation is never executed again.
cache=$(mktemp -d "$control/service-source-$generation.XXXXXX")
mkdir "$cache/studio"
# A pre-build transfer failure can be retried; no containers have changed.
tail -n +5 "$lock/parsed" > "$cache/sources.sha256"
while read -r digest path;do
  curl -fsSL --connect-timeout 15 --max-time 120 --max-filesize 2097152 "$base/$revision/$path" -o "$cache/$path"
done < "$cache/sources.sha256"
(cd "$cache" && sha256sum -c sources.sha256 >/dev/null)
cp "$control/service-recipes/Dockerfile.login" "$cache/Dockerfile.login"
cp "$control/service-recipes/Dockerfile.worker" "$cache/Dockerfile.worker"
# Mark only once all source bytes are verified, before builds / service mutation.
printf '%s\n' "$generation" > services.attempted.new;mv services.attempted.new services.attempted
started=yes
keep_cache=yes
printf 'generation=%s\nrevision=%s\nservices=in_progress\n' "$generation" "$revision" > services.result.new;mv services.result.new services.result
apply() {
  # Container Manager 24 can lack buildx. These frozen recipes need no BuildKit.
  DOCKER_BUILDKIT=0
  export DOCKER_BUILDKIT
  docker_local build --network default --memory 1g --tag "library-studio-login:g$generation" -f "$cache/Dockerfile.login" "$cache"
  docker_local build --network default --memory 1g --tag "library-studio-worker:g$generation" -f "$cache/Dockerfile.worker" "$cache"
  login=$(docker_local image inspect --format '{{.Id}}' "library-studio-login:g$generation")
  worker_image=$(docker_local image inspect --format '{{.Id}}' "library-studio-worker:g$generation")
  sh "$control/service-recipes/deploy/install-site-login.sh" update-login "$root" library-studio-nas-pilot "$login" "$worker_image"
  if [ "$worker" = yes ];then
    sh "$control/service-recipes/deploy/install-site-login.sh" start-worker "$root" library-studio-nas-pilot "$login" "$worker_image"
  fi
  # Verify RPC is actually responsive using the Studio-side private key; never print it.
  docker_local exec library-studio-nas-pilot-studio-1 python -c 'from site_sessions import LoginClient; c=LoginClient(config_root="/data"); assert c.call({"op":"status"})["configured"]'
}
# Direct invocation keeps errexit active (an if/function would suppress it).
apply > services.log 2>&1
printf 'generation=%s\nrevision=%s\nservices=healthy\n' "$generation" "$revision" > services.result.new
mv services.result.new services.result
started=no
cat services.result
