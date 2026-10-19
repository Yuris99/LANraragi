#!/bin/sh
# One local capability upgrade, retaining the existing scheduled command.
set -eu
umask 077
[ "$#" -eq 4 ] || { printf 'Use: install-service-channel.sh APP_ROOT REVISION MANIFEST_SHA preview|install\n' >&2;exit 2; }
root=$1;revision=$2;digest=$3;mode=$4
case "$root" in /volume*/docker/library-studio) ;; *) exit 2;;esac
case "$mode" in preview|install) ;; *) exit 2;;esac
printf '%s\n' "$revision" | LC_ALL=C grep -Eq '^[0-9a-f]{40}$' || exit 2
printf '%s\n' "$digest" | LC_ALL=C grep -Eq '^[0-9a-f]{64}$' || exit 2
control=$root-deploy
printf 'Scope: retain app updater; add two fixed Studio image recipes and separate login/worker project.\n'
printf 'NAS downloads source/dependencies itself; no manual image transfer, SSH keys or new host ports.\n'
printf 'No original-media, LANraragi, Stash/NMLO, account, ACL, firewall or scheduler changes.\n'
[ "$mode" = install ] || exit 0
[ "$(id -u)" -eq 0 ] && [ -d "$control" ] && [ ! -L "$control" ] && [ "$(readlink -f "$control")" = "$control" ] && [ "$(stat -c '%u:%a' "$control")" = 0:700 ] || exit 1
cd "$control"
[ ! -e poll-app-legacy.sh ] && [ ! -L poll-app-legacy.sh ] || { printf 'Extension already installed; not overwritten.\n' >&2;exit 1; }
for target in service-recipes service-release.py poll-studio-services.sh;do
  [ ! -e "$target" ] && [ ! -L "$target" ] || { printf 'Prior extension files preserved; review interrupted installation locally.\n' >&2;exit 1; }
done
sha256sum -c controller.sha256 >/dev/null
sha256sum -c configs.sha256 >/dev/null
mkdir poll.lock 2>/dev/null || { printf 'Existing update is active/locked; preserved.\n' >&2;exit 75; }
printf '%s\n' "$$" > poll.lock/pid
stage=$(mktemp -d "$control/.services-install.XXXXXX")
cleanup() { rm -rf "$stage";rm -f poll.lock/pid;rmdir poll.lock; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
base=https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio/deploy
curl -fsSL --connect-timeout 15 --max-time 60 --max-filesize 4096 "$base/service-controller.sha256" -o "$stage/manifest"
printf '%s  %s\n' "$digest" "$stage/manifest" | sha256sum -c - >/dev/null
count=0
while read -r hash path;do
  case "$path" in service-dispatch.sh|poll-studio-services.sh|service-release.py|service-recipes/Dockerfile.login|service-recipes/Dockerfile.worker|service-recipes/compose.login.yaml|service-recipes/compose.worker-sessions.yaml|service-recipes/deploy/install-site-login.sh) ;; *) exit 1;;esac
  [ ! -e "$stage/$path" ] || exit 1
  mkdir -p "$(dirname "$stage/$path")"
  curl -fsSL --connect-timeout 15 --max-time 60 --max-filesize 131072 "$base/$path" -o "$stage/$path"
  count=$((count + 1))
done < "$stage/manifest"
[ "$count" -eq 8 ] || exit 1
(cd "$stage" && sha256sum -c manifest >/dev/null)
backup=$control/before-service-channel
[ ! -e "$backup" ] && [ ! -L "$backup" ] || exit 1
mkdir "$backup"
cp poll.sh controller.sha256 "$backup/"
cp poll.sh poll-app-legacy.sh
cp "$stage/poll-studio-services.sh" "$stage/service-release.py" .
cp -R "$stage/service-recipes" .
cp "$stage/service-dispatch.sh" poll.sh.new
# Freeze the newly reviewed privilege boundary, not a remote host command.
sha256sum poll-app-legacy.sh update-studio-ui.sh poll-studio-services.sh service-release.py service-recipes/Dockerfile.login service-recipes/Dockerfile.worker service-recipes/compose.login.yaml service-recipes/compose.worker-sessions.yaml service-recipes/deploy/install-site-login.sh > controller.sha256.new
hash=$(sha256sum poll.sh.new | cut -d ' ' -f 1)
printf '%s  poll.sh\n' "$hash" >> controller.sha256.new
mv poll.sh.new poll.sh
mv controller.sha256.new controller.sha256
sha256sum -c controller.sha256 >/dev/null
printf 'service_channel=installed; existing scheduler command retained; services start on next enabled tick\n'
