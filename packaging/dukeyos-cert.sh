#!/usr/bin/env bash
# Create / renew the dashboard's TLS certificate.
#   1. Tailscale-issued certificate for the node's MagicDNS name (browser-trusted), when available;
#   2. otherwise a self-signed certificate whose SAN covers the VPN IP, loopback and the hostname.
# Prints "changed" on stdout when the files were replaced (the caller restarts the dashboard).
set -euo pipefail
ENV_FILE=${DUKEYOS_ENV_FILE:-/etc/dukeyos/dashboard.env}
[ -r "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a
STATE=${DUKEYOS_STATE:-/var/lib/dukeyos/dashboard}
TLS=${DUKEYOS_TLS_DIR:-$STATE/tls}
BIND=${DUKEYOS_BIND:-127.0.0.1}
mkdir -p "$TLS"; chmod 750 "$TLS"
CERT=$TLS/cert.pem; KEY=$TLS/key.pem
before=$(cat "$CERT" "$KEY" 2>/dev/null | sha256sum | cut -d' ' -f1 || true)

fqdn=""
if command -v tailscale >/dev/null 2>&1 && [ "${DUKEYOS_NO_TS_CERT:-0}" != 1 ]; then
  fqdn=$(tailscale status --json 2>/dev/null | python3 -c 'import sys,json
try: print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))
except Exception: pass' || true)
fi

made=""
if [ -n "$fqdn" ]; then
  if tailscale cert --cert-file "$CERT.new" --key-file "$KEY.new" "$fqdn" >/dev/null 2>&1; then
    mv -f "$CERT.new" "$CERT"; mv -f "$KEY.new" "$KEY"; made=tailscale; rm -f "$TLS/self-signed.san"
  else
    rm -f "$CERT.new" "$KEY.new"
  fi
fi

if [ -z "$made" ]; then
  host=$(hostname)
  san="DNS:$host,DNS:localhost,IP:127.0.0.1"
  case "$BIND" in 127.0.0.1|localhost|0.0.0.0|"") ;; *) san="$san,IP:$BIND";; esac
  [ -n "$fqdn" ] && san="$san,DNS:$fqdn"
  marker=$TLS/self-signed.san
  if [ ! -s "$CERT" ] || [ ! -s "$KEY" ] || [ "$(cat "$marker" 2>/dev/null)" != "$san" ] \
     || ! openssl x509 -checkend $((30*86400)) -noout -in "$CERT" >/dev/null 2>&1; then
    openssl req -x509 -newkey rsa:3072 -nodes -days 825 -subj "/CN=$host" -addext "subjectAltName=$san" \
      -keyout "$KEY.new" -out "$CERT.new" 2>/dev/null
    mv -f "$CERT.new" "$CERT"; mv -f "$KEY.new" "$KEY"; echo "$san" > "$marker"; made=self-signed
  fi
fi

chmod 640 "$CERT" "$KEY"
if id dukeyos >/dev/null 2>&1; then chown -R root:dukeyos "$TLS"; fi
after=$(cat "$CERT" "$KEY" | sha256sum | cut -d' ' -f1)
echo "tls: ${made:-unchanged}${fqdn:+ ($fqdn)}" >&2
[ "$before" != "$after" ] && echo changed
exit 0
