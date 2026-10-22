#!/bin/sh
# One locally reviewed recipe upgrade; no remote host commands or new mounts.
set -eu
umask 077
[ "$#" -eq 4 ] || { printf 'Use: upgrade-desktop-login.sh APP_ROOT REVISION MANIFEST_SHA preview|apply\n' >&2;exit 2; }
root=$1;revision=$2;digest=$3;mode=$4
case "$root" in /volume*/docker/library-studio) ;; *) exit 2;;esac
case "$mode" in preview|apply) ;; *) exit 2;;esac
printf '%s\n' "$revision" | LC_ALL=C grep -Eq '^[0-9a-f]{40}$' || exit 2
printf '%s\n' "$digest" | LC_ALL=C grep -Eq '^[0-9a-f]{64}$' || exit 2
control=$root-deploy
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
printf 'Scope: replace only frozen Studio service recipes/controller; add X11 tools for an ordinary Chromium window.\n'
printf 'Same existing login/worker project, UID, ports, mounts, keys and session volumes. No browser debug or VNC port.\n'
printf 'No originals, media/DB, NAS accounts/ACL, LANraragi, Stash/NMLO or scheduler changes.\n'
[ "$mode" = apply ] || exit 0
[ "$(id -u)" -eq 0 ] && [ -d "$control" ] && [ ! -L "$control" ] && [ "$(readlink -f "$control")" = "$control" ] && [ "$(stat -c '%u:%a' "$control")" = 0:700 ] || exit 1
cd "$control"
sha256sum -c controller.sha256 >/dev/null
sha256sum -c configs.sha256 >/dev/null
[ -f poll-app-legacy.sh ] && [ ! -L poll-app-legacy.sh ] || exit 1
if [ -f desktop-controller.revision ];then
  recorded=$(cat desktop-controller.revision)
  recorded_revision=${recorded%:*};recorded_digest=${recorded#*:}
  printf '%s\n' "$recorded_revision" | LC_ALL=C grep -Eq '^[0-9a-f]{40}$' || exit 1
  [ "$recorded_digest" = "$digest" ] || exit 1
  printf 'desktop_controller=already_installed; no overwrite\n';exit 0
fi
[ ! -e before-desktop-login ] && [ ! -L before-desktop-login ] || { printf 'Prior upgrade backup preserved; inspect locally before retry.\n' >&2;exit 1; }
mkdir poll.lock 2>/dev/null || exit 75
printf '%s\n' "$$" > poll.lock/pid
if ! mkdir services.lock 2>/dev/null;then rm -f poll.lock/pid;rmdir poll.lock;exit 75;fi
printf '%s\n' "$$" > services.lock/pid
stage=$(mktemp -d "$control/.desktop-upgrade.XXXXXX")
changed=no
cleanup() {
  code=$?
  if [ "$changed" = yes ] && [ "$code" -ne 0 ];then
    while read -r hash path;do
      target=$path;[ "$path" != service-dispatch.sh ] || target=poll.sh
      cp "before-desktop-login/$target" "$target" || true
    done < "$stage/manifest"
    cp before-desktop-login/controller.sha256 controller.sha256 || true
    printf 'desktop_upgrade=failed; previous frozen files restored where possible; inspect locally\n' >&2
  fi
  rm -rf "$stage";rm -f poll.lock/pid services.lock/pid;rmdir poll.lock services.lock
  exit "$code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
base=https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio/deploy
fetch --max-filesize 4096 "$base/service-controller.sha256" -o "$stage/manifest"
printf '%s  %s\n' "$digest" "$stage/manifest" | sha256sum -c - >/dev/null
count=0
while read -r hash path;do
  case "$path" in service-dispatch.sh|poll-studio-services.sh|service-release.py|service-recipes/Dockerfile.login|service-recipes/Dockerfile.worker|service-recipes/compose.login.yaml|service-recipes/compose.worker-sessions.yaml|service-recipes/deploy/install-site-login.sh) ;; *) exit 1;;esac
  [ ! -e "$stage/$path" ] || exit 1
  mkdir -p "$(dirname "$stage/$path")"
  fetch --max-filesize 131072 "$base/$path" -o "$stage/$path"
  count=$((count + 1))
done < "$stage/manifest"
[ "$count" -eq 8 ] || exit 1
(cd "$stage" && sha256sum -c manifest >/dev/null)
# The Compose files remain byte-identical: no authority or volume expansion.
cmp "$stage/service-recipes/compose.login.yaml" service-recipes/compose.login.yaml >/dev/null
cmp "$stage/service-recipes/compose.worker-sessions.yaml" service-recipes/compose.worker-sessions.yaml >/dev/null
mkdir before-desktop-login
cp controller.sha256 before-desktop-login/
while read -r hash path;do
  target=$path;[ "$path" != service-dispatch.sh ] || target=poll.sh
  [ -f "$target" ] && [ ! -L "$target" ] || exit 1
  mkdir -p "$(dirname "before-desktop-login/$target")"
  cp "$target" "before-desktop-login/$target"
done < "$stage/manifest"
changed=yes
while read -r hash path;do
  target=$path;[ "$path" != service-dispatch.sh ] || target=poll.sh
  cp "$stage/$path" "$target.new";mv "$target.new" "$target"
done < "$stage/manifest"
sha256sum poll-app-legacy.sh update-studio-ui.sh poll-studio-services.sh service-release.py service-recipes/Dockerfile.login service-recipes/Dockerfile.worker service-recipes/compose.login.yaml service-recipes/compose.worker-sessions.yaml service-recipes/deploy/install-site-login.sh poll.sh > controller.sha256.new
mv controller.sha256.new controller.sha256
sha256sum -c controller.sha256 >/dev/null
sha256sum -c configs.sha256 >/dev/null
printf '%s:%s\n' "$revision" "$digest" > desktop-controller.revision
changed=no
printf 'desktop_controller=installed; ordinary-browser image builds on next enabled tick; website_verification=not_performed\n'
