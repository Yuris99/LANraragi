#!/bin/sh
# One local, pinned recipe change. Never accepts a remote host command.
set -eu
umask 077
[ "$#" -eq 1 ] || { printf 'Use: enable-desktop-login.sh EXISTING_APP_ROOT\n' >&2;exit 2; }
root=$1
[ "$(id -u)" -eq 0 ] || { printf 'Run once with sudo on the NAS; no credentials are uploaded.\n' >&2;exit 1; }
revision=7e5fece1f4820ea270ebf6980bfe273cb3664c87
installer_sha=bd650b50403799e8cd7a1ca3b1ec56f5c750ebd82ebe726df2ac75c3b5d8b79d
manifest_sha=f9580cad0ee907a6b10698e640999613e5e22ef8b5812615d6d8576e44332f6e
fetch() {
  attempt=0
  while :;do
    if curl -fsSL --connect-timeout 15 --max-time 60 "$@";then return 0;else code=$?;fi
    # Retry transport failures only, on the same HTTPS URL and normal route.
    # HTTP denials, certificate failures and invalid options stop immediately.
    case "$code" in 6|7|28|52|55|56) ;; *) return "$code";;esac
    attempt=$((attempt + 1))
    [ "$attempt" -lt 4 ] || return "$code"
    printf 'download_network_retry=%s/3; curl_code=%s\n' "$attempt" "$code" >&2
    sleep "$((attempt * 2))"
  done
}

temporary=$(mktemp /tmp/studio-desktop-upgrade.XXXXXX)
trap 'rm -f "$temporary"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
fetch --max-filesize 16384 "https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio/deploy/upgrade-desktop-login.sh" -o "$temporary"
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
