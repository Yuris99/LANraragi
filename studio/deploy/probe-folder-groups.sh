#!/bin/sh
# Read-only pilot diagnosis with the current NAS account's existing groups.
# No ACL/chown/service changes and no media/database write mounts.
set -eu
umask 077
mode=${1:-preview}
source=${2:-}
collections=${3:-'["manga","images"]'}
case "$mode" in preview|diagnose|plan) ;; *) printf 'Use: probe-folder-groups.sh preview|diagnose|plan /volumeN/SHARE/ROOT [COLLECTIONS_JSON]\n' >&2;exit 2;;esac
case "$source" in /volume[0-9]*/*) ;; *) printf 'Use the verified absolute NAS source path\n' >&2;exit 2;;esac
case "$source" in */../*|*/..|*/./*|*/.|*//*|*,*|*'\'*|*'
'*|*''*) printf 'Use a canonical source path\n' >&2;exit 2;;esac
volume_number=${source#/volume};volume_number=${volume_number%%/*}
case "$volume_number" in ''|*[!0-9]*) printf 'Invalid NAS volume\n' >&2;exit 2;;esac
runtime_uid=$(id -u);runtime_gid=$(id -g);groups=$(id -G)
[ "$runtime_uid" = 1026 ] && [ "$runtime_gid" = 100 ] || {
  printf 'Run as the approved ordinary NAS account (UID1026/GID100), not with sudo sh.\n' >&2;exit 1;
}
set --
[ -n "$groups" ] || { printf 'Cannot determine current account groups\n' >&2;exit 1; }
for group in $groups;do
  case "$group" in ''|*[!0-9]*) printf 'Invalid numeric group identity\n' >&2;exit 2;;esac
  [ "$group" -le 2147483647 ] || exit 2
  set -- "$@" --group-add "$group"
done
[ "$#" -gt 0 ] || { printf 'Cannot determine current account groups\n' >&2;exit 1; }
printf 'Runtime UID/GID: %s:%s\nExisting NAS account groups: %s\n' "$runtime_uid" "$runtime_gid" "$groups"
printf 'Source: %s (read-only)\nNo network, no ACL/ownership changes, no media/database write mounts.\n' "$source"
[ "$mode" != preview ] || { printf 'Preview only: no downloads, containers or NAS changes.\n';exit 0; }
[ -d "$source" ] && [ ! -L "$source" ] && [ "$(readlink -f "$source")" = "$source" ] || {
  printf 'Source missing, inaccessible or not canonical; no container started.\n' >&2;exit 1;
}
work=$(mktemp -d /tmp/library-studio-group-probe.XXXXXX)
revision=14439ae3e3d51b44e9658a8c0d8acb7259551122
curl -fsSL --connect-timeout 15 --max-time 60 \
  "https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio/folder_importer.py" \
  -o "$work/folder_importer.py"
printf '%s  %s\n' a41446f7098c7726f9de03e9072e78423c9aa94a4697b523c12a67215000d8e4 "$work/folder_importer.py" | sha256sum -c -
chmod 644 "$work/folder_importer.py"
# Read the ordinary user's IDs before sudo; never derive memberships from root.
sudo sh -c 'unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH; exec docker --host=unix:///var/run/docker.sock "$@"' library-studio-group-probe \
  run --rm --pull=never --user "$runtime_uid:$runtime_gid" "$@" \
  --network none --read-only --memory 256m --cap-drop ALL --security-opt no-new-privileges:true \
  --mount "type=bind,src=$source,dst=/nas-library,readonly" \
  --mount "type=bind,src=$work/folder_importer.py,dst=/app/folder_importer.py,readonly" \
  --entrypoint python \
  sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0 \
  /app/folder_importer.py --operation "$mode" --collections "$collections"
