#!/bin/sh
# One-time NAS-local installer. Publishing a release never replaces this helper.
set -eu
umask 077
mode=${1:-preview}
root=${2:-/volume1/docker/library-studio}
case "$mode" in preview|install) ;; *) printf 'Use: install-release-poller.sh preview|install /volumeN/docker/library-studio\n' >&2;exit 2;;esac
[ "$#" -le 2 ] || exit 2
case "$root" in /volume*/docker/library-studio) ;; *) printf 'Refusing unrelated app root\n' >&2;exit 2;;esac
volume=${root%/docker/library-studio};number=${volume#/volume}
case "$number" in ''|*[!0-9]*) exit 2;;esac
control=$root-deploy
revision=6f503e823a3cc1528f9d6cc5004d09006b023f19
poll_sha=e9d49924654fc0bf962b9bb9791cfab389a2ace87efe315e448baaacc02c404e
updater_sha=d1fdfa7b0112825abacddee07381163ca1f03c96668c4b84829aefc767493426
printf 'Install fixed Studio-only controller at %s (root-owned0700).\n' "$control"
printf 'No SSH/account/sudoers/firewall changes, no socket handed to Studio, no current deployment.\n'
printf 'Fixed scope: existing Studio project/image, own volumes, RO code, NAS loopback43120.\n'
printf 'Schedule its poll.sh tick using one NAS-local root task; GitHub release requests contain no commands.\n'
[ "$mode" = install ] || { printf 'Preview only: no network, Docker or NAS changes.\n';exit 0; }
[ "$(id -u)" -eq 0 ] || { printf 'One-time install requires NAS-local sudo.\n' >&2;exit 1; }
[ -d "$root" ] && [ ! -L "$root" ] && [ "$(readlink -f "$root")" = "$root" ] || exit 1
[ -d "$volume/docker" ] && [ "$(readlink -f "$volume/docker")" = "$volume/docker" ] || exit 1
[ ! -e "$control" ] && [ ! -L "$control" ] || { printf 'Controller already exists; preserve it and review locally.\n' >&2;exit 1; }
for name in compose.nas.yaml compose.import.yaml compose.pilot.yaml .env.nas;do
  [ -f "$root/$name" ] && [ ! -L "$root/$name" ] || { printf 'Unsafe/missing pilot config\n' >&2;exit 1; }
done
printf '%s\n' "$revision" | LC_ALL=C grep -Eq '^[0-9a-f]{40}$' || exit 1
for digest in "$poll_sha" "$updater_sha";do printf '%s\n' "$digest" | LC_ALL=C grep -Eq '^[0-9a-f]{64}$' || exit 1;done
# Exclusive creation: never overwrite an existing controller/configuration.
mkdir "$control"
chmod 700 "$control"
curl -fsSL --connect-timeout 15 --max-time 60 "https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio/deploy/poll-studio-release.sh" -o "$control/poll.sh"
curl -fsSL --connect-timeout 15 --max-time 60 "https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio/deploy/update-studio-ui.sh" -o "$control/update-studio-ui.sh"
printf '%s  poll.sh\n%s  update-studio-ui.sh\n' "$poll_sha" "$updater_sha" > "$control/controller.sha256"
(cd "$control" && sha256sum -c controller.sha256)
chmod 600 "$control/poll.sh" "$control/update-studio-ui.sh" "$control/controller.sha256"
sha256sum "$root/compose.nas.yaml" "$root/compose.import.yaml" "$root/compose.pilot.yaml" "$root/.env.nas" > "$control/configs.sha256"
: > "$control/enabled"
printf 'controller=installed; NAS services unchanged; no scheduler created.\n'
printf 'DSM Task Scheduler: user=root, every5minutes, command:\n/bin/sh %s/poll.sh tick\n' "$control"
printf 'Disable that DSM task or run: sudo sh %s/poll.sh disable\n' "$control"
