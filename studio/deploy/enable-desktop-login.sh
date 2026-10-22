#!/bin/sh
# One local, pinned recipe change. Never accepts a remote host command.
set -eu
umask 077
[ "$#" -eq 1 ] || { printf 'Use: enable-desktop-login.sh EXISTING_APP_ROOT\n' >&2;exit 2; }
root=$1
[ "$(id -u)" -eq 0 ] || { printf 'Run once with sudo on the NAS; no credentials are uploaded.\n' >&2;exit 1; }
revision=ada25d12ea62b1db90f86f34a584203ea1520283
installer_sha=e11fd5629b85276976dba0cb55b330802e2c229b9ba5b56b879dbf7bd9373105
manifest_sha=f9580cad0ee907a6b10698e640999613e5e22ef8b5812615d6d8576e44332f6e
temporary=$(mktemp /tmp/studio-desktop-upgrade.XXXXXX)
trap 'rm -f "$temporary"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
curl -fsSL --connect-timeout 15 --max-time 60 --max-filesize 16384 "https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio/deploy/upgrade-desktop-login.sh" -o "$temporary"
printf '%s  %s\n' "$installer_sha" "$temporary" | sha256sum -c - >/dev/null
sh "$temporary" "$root" "$revision" "$manifest_sha" apply
control=$root-deploy
if [ -f "$control/enabled" ] && command -v nohup >/dev/null 2>&1;then
  nohup sh "$control/poll.sh" tick >> "$control/desktop-first.log" 2>&1 </dev/null &
  printf 'desktop_first_tick=started; pid=%s; browser_build_and_website_login_not_yet_verified\n' "$!"
  printf 'Progress: %s/desktop-first.log and services.log; status: poll.sh status\n' "$control"
else
  printf 'desktop_first_tick=not_started; existing schedule and enabled/disabled preference preserved\n'
fi
printf 'After services are healthy, refresh Studio and open Site connections. Human verification is manual.\n'
