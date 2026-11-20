# DukeyOS

A personal, single-user server dashboard for an HP-laptop homelab (Ubuntu Server 22.04).
CasaOS-derived back end (`core`, `gateway`, `usersvc`, `appmanagement`, `localstorage`, `messagebus`, rebranded `dukeyos-*`)
plus a Flask dashboard: red boot + login screens, then a white-on-black home screen with live system graphs, a cosmetic
Hyderabad globe, real `tshark` packets (view-only), the server's own webcam, and an app strip with the CasaOS app store.

## Install

On your PC (needs Go 1.21+ and internet):

    ./build.sh                  # generates the API code, then builds dist/dukeyos-*

Copy this whole folder to the server, then:

    sudo ./install.sh           # idempotent: keeps config, password and certificate on re-run
    sudo ./uninstall.sh         # keeps /DATA.  --purge-data deletes it (asks you to type DELETE; --yes skips)

Open `https://<tailscale-name-or-ip>:8443` and choose your password on the first visit (10+ characters).

| Environment (`/etc/dukeyos/dashboard.env`) | Meaning | Default |
|---|---|---|
| `DUKEYOS_BIND` | listen address (never 0.0.0.0) | this machine's Tailscale IPv4, else 127.0.0.1 |
| `DUKEYOS_PORT` | dashboard port | 8443 |
| `DUKEYOS_CAPTURE_IFACE` | interface for the packet panel | auto |
| `DUKEYOS_CAM` | camera device | auto-detect |
| `DUKEYOS_MAX_FAILS` / `DUKEYOS_LOCK_SECS` | login lockout | 5 / 300 |

Forgot the password (on the server):

    echo 'new-password' | sudo -u dukeyos /opt/dukeyos/venv/bin/python /opt/dukeyos/dashboard/backend/app.py --set-password

## Security model

* Reachable only over the VPN: the dashboard binds the Tailscale address (+ loopback); every CasaOS service and the gateway bind loopback only.
  No port forwarding. If `ufw` is active the installer admits the dashboard on `tailscale0` only.
* HTTPS always: a Tailscale-issued certificate when HTTPS certs are enabled for your tailnet, otherwise a self-signed one
  (SAN = VPN IP, loopback, hostname). A weekly timer renews it.
* Password hashed with argon2 server-side; random server-side sessions in an HttpOnly, SameSite=Strict, Secure cookie;
  lockout after 5 wrong attempts; CSRF header on every state-changing call; strict CSP.
* The dashboard reaches the app engine only through an allow-listed proxy (`/v2/app_management/*`), nothing else of the gateway.
* Runs as the unprivileged `dukeyos` user; packet capture uses ambient `CAP_NET_RAW/NET_ADMIN`, not root.
* Camera: the **server's** camera only (never the viewer's). Packets: real `tshark` output or an honest OFFLINE with the reason.
* The globe is cosmetic. It is not connected to any location or GeoIP data.

## Open items (from the spec)

* **Kiosk mode** is not implemented. The dashboard listens on `127.0.0.1:8443` as well, so a local browser in kiosk mode can be added later.
* **Uninstall data wipe**: the safe default (keep `/DATA`) was chosen; wipe is opt-in.

## Layout

    dashboard/   Flask back end (backend/), static front end (frontend/), tests (tests/)
    packaging/   systemd units, certificate script
    core gateway usersvc appmanagement localstorage messagebus common   Go services (CasaOS fork)
    build.sh install.sh uninstall.sh

See `dashboard/README.md` for development and tests.
