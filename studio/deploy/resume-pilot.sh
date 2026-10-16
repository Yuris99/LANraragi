#!/bin/sh
# Recover ONLY the approved pilot after Synology NanoCPUs/CFS creation failure.
# Never runs install-pilot.sh, regenerates secrets, removes volumes or changes DSM.
set -eu
mode=${1:-plan}
root=${2:-/volume1/docker/library-studio}
case "$mode" in plan|apply) ;; *) printf 'Use: resume-pilot.sh plan|apply /volumeN/docker/library-studio\n' >&2; exit 2;; esac
case "$root" in /volume*/docker/library-studio) ;; *) printf 'Refusing unrelated directory\n' >&2; exit 2;; esac
volume=${root%/docker/library-studio};number=${volume#/volume}
case "$number" in ''|*[!0-9]*) printf 'Invalid volume root\n' >&2; exit 2;; esac
printf 'Project: library-studio-nas-pilot\nRoot: %s\n' "$root"
printf 'Back up own Compose config; remove cpus quota entries; recreate own containers using existing volumes/env.\n'
printf 'Memory limits and worker concurrency 1 remain. No secret regeneration, data deletion or DSM changes.\n'
[ "$mode" = apply ] || { printf 'Plan only: no changes.\n'; exit 0; }
[ "$(id -u)" -eq 0 ] || { printf 'Use sudo for apply.\n' >&2; exit 1; }
[ -d "$root" ] && [ ! -L "$root" ] && [ ! -L "$volume" ] && [ ! -L "$volume/docker" ] || { printf 'Verify the existing dedicated directory first.\n' >&2; exit 1; }
for name in compose.nas.yaml compose.import.yaml compose.pilot.yaml .env.nas; do
  [ -f "$root/$name" ] && [ ! -L "$root/$name" ] || { printf 'Missing or unsafe pilot file: %s\n' "$name" >&2; exit 1; }
done
cd "$root"
docker_local() { (unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH; docker --host=unix:///var/run/docker.sock "$@"); }
docker_local version --format '{{.Server.Version}}' >/dev/null
count=$(grep -Ec '^[[:space:]]*cpus:' compose.nas.yaml || true)
case "$count" in 0) printf 'CPU quota entries already absent.\n';;
  2)
    backup=compose.nas.before-cfs.yaml
    [ ! -e "$backup" ] && [ ! -L "$backup" ] || { printf 'Backup exists; inspect before overwriting any config.\n' >&2; exit 1; }
    cp -p compose.nas.yaml "$backup"
    sed -i '/^[[:space:]]*cpus:/d' compose.nas.yaml
    printf 'Own Compose backed up; CPU quota entries removed.\n';;
  *) printf 'Unexpected CPU configuration; stop for review.\n' >&2; exit 1;;
esac
docker_local compose --env-file .env.nas -p library-studio-nas-pilot -f compose.nas.yaml -f compose.import.yaml -f compose.pilot.yaml config --quiet
docker_local compose --env-file .env.nas -p library-studio-nas-pilot -f compose.nas.yaml -f compose.import.yaml -f compose.pilot.yaml up -d --force-recreate
docker_local compose --env-file .env.nas -p library-studio-nas-pilot -f compose.nas.yaml -f compose.import.yaml -f compose.pilot.yaml ps
