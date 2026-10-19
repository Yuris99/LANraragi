#!/bin/sh
# NAS-local, explicit installation of a separate Studio login project.
# Requires the reviewed bundle's two images to be loaded already.
set -eu
umask 077
[ "$#" -eq 5 ] || { printf 'Use: install-site-login.sh preview|apply-login|start-worker|status APP_ROOT APP_PROJECT LOGIN_IMAGE WORKER_IMAGE\n' >&2;exit 2; }
mode=$1;root=$2;project=$3;login_image=$4;worker_image=$5
case "$mode" in preview|apply-login|start-worker|status) ;; *) exit 2;;esac
case "$root" in /volume*/docker/*) ;; *) printf 'Use the existing dedicated app root.\n' >&2;exit 2;;esac
[ -d "$root" ] && [ ! -L "$root" ] && [ "$(readlink -f "$root")" = "$root" ] || exit 2
case "$project" in ''|*[!a-zA-Z0-9_-]*) exit 2;;esac
[ "${#project}" -le 45 ] || exit 2
for value in "$login_image" "$worker_image";do
  printf '%s\n' "$value" | LC_ALL=C grep -Eq '^sha256:[0-9a-f]{64}$' || exit 2
done
[ "$(id -u)" -eq 0 ] || { printf 'Run locally with sudo.\n' >&2;exit 1; }
docker_local() { (unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH;docker --host=unix:///var/run/docker.sock "$@"); }
container=$project-studio-1
identity=$(docker_local inspect --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.State.Health.Status}}' "$container")
[ "$identity" = "$project|studio|healthy" ] || { printf 'Existing Studio identity/health differs.\n' >&2;exit 1; }
volume=${project}_studio-data;network=${project}_default
[ "$(docker_local volume inspect --format '{{.Driver}}|{{index .Labels "com.docker.compose.project"}}|{{index .Labels "com.docker.compose.volume"}}' "$volume")" = "local|$project|studio-data" ] || exit 1
[ "$(docker_local network inspect --format '{{index .Labels "com.docker.compose.project"}}' "$network")" = "$project" ] || exit 1
mount=$(docker_local inspect --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Type}}|{{.Name}}|{{.RW}}{{end}}{{end}}' "$container")
[ "$mount" = "volume|$volume|true" ] || exit 1
for image in "$login_image" "$worker_image";do [ "$(docker_local image inspect --format '{{.Id}}' "$image")" = "$image" ] || exit 1;done
[ -f "$root/.env.nas" ] && [ ! -L "$root/.env.nas" ] || exit 1
library=$(sed -n 's/^STUDIO_LIBRARY=//p' "$root/.env.nas")
downloads=$(sed -n 's/^STUDIO_DOWNLOADS=//p' "$root/.env.nas")
case "$library" in "$root"/*) ;; *) printf 'Verify the dedicated app library path first.\n' >&2;exit 1;;esac
case "$downloads" in "$library"/*) ;; *) printf 'Downloads must stay inside the dedicated app library.\n' >&2;exit 1;;esac
[ -d "$downloads" ] && [ ! -L "$downloads" ] && [ "$(readlink -f "$downloads")" = "$downloads" ] || exit 1
source_dir=$(CDPATH='' cd "$(dirname "$0")/.." && pwd -P)
for name in compose.login.yaml compose.worker-sessions.yaml;do [ -f "$source_dir/$name" ] && [ ! -L "$source_dir/$name" ] || exit 1;done
destination=$root/site-login-deploy
printf 'Scope: separate project %s-login; existing Studio is not recreated.\n' "$project"
printf 'New login key/session volumes; one-time initializer creates only .site-login-token and .site-login.json in the dedicated Studio data volume.\n'
printf 'Browser: non-root, one window, 10-minute limit, 1GiB memory, no host port. Worker: concurrency 1, dedicated app downloads, 384MiB.\n'
printf 'Base Compose, deployment controller, DB, original media, Stash/NMLO and NAS ACL are not changed.\n'
[ "$mode" != preview ] || { printf 'preview=complete; nas_changes=none\n';exit 0; }
if [ ! -e "$destination" ];then
  [ "$mode" = apply-login ] || { printf 'Install login first.\n' >&2;exit 1; }
  mkdir "$destination";chmod 700 "$destination"
  cp "$source_dir/compose.login.yaml" "$source_dir/compose.worker-sessions.yaml" "$destination/"
  printf 'STUDIO_LOGIN_IMAGE=%s\nSTUDIO_WORKER_IMAGE=%s\nSTUDIO_DATA_VOLUME=%s\nSTUDIO_APP_NETWORK=%s\n' "$login_image" "$worker_image" "$volume" "$network" > "$destination/.env.images"
  (cd "$destination" && sha256sum compose.login.yaml compose.worker-sessions.yaml .env.images > installation.sha256)
fi
[ -d "$destination" ] && [ ! -L "$destination" ] && [ "$(readlink -f "$destination")" = "$destination" ] || exit 1
(cd "$destination" && sha256sum -c installation.sha256 >/dev/null)
cmp "$source_dir/compose.login.yaml" "$destination/compose.login.yaml" >/dev/null
cmp "$source_dir/compose.worker-sessions.yaml" "$destination/compose.worker-sessions.yaml" >/dev/null
compose() { docker_local compose --env-file "$root/.env.nas" --env-file "$destination/.env.images" -p "$project-login" -f "$destination/compose.login.yaml" -f "$destination/compose.worker-sessions.yaml" "$@"; }
case "$mode" in
  apply-login)
    compose up -d login-init site-login
    printf 'login=started; worker=not_started; use Studio > Site connections. Saved sessions remain unverified.\n';;
  start-worker)
    printf 'Starting the NAS-only external worker. Existing queued NAS command jobs can run. No authentication bypass.\n'
    compose --profile downloads up -d worker
    printf 'worker=started; actual_site_downloads=unverified; choose external worker in Studio.\n';;
  status) compose --profile downloads ps ;;
esac
