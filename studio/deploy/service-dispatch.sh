#!/bin/sh
# Installed once as poll.sh; existing DSM schedule remains unchanged.
set -eu
umask 077
cd "$(CDPATH='' cd "$(dirname "$0")" && pwd -P)"
sha256sum -c controller.sha256 >/dev/null
mode=${1:-status}
[ "$#" -le 1 ] || exit 2
case "$mode" in
  tick)
    sh ./poll-app-legacy.sh tick
    sh ./poll-studio-services.sh ;;
  status)
    sh ./poll-app-legacy.sh status
    if [ -f services.result ];then cat services.result;else printf 'services=not_attempted\n';fi ;;
  recover-locks)
    sh ./poll-app-legacy.sh recover-locks
    if [ -e services.lock ];then
      [ -d services.lock ] && [ ! -L services.lock ] && [ -f services.lock/pid ] && [ ! -L services.lock/pid ] || exit 1
      owner=$(cat services.lock/pid)
      case "$owner" in ''|*[!0-9]*) exit 1;;esac
      [ "$owner" -gt 1 ] && ! kill -0 "$owner" 2>/dev/null || exit 1
      rm -f services.lock/request services.lock/parsed services.lock/pid
      rmdir services.lock
    fi ;;
  enable|disable|rollback) sh ./poll-app-legacy.sh "$mode" ;;
  *) exit 2 ;;
esac
