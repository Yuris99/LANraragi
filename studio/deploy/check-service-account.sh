#!/bin/sh
# Read-only identity check. Does not create accounts, inspect media or run Docker.
set -eu
mode=${1:-preview}
expected_uid=${2:-}
expected_gid=${3:-}
case "$mode" in
  preview)
    printf '%s\n' 'Required: dedicated NAS account library-studio, without administrator/root/docker groups.' 'Personal UID1026 is refused. No account, ACL, files or services changed.'
    exit 0;;
  check) ;;
  *) printf 'Use: check-service-account.sh preview|check [EXPECTED_UID EXPECTED_GID]\n' >&2;exit 2;;
esac
account=library-studio
fail() { printf '%s\n' "$1" >&2;exit 1; }
uid=$(id -u "$account" 2>/dev/null) || fail 'Dedicated library-studio account is not present; no changes made.'
gid=$(id -g "$account" 2>/dev/null) || fail 'Cannot verify service primary group.'
groups=$(id -G "$account" 2>/dev/null) || fail 'Cannot verify service groups.'
names=$(id -Gn "$account" 2>/dev/null) || fail 'Cannot verify service group names.'
for number in "$uid" "$gid" $groups;do
  case "$number" in ''|*[!0-9]*) fail 'Invalid numeric service identity.';;esac
  [ "$number" -gt 0 ] && [ "$number" -le 2147483647 ] || fail 'Root or invalid service identity is refused.'
done
[ "$uid" != 1026 ] || fail 'Personal UID1026 is refused.'
[ -n "$groups" ] && [ -n "$names" ] || fail 'Empty service group identity is refused.'
for group in "$gid" $groups;do
  [ "$group" != 101 ] || fail 'NAS administrator group101 is refused.'
done
for name in $names;do
  case "$name" in root|administrators|docker) fail 'Privileged service group is refused.';;esac
done
if [ -n "$expected_uid$expected_gid" ];then
  [ "$uid:$gid" = "$expected_uid:$expected_gid" ] || fail 'Supplied UID/GID does not match dedicated library-studio account.'
fi
printf 'account=%s\nservice_uid=%s\nservice_gid=%s\nservice_groups=%s\n' "$account" "$uid" "$gid" "$groups"
printf '%s\n' 'identity_check=passed' 'source_access=not_checked' 'existing_service_migration=not_performed' 'nas_changes=none'
