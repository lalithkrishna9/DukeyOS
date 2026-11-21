#!/usr/bin/env bash
# DukeyOS installer for Ubuntu Server 22.04.   Run on the server:  sudo ./install.sh
# Build first (on your PC):  ./build.sh      Re-running is safe: config, password and certificate are kept.
#
# Environment:  DUKEYOS_BIND   address to listen on (default: this machine's Tailscale IPv4)
#               DUKEYOS_PORT   dashboard port (default 8443)
#               DUKEYOS_DATA   data directory (default /DATA - must be on the Ubuntu partition)
set -euo pipefail

P=${DUKEYOS_PREFIX:-}                       # test hook: install under a scratch root instead of /
[ -n "$P" ] || [ "$EUID" -eq 0 ] || { echo "run with sudo:  sudo ./install.sh" >&2; exit 1; }
cd "$(dirname "$0")"
DATA=${DUKEYOS_DATA:-/DATA}
PORT=${DUKEYOS_PORT:-8443}
SERVICES="messagebus gateway usersvc localstorage core appmanagement"
say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
die() { echo "error: $*" >&2; exit 1; }

# ---- preflight --------------------------------------------------------------------------------
case "$(uname -m)" in x86_64|amd64) ;; *) echo "warning: this build is linux/amd64 but the machine is $(uname -m)" >&2;; esac
for s in $SERVICES; do [ -x "dist/dukeyos-$s" ] || die "dist/dukeyos-$s is missing - run ./build.sh on your PC first and copy the whole folder here"; done
[ -f dashboard/backend/app.py ] || die "dashboard/ is missing"
case "$PORT" in ''|*[!0-9]*) die "DUKEYOS_PORT must be a number";; esac

# ---- listen address: the VPN only ---------------------------------------------------------------
BIND=${DUKEYOS_BIND:-}
if [ -z "$BIND" ] && command -v tailscale >/dev/null 2>&1; then BIND=$(tailscale ip -4 2>/dev/null | head -1 || true); fi
if [ -z "$BIND" ]; then
  BIND=127.0.0.1
  echo "warning: no Tailscale address found - the dashboard will listen on 127.0.0.1 ONLY." >&2
  echo "         Bring Tailscale up and re-run ./install.sh (or set DUKEYOS_BIND) to reach it over the VPN." >&2
fi
case "$BIND" in 0.0.0.0|::|"") die "refusing to listen on all interfaces; use a VPN address or 127.0.0.1";; esac

# ---- packages -----------------------------------------------------------------------------------
if [ "${DUKEYOS_SKIP_APT:-0}" != 1 ]; then
  say "installing packages"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq docker.io docker-compose-v2 python3-venv python3-pip openssl samba tshark ffmpeg curl ca-certificates >/dev/null \
    || apt-get install -y -qq docker.io python3-venv python3-pip openssl samba tshark ffmpeg curl ca-certificates >/dev/null
fi

# ---- service user -------------------------------------------------------------------------------
if ! id dukeyos >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/dukeyos --shell /usr/sbin/nologin --user-group dukeyos 2>/dev/null || true
fi
getent group video >/dev/null && usermod -aG video dukeyos 2>/dev/null || true

# ---- Go services --------------------------------------------------------------------------------
say "installing services"
mkdir -p "$P/etc/dukeyos" "$P/usr/bin" "$P/etc/systemd/system" "$P/var/lib/dukeyos/dashboard" "$P/var/log/dukeyos" "$P/var/run/dukeyos" "$P$DATA"
chmod 755 "$P/etc/dukeyos"
install -m755 dist/dukeyos-core "$P/usr/bin/dukeyos-core"; ln -sf dukeyos-core "$P/usr/bin/dukeyos"
for s in gateway usersvc appmanagement localstorage messagebus; do install -m755 "dist/dukeyos-$s" "$P/usr/bin/dukeyos-$s"; done
for d in core gateway usersvc appmanagement localstorage messagebus; do
  for f in "$d"/build/sysroot/etc/dukeyos/*.sample; do
    [ -e "$f" ] || continue
    t="$P/etc/dukeyos/$(basename "${f%.sample}")"; [ -e "$t" ] || cp "$f" "$t"
  done
  for u in "$d"/build/sysroot/usr/lib/systemd/system/dukeyos-*.service; do [ -e "$u" ] && cp "$u" "$P/etc/systemd/system/"; done
done
chmod 644 "$P"/etc/dukeyos/*.conf "$P"/etc/dukeyos/*.ini 2>/dev/null || true
# The gateway must stay on loopback; app-management's env file is not needed.
if [ -f "$P/etc/dukeyos/gateway.ini" ] && ! grep -q '^bind=' "$P/etc/dukeyos/gateway.ini"; then
  sed -i '/^\[gateway\]/a bind=127.0.0.1' "$P/etc/dukeyos/gateway.ini"
fi

# ---- dashboard ----------------------------------------------------------------------------------
say "installing dashboard"
APP=$P/opt/dukeyos
mkdir -p "$APP"; rm -rf "$APP/dashboard"; mkdir -p "$APP/dashboard"
cp -r dashboard/backend dashboard/frontend dashboard/requirements.txt dashboard/requirements-camera.txt "$APP/dashboard/"
rm -rf "$APP/dashboard/backend/.state" "$APP/dashboard/backend/__pycache__" "$APP/dashboard/backend/dukeyos_dash/__pycache__"
install -m755 packaging/dukeyos-cert.sh "$APP/dukeyos-cert.sh"
if [ ! -x "$APP/venv/bin/pip" ]; then python3 -m venv "$APP/venv"; fi
if [ "${DUKEYOS_SKIP_PIP:-0}" != 1 ]; then
  "$APP/venv/bin/pip" install -q --upgrade pip >/dev/null 2>&1 || true
  "$APP/venv/bin/pip" install -q -r dashboard/requirements.txt
  # camera support is optional: without OpenCV the camera simply shows OFFLINE
  "$APP/venv/bin/pip" install -q -r dashboard/requirements-camera.txt || echo "note: OpenCV not installed - camera will show OFFLINE" >&2
fi

ENVF=$P/etc/dukeyos/dashboard.env
if [ -f "$ENVF" ]; then                       # keep local edits (e.g. DUKEYOS_CAM / DUKEYOS_CAPTURE_IFACE), refresh the essentials
  sed -i -e "s|^DUKEYOS_BIND=.*|DUKEYOS_BIND=$BIND|" -e "s|^DUKEYOS_PORT=.*|DUKEYOS_PORT=$PORT|" -e "s|^DUKEYOS_DATA=.*|DUKEYOS_DATA=$DATA|" "$ENVF"
else
  cat > "$ENVF" <<ENV
# DukeyOS dashboard - read by systemd (dukeyos-dashboard.service)
DUKEYOS_BIND=$BIND
DUKEYOS_PORT=$PORT
DUKEYOS_HTTPS=1
DUKEYOS_DATA=$DATA
# DUKEYOS_CAPTURE_IFACE=tailscale0    # which interface the packet panel watches (default: auto)
# DUKEYOS_CAM=/dev/video0             # force a camera (default: auto-detect)
ENV
fi
chown root:dukeyos "$ENVF" 2>/dev/null || true; chmod 640 "$ENVF"
chown -R dukeyos:dukeyos "$P/var/lib/dukeyos" 2>/dev/null || true; chmod 750 "$P/var/lib/dukeyos/dashboard"

say "creating TLS certificate"
DUKEYOS_ENV_FILE=$ENVF DUKEYOS_STATE=$P/var/lib/dukeyos/dashboard "$APP/dukeyos-cert.sh" >/dev/null

cp packaging/dukeyos-dashboard.service packaging/dukeyos-cert.service packaging/dukeyos-cert.timer "$P/etc/systemd/system/"

# ---- laptop: keep running with the lid closed -----------------------------------------------------
mkdir -p "$P/etc/systemd/logind.conf.d"
printf '[Login]\nHandleLidSwitch=ignore\nHandleLidSwitchExternalPower=ignore\nHandleLidSwitchDocked=ignore\n' > "$P/etc/systemd/logind.conf.d/dukeyos.conf"

# ---- firewall: if ufw is active, admit the dashboard on the VPN interface only ------------------------
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
  ufw allow in on tailscale0 to any port "$PORT" proto tcp >/dev/null 2>&1 || true
fi

# ---- start --------------------------------------------------------------------------------------
if [ -z "$P" ]; then
  systemctl kill -s HUP systemd-logind 2>/dev/null || true
  systemctl daemon-reload
  systemctl enable dukeyos-localstorage-first; systemctl enable --now dukeyos-messagebus dukeyos-gateway dukeyos-usersvc dukeyos-localstorage dukeyos-core dukeyos-appmanagement
  systemctl enable dukeyos-dashboard dukeyos-cert.timer; systemctl restart dukeyos-dashboard; systemctl start dukeyos-cert.timer
  sleep 2
  systemctl is-active --quiet dukeyos-dashboard || { echo "dashboard did not start:  journalctl -u dukeyos-dashboard -n 50" >&2; exit 1; }
fi

HOSTNAME_URL=$BIND
if command -v tailscale >/dev/null 2>&1; then
  n=$(tailscale status --json 2>/dev/null | python3 -c 'import sys,json
try: print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))
except Exception: pass' || true); [ -n "$n" ] && HOSTNAME_URL=$n
fi
echo
echo "DukeyOS is installed.  Open:  https://$HOSTNAME_URL:$PORT"
echo "First visit: choose your password (10+ characters). Change it later from the PASSWORD button."
[ -f "$P/var/lib/dukeyos/dashboard/tls/self-signed.san" ] && echo "(self-signed certificate: your browser will warn once. Enable HTTPS certificates in the Tailscale admin console, then re-run ./install.sh, for a trusted one.)"
echo "Reset a forgotten password on the server:  echo 'new-password' | sudo -u dukeyos /opt/dukeyos/venv/bin/python /opt/dukeyos/dashboard/backend/app.py --set-password"
