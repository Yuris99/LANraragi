#!/bin/sh
# One NAS-local connection; subsequent service releases use the existing schedule.
set -eu
umask 077
[ "$#" -eq 1 ] || { printf 'Use: enable-service-channel.sh EXISTING_APP_ROOT\n' >&2;exit 2; }
root=$1
[ "$(id -u)" -eq 0 ] || { printf 'Run once with sudo on the NAS. No passwords or keys are uploaded.\n' >&2;exit 1; }
revision=922a2d7960b086b9b025fe72c6df3a5bcebf5909
installer_sha=7c4495ea7f1a0e0ac1e6ba4d0ce49745061a414465774497b3908b8e65535a37
manifest_sha=f20cb5ac5d89f40fdc2022806157cb1e9bd07e07356c550d3500dacc138f0cbd
temporary=$(mktemp /tmp/library-studio-channel.XXXXXX)
trap 'rm -f "$temporary"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
curl -fsSL --connect-timeout 15 --max-time 60 --max-filesize 16384 "https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio/deploy/install-service-channel.sh" -o "$temporary"
printf '%s  %s\n' "$installer_sha" "$temporary" | sha256sum -c - >/dev/null
sh "$temporary" "$root" "$revision" "$manifest_sha" install
control=$root-deploy
if [ -f "$control/enabled" ] && command -v nohup >/dev/null 2>&1;then
  nohup sh "$control/poll.sh" tick > "$control/first-services.log" 2>&1 </dev/null &
  printf 'first_tick=started; pid=%s; installation_is_not_yet_verified\n' "$!"
  printf 'Progress: %s/first-services.log and services.log\n' "$control"
else
  printf 'first_tick=not_started; existing schedule and local enabled/disabled preference preserved\n'
fi
printf 'Future app/service updates use the existing NAS schedule. Login happens in Studio after installation.\n'
