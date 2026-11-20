#!/usr/bin/env bash
# DukeyOS uninstaller.   sudo ./uninstall.sh [--purge-data] [--yes]
# By default your data (/DATA: app data, files) is KEPT. --purge-data deletes it after you type the word DELETE.
# Docker containers/images of installed apps are not touched; remove them with `docker rm`/`docker system prune` if wanted.
set -euo pipefail
P=${DUKEYOS_PREFIX:-}
[ -n "$P" ] || [ "$EUID" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
DATA=${DUKEYOS_DATA:-/DATA}; PURGE=0; YES=0
for a in "$@"; do case "$a" in --purge-data) PURGE=1;; --yes|-y) YES=1;; *) echo "unknown option: $a" >&2; exit 2;; esac; done

if [ $PURGE -eq 1 ]; then
  case "$DATA" in ""|/|/usr|/etc|/var|/home|/root|/boot|/bin|/lib|/opt) echo "refusing to purge '$DATA'" >&2; exit 2;; esac
  if [ $YES -ne 1 ]; then
    printf 'This permanently deletes everything in %s. Type DELETE to continue: ' "$DATA"; read -r ans
    [ "$ans" = DELETE ] || { echo "aborted"; exit 1; }
  fi
fi

if [ -z "$P" ]; then
  for u in dukeyos-cert.timer dukeyos-dashboard dukeyos-appmanagement dukeyos-core dukeyos-localstorage dukeyos-usersvc dukeyos-gateway dukeyos-messagebus dukeyos-localstorage-first; do
    systemctl disable --now "$u" 2>/dev/null || true
  done
fi
rm -f "$P"/etc/systemd/system/dukeyos-*.service "$P"/etc/systemd/system/dukeyos-*.timer "$P/usr/bin/dukeyos" "$P"/usr/bin/dukeyos-*
rm -f "$P/etc/systemd/logind.conf.d/dukeyos.conf"
rm -rf "$P/opt/dukeyos" "$P/etc/dukeyos" "$P/var/lib/dukeyos" "$P/var/log/dukeyos" "$P/var/run/dukeyos"
if [ -z "$P" ]; then
  command -v ufw >/dev/null 2>&1 && ufw status numbered 2>/dev/null | grep -q tailscale0 && true
  systemctl daemon-reload; systemctl kill -s HUP systemd-logind 2>/dev/null || true
  id dukeyos >/dev/null 2>&1 && userdel dukeyos 2>/dev/null || true
fi
if [ $PURGE -eq 1 ]; then rm -rf "$P$DATA"; echo "data purged: $DATA"; else echo "kept $DATA  (use --purge-data to delete it)"; fi
echo "DukeyOS removed."
