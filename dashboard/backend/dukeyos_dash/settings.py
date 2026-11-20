"""Runtime settings. Everything comes from the environment so that the systemd
EnvironmentFile (/etc/dukeyos/dashboard.env) is the single source of truth."""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent          # .../dashboard/backend
FRONT = BASE.parent / "frontend"


def _int(env, name, default):
    try:
        return int(env.get(name, default))
    except (TypeError, ValueError):
        return int(default)


class Settings:
    def __init__(self, env=None):
        e = os.environ if env is None else env
        self.bind = e.get("DUKEYOS_BIND", "127.0.0.1")
        self.port = _int(e, "DUKEYOS_PORT", 8443)
        self.https = e.get("DUKEYOS_HTTPS", "1") == "1"

        default_state = Path("/var/lib/dukeyos/dashboard")
        if "DUKEYOS_STATE" in e:
            self.state = Path(e["DUKEYOS_STATE"])
        elif default_state.is_dir() and os.access(default_state, os.W_OK):
            self.state = default_state
        else:
            self.state = BASE / ".state"
        self.cert = Path(e.get("DUKEYOS_TLS_CERT", self.state / "tls" / "cert.pem"))
        self.key = Path(e.get("DUKEYOS_TLS_KEY", self.state / "tls" / "key.pem"))

        self.gateway_url = e.get("DUKEYOS_GATEWAY_URL", "")        # empty = read gateway.ini
        self.gateway_ini = Path(e.get("DUKEYOS_GATEWAY_INI", "/etc/dukeyos/gateway.ini"))
        self.svc_user = e.get("DUKEYOS_USER", "")
        self.svc_pass = e.get("DUKEYOS_PASS", "")

        self.data_path = e.get("DUKEYOS_DATA", "/DATA")
        self.capture_iface = e.get("DUKEYOS_CAPTURE_IFACE", "")
        self.capture_filter = e.get("DUKEYOS_CAPTURE_FILTER", "")   # empty = auto
        self.cam_device = e.get("DUKEYOS_CAM", "")                  # empty = auto-detect

        self.max_fails = _int(e, "DUKEYOS_MAX_FAILS", 5)
        self.lock_secs = _int(e, "DUKEYOS_LOCK_SECS", 300)
        self.idle_secs = _int(e, "DUKEYOS_SESSION_IDLE", 12 * 3600)
        self.absolute_secs = _int(e, "DUKEYOS_SESSION_MAX", 7 * 86400)
        self.min_password = 10
        self.fail_delay = float(e.get("DUKEYOS_FAIL_DELAY", "0.6"))   # seconds added to every failed login
