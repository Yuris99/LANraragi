#!/bin/sh
# Read-only local NAS inventory. No network, sudo, containers, media or secrets.
# Run on the NAS itself; account UID/GID are observations, not deployment approval.
set -u
printf 'report_version=1\n'
printf 'architecture=%s\n' "$(uname -m)"
printf 'account_uid=%s\n' "$(id -u)"
printf 'account_gid=%s\n' "$(id -g)"
if [ -r /etc.defaults/VERSION ]; then
  awk -F= '/^(majorversion|minorversion|productversion|buildnumber|smallfixnumber)=/ {gsub(/"/,"",$2); print "dsm_" $1 "=" $2}' /etc.defaults/VERSION
else
  printf 'dsm_version=unavailable\n'
fi
for package in ContainerManager Docker; do
  info="/var/packages/$package/INFO"
  if [ -r "$info" ]; then
    awk -F= -v name="$package" '/^version=/ {gsub(/"/,"",$2); print "package_" name "=" $2}' "$info"
  else
    printf 'package_%s=unavailable\n' "$package"
  fi
done
if [ -r /proc/meminfo ]; then
  awk '/^(MemTotal|MemAvailable):/ {print $1 " " $2 " " $3}' /proc/meminfo
fi
if command -v docker >/dev/null 2>&1; then
  # Explicit local daemon, no inherited remote context/TLS selectors.
  (unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH; \
    docker --host=unix:///var/run/docker.sock version --format 'docker_client={{.Client.Version}} docker_server={{if .Server}}{{.Server.Version}}{{else}}unavailable{{end}}' 2>/dev/null) || printf 'docker_daemon=unavailable_or_not_permitted\n'
  if compose_version=$(unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH;
    docker --host=unix:///var/run/docker.sock compose version --short 2>/dev/null); then
    printf 'compose_v2=%s\n' "$compose_version"
  else
    printf 'compose_v2=unavailable\n'
  fi
else
  printf 'docker=unavailable\n'
fi
# Inspect only standard volume roots, never list their contents.
for volume in /volume[0-9]*; do
  [ -d "$volume" ] || continue
  case "${volume#/volume}" in ''|*[!0-9]*) continue;; esac
  printf 'volume_root=%s\n' "$volume"
  candidate="$volume/docker/library-studio"
  if [ -e "$candidate" ] || [ -L "$candidate" ]; then
    printf 'candidate=%s status=already_exists_do_not_adopt\n' "$candidate"
  else
    printf 'candidate=%s status=unverified_not_created\n' "$candidate"
  fi
done
printf 'runtime_uid_gid=unverified\n'
printf 'nas_deployment=not_performed\n'
