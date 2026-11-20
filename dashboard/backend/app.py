#!/usr/bin/env python3
"""DukeyOS dashboard entry point.

  production : gunicorn -c gunicorn.conf.py app:app      (see packaging/dukeyos-dashboard.service)
  development: python app.py --dev                       (HTTP on 127.0.0.1:8443)
  password   : python app.py --set-password              (reads the new password from stdin)
"""
import sys

from dukeyos_dash.server import create_app
from dukeyos_dash.settings import Settings


def _set_password():
    from dukeyos_dash.auth import AuthStore
    cfg = Settings()
    cfg.state.mkdir(parents=True, exist_ok=True)
    store = AuthStore(cfg.state, min_password=cfg.min_password)
    pw = sys.stdin.readline().rstrip("\n")
    err = store.validate_new(pw)
    if err:
        sys.exit("password rejected: " + err)
    store.set_password(pw)
    print("DukeyOS password updated.")


if "--set-password" in sys.argv:
    _set_password()
    sys.exit(0)

app = create_app()

if __name__ == "__main__":
    cfg = Settings()
    if "--dev" in sys.argv:
        app.run(host="127.0.0.1", port=cfg.port, threaded=True)
    else:
        ctx = (str(cfg.cert), str(cfg.key)) if cfg.https and cfg.cert.exists() else None
        if cfg.https and ctx is None:
            sys.exit("HTTPS is enabled but no certificate was found at %s" % cfg.cert)
        app.run(host=cfg.bind, port=cfg.port, ssl_context=ctx, threaded=True)
