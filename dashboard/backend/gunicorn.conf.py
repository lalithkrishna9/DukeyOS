"""gunicorn settings (everything driven by the same environment as the app).

ONE worker with many threads: sessions, the camera thread and the tshark thread
live in-process, and every WebSocket / MJPEG viewer holds a thread."""
from dukeyos_dash.settings import Settings

_cfg = Settings()
_binds = ["%s:%d" % (_cfg.bind, _cfg.port)]
if _cfg.bind not in ("127.0.0.1", "localhost"):
    _binds.append("127.0.0.1:%d" % _cfg.port)      # local access (kiosk / debugging)
bind = _binds
workers = 1
worker_class = "gthread"
threads = 48
timeout = 60
graceful_timeout = 5
keepalive = 5
limit_request_line = 4094
accesslog = None
errorlog = "-"
if _cfg.https:
    certfile = str(_cfg.cert)
    keyfile = str(_cfg.key)

# gunicorn >= 25 opens a control socket under $HOME by default; this service has no use for it
control_socket_disable = True
