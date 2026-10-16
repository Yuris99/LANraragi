#!/bin/sh
# Approved, exact-user/exact-client exception. No global forwarding enablement.
set -eu
umask 077
config=/etc/ssh/sshd_config
mode=${1:-plan}
case "$mode" in plan|apply) user=${2:-};client=${3:-};server=${4:-};port=${5:-22};;
  rollback) work=${2:-};case "$work" in /etc/ssh/.studio-tunnel.*) ;; *) printf 'Invalid backup directory\n' >&2;exit 2;;esac
    case "${work#/etc/ssh/.studio-tunnel.}" in ''|*[!A-Za-z0-9]*) printf 'Invalid backup directory\n' >&2;exit 2;;esac
    [ -d "$work" ] && [ ! -L "$work" ] && [ -f "$work/context" ] && [ ! -L "$work/context" ] || exit 2
    user=$(sed -n '1p' "$work/context");client=$(sed -n '2p' "$work/context");server=$(sed -n '3p' "$work/context");port=$(sed -n '4p' "$work/context");;
  *) printf 'Use: configure-tunnel.sh plan|apply USER CLIENT_IPV4 NAS_IPV4 SSH_PORT, or rollback BACKUP_DIR\n' >&2;exit 2;;
esac
die() { printf '%s\n' "$*" >&2;exit 1; }
case "$user" in ''|*[!A-Za-z0-9_.-]*) die 'Use an exact username';;esac
printf '%s\n' "$user" | LC_ALL=C grep -Eq '^[A-Za-z_][A-Za-z0-9_.-]{0,63}$' || die 'Use an exact username'
[ "$user" != root ] || die 'This helper requires a normal approved NAS account'
valid_ip() { case "$1" in ''|*[!0-9.]*) return 1;;esac;printf '%s\n' "$1" | awk -F. 'NF!=4 {exit 1} {for(i=1;i<=4;i++) if($i !~ /^[0-9]+$/ || $i>255 || $i<0 || (length($i)>1 && substr($i,1,1)=="0")) exit 1}'; }
valid_ip "$client" && valid_ip "$server" || die 'Use exact IPv4 addresses, no patterns or networks'
case "$port" in ''|*[!0-9]*) die 'Invalid SSH port';;esac
[ "$port" -ge 1 ] && [ "$port" -le 65535 ] || die 'Invalid SSH port'
printf 'Scope: user=%s client=%s destination=127.0.0.1:43120 local forwarding only\n' "$user" "$client"
[ "$mode" != plan ] || { printf 'Match User %s Address %s\n    AllowTcpForwarding local\n    PermitOpen 127.0.0.1:43120\nPlan only: no NAS changes.\n' "$user" "$client";exit 0; }
[ "$(id -u)" -eq 0 ] || die 'Use sudo for apply/rollback'
[ -f "$config" ] && [ ! -L "$config" ] || die 'Inspect the actual sshd config path first'
[ "$(stat -c %u "$config")" = 0 ] || die 'SSH config must be root-owned'
sshd=$(command -v sshd) || die 'sshd executable is unavailable'
exe=$(readlink -f "$sshd")
[ -x "$exe" ] || die 'Cannot verify sshd executable'
get_effective() { "$sshd" -T -f "$1" -C "user=$2,addr=$3,host=$3,laddr=$server,lport=$port"; }
field() { sed -n "s/^$2 //p" "$1"; }
identity_ok() {
  [ "$(cat "$pidfile" 2>/dev/null)" = "$pid" ] &&
  [ "$(readlink -f "/proc/$pid/exe" 2>/dev/null)" = "$exe" ] &&
  [ "$(cat "/proc/$pid/comm" 2>/dev/null)" = sshd ] &&
  [ "$(awk '/^PPid:/{print $2}' "/proc/$pid/status" 2>/dev/null)" = 1 ] &&
  [ "$(awk '{print $22}' "/proc/$pid/stat" 2>/dev/null)" = "$started" ] && kill -0 "$pid" 2>/dev/null
}
verify_daemon() {
  pidfile=$(field "$1" pidfile)
  case "$pidfile" in /*) ;; *) die 'Cannot verify SSH main PidFile; no config change';;esac
  [ -f "$pidfile" ] && [ ! -L "$pidfile" ] || die 'Main PidFile missing/unsafe; no config change'
  [ "$(stat -c %u "$pidfile")" = 0 ] || die 'Main PidFile must be root-owned'
  pid=$(cat "$pidfile");case "$pid" in ''|*[!0-9]*) die 'Invalid SSH main PID';;esac
  [ "$pid" -gt 1 ] || die 'Invalid SSH main PID'
  started=$(awk '{print $22}' "/proc/$pid/stat")
  identity_ok || die 'Cannot verify the existing SSH main process; no config change'
  tr '\000' '\n' < "/proc/$pid/cmdline" > "$work/main.argv"
  if grep -Eq '(^|[[:space:]])-[fo]' "$work/main.argv";then die 'Custom SSH config/option flags require review; no config change';fi
}
if [ "$mode" = rollback ];then
  [ "$(stat -c %u "$work")" = 0 ] || die 'Backup must be root-owned'
  for name in original applied;do [ -f "$work/$name" ] && [ ! -L "$work/$name" ] || die 'Invalid backup';done
  cmp -s "$config" "$work/applied" || die 'SSH config changed since this proposal; inspect before rollback'
  "$sshd" -t -f "$work/original"
  get_effective "$config" "$user" "$client" > "$work/rollback.before"
  verify_daemon "$work/rollback.before"
  cp -p "$work/original" "$work/rollback.staged"
  identity_ok || die 'SSH main process changed; no config change'
  mv "$work/rollback.staged" "$config"
  kill -HUP "$pid" || die 'Original config restored; main reload could not be confirmed. Keep management session open.'
  printf 'Original SSH config restored and main daemon signaled. Verify a new SSH login before closing this session.\n';exit 0
fi
work=$(mktemp -d /etc/ssh/.studio-tunnel.XXXXXX)
printf '%s\n%s\n%s\n%s\n' "$user" "$client" "$server" "$port" > "$work/context"
printf 'Backup directory: %s\n' "$work"
cp -p "$config" "$work/original"
get_effective "$config" "$user" "$client" > "$work/before"
if grep -Fq '# BEGIN Library Studio scoped tunnel' "$config";then
  [ "$(field "$work/before" allowtcpforwarding)" = local ] && [ "$(field "$work/before" permitopen)" = 127.0.0.1:43120 ] && [ "$(field "$work/before" disableforwarding)" = no ] || die 'Existing Studio rule differs; stop for review'
  printf 'Scoped rule already configured. No config changes or reload. Retry a new PC tunnel.\n';exit 0
fi
[ "$(field "$work/before" allowtcpforwarding)" = no ] && [ "$(field "$work/before" disableforwarding)" = no ] && [ "$(field "$work/before" permitopen)" = any ] || die 'Existing policy differs from the approved report; no config change'
verify_daemon "$work/before"
cp -p "$work/original" "$work/candidate"
printf '\n# BEGIN Library Studio scoped tunnel\nMatch User %s Address %s\n    AllowTcpForwarding local\n    PermitOpen 127.0.0.1:43120\n# END Library Studio scoped tunnel\n' "$user" "$client" >> "$work/candidate"
"$sshd" -t -f "$work/candidate"
get_effective "$work/candidate" "$user" "$client" > "$work/after"
[ "$(field "$work/after" allowtcpforwarding)" = local ] && [ "$(field "$work/after" permitopen)" = 127.0.0.1:43120 ] && [ "$(field "$work/after" disableforwarding)" = no ] || die 'Earlier Match/Include policy prevents the exact scope; no config change'
grep -Ev '^(allowtcpforwarding|permitopen) ' "$work/before" > "$work/before.auth"
grep -Ev '^(allowtcpforwarding|permitopen) ' "$work/after" > "$work/after.auth"
cmp -s "$work/before.auth" "$work/after.auth" || die 'Other target settings changed; no config change'
other_client=$(printf '%s\n' "$client" | awk -F. '{n=$4;if(n%2==0)n++;else n--;printf "%s.%s.%s.%d\n",$1,$2,$3,n}')
get_effective "$config" "$user" "$other_client" > "$work/other-ip.before"
get_effective "$work/candidate" "$user" "$other_client" > "$work/other-ip.after"
cmp -s "$work/other-ip.before" "$work/other-ip.after" || die 'Unrelated client policy changed; no config change'
get_effective "$config" root "$client" > "$work/other-user.before"
get_effective "$work/candidate" root "$client" > "$work/other-user.after"
cmp -s "$work/other-user.before" "$work/other-user.after" || die 'Unrelated user policy changed; no config change'
cmp -s "$config" "$work/original" || die 'SSH config changed during validation; no config change'
cp -p "$work/candidate" "$work/applied"
identity_ok || die 'SSH main process changed; no config change'
changed=0
finished=0
recover_on_error() {
  result=$?
  trap - 0 HUP INT TERM
  if [ "$changed" = 1 ] && [ "$finished" = 0 ];then
    set +e
    cp -p "$work/original" "$work/error-restore" && mv "$work/error-restore" "$config"
    if cmp -s "$config" "$work/original";then
      printf 'Error: original config restored. Keep this management session open.\n' >&2
      if identity_ok;then kill -HUP "$pid";fi
    else printf 'ERROR restoring original: inspect backup %s/original using the open management session.\n' "$work" >&2;fi
  fi
  exit "$result"
}
trap recover_on_error 0
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
changed=1
mv "$work/candidate" "$config"
"$sshd" -t -f "$config"
identity_ok || die 'SSH main process changed before reload'
kill -HUP "$pid"
sleep 1
identity_ok || die 'Main daemon reload needs review'
finished=1
printf 'Scoped SSH rule validated and main daemon reloaded. Existing management session should remain open.\n'
printf 'allowtcpforwarding local\ndisableforwarding no\npermitopen 127.0.0.1:43120\n'
printf 'Rollback if needed: sudo sh %s rollback %s\n' "$0" "$work"
printf 'Reconnect the PC tunnel and verify Studio before closing the NAS SSH session.\n'
