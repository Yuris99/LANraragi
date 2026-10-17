#!/bin/sh
# Separate one-time opt-in: this extends source-reading capability, not deploy.
set -eu
umask 077
mode=${1:-preview}
source=${2:-}
case "$mode" in preview|install) ;; *) exit 2;;esac
[ "$#" -le 2 ] || exit 2
case "$source" in /volume[0-9]*/*) ;; *) printf 'Supply the approved NAS source root.\n' >&2;exit 2;;esac
cr=$(printf '\r')
case "$source" in */../*|*/..|*/./*|*/.|*//*|*,*|*'\'*|*'
'*|*"$cr"*) exit 2;;esac
number=${source#/volume};number=${number%%/*}
case "$number" in ''|*[!0-9]*) exit 2;;esac
control=/volume1/docker/library-studio-folders
revision=e328e8fe828cf1288bf728d6ce4954b273a78244
manifest_sha=70abe2d17c753851d4b25c828187bd57cde15bf38accb2ea28384baef6de4faa
tick_sha=e4b5973078d5a4e219f9a424e7e1b58e3aa4f3e580d636cc66261dd4fd711614
printf 'One-time fixed folder queue reader; source RO; only manga/images;10new copies/request; concurrency1.\n'
printf 'Only own Studio data/uploads outputs; no original/ACL/ownership/service/deploy-controller changes.\n'
[ "$mode" = install ] || { printf 'Preview only: no network, Docker or NAS changes.\n';exit 0; }
[ "$(id -u)" -eq 0 ] || exit 1
[ -d "$source" ] && [ ! -L "$source" ] && [ "$(readlink -f "$source")" = "$source" ] || exit 1
[ "$(readlink -f /volume1/docker)" = /volume1/docker ] || exit 1
[ ! -e "$control" ] && [ ! -L "$control" ] || { printf 'Controller exists; preserve and review.\n' >&2;exit 1; }
docker_local() { (unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH;docker --host=unix:///var/run/docker.sock "$@"); }
writer=$(docker_local inspect --type container --format '{{.Config.User}}' library-studio-nas-pilot-studio-1)
case "$writer" in *:*) uid=${writer%:*};gid=${writer#*:};; *) exit 1;;esac
for value in "$uid" "$gid";do case "$value" in ''|*[!0-9]*) exit 1;;esac;[ "$value" -gt 0 ] && [ "$value" -le 2147483647 ] || exit 1;done
metadata=$(docker_local inspect --type container --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.Image}}|{{.State.Health.Status}}' library-studio-nas-pilot-lanraragi-1)
[ "$metadata" = 'library-studio-nas-pilot|lanraragi|sha256:b76c792a43846f0755d0dadf98c8dd46123e8d244045e2f9b6834d9b45988957|healthy' ] || exit 1
metadata=$(docker_local inspect --format '{{range .Mounts}}{{if eq .Destination "/home/koyomi/lanraragi/content/StudioUploads"}}{{.Name}}|{{.Type}}|{{.RW}}{{end}}{{end}}' library-studio-nas-pilot-lanraragi-1)
[ "$metadata" = 'library-studio-nas-pilot_studio-uploads|volume|false' ] || exit 1
printf '%s\n' "$revision" | LC_ALL=C grep -Eq '^[0-9a-f]{40}$' || exit 1
mkdir "$control";chmod 700 "$control"
mkdir "$control/code" "$control/code/web";chmod 755 "$control/code" "$control/code/web"
base=https://raw.githubusercontent.com/Yuris99/LANraragi/$revision/studio
curl -fsSL --connect-timeout 15 --max-time 60 "$base/deploy/runtime-manifest.sha256" -o "$control/code/runtime-manifest.sha256"
printf '%s  %s\n' "$manifest_sha" "$control/code/runtime-manifest.sha256" | sha256sum -c -
while read -r digest relative;do
  printf '%s\n' "$digest" | LC_ALL=C grep -Eq '^[0-9a-f]{64}$' || exit 1
  case "$relative" in web/app.js|web/index.html|web/style.css) ;; *.py) case "$relative" in */*|*..*|*[!A-Za-z0-9_.]*) exit 1;;esac;; *) exit 1;;esac
  curl -fsSL --connect-timeout 15 --max-time 60 "$base/$relative" -o "$control/code/$relative"
  chmod 644 "$control/code/$relative"
done < "$control/code/runtime-manifest.sha256"
(cd "$control/code" && sha256sum -c runtime-manifest.sha256)
curl -fsSL --connect-timeout 15 --max-time 60 "$base/deploy/tick-folder-queue.sh" -o "$control/tick.sh"
printf '%s  tick.sh\n' "$tick_sha" > "$control/controller.sha256"
printf '%s  code/runtime-manifest.sha256\n' "$manifest_sha" >> "$control/controller.sha256"
(cd "$control" && sha256sum -c controller.sha256)
printf '%s\n' "$source" > "$control/source.path"
printf '%s\n' "$writer" > "$control/writer"
chmod 600 "$control/tick.sh" "$control/source.path" "$control/writer"
(cd "$control" && sha256sum source.path writer >> controller.sha256)
sh "$control/tick.sh"
printf 'Folder worker linked. Append this line to the existing5-minute DSM Studio task:\n/bin/sh %s/tick.sh\n' "$control"
