"""Flask application factory for the DukeyOS dashboard."""
import gzip
import hashlib
import json
import mimetypes
import time
from urllib.parse import urlparse

from flask import Flask, Response, abort, jsonify, make_response, request, send_from_directory
from flask_sock import Sock

from . import __version__
from .auth import COOKIE, MAX_PW, AuthStore
from .camera import CameraService
from .gateway import Gateway, GatewayError, PathNotAllowed
from .packets import PacketService
from .settings import FRONT, Settings
from .stats import Stats

CSP = ("default-src 'self'; img-src 'self' data: blob: https: http:; style-src 'self' 'unsafe-inline'; "
       "script-src 'self'; connect-src 'self' ws: wss:; media-src 'self' data: blob:; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
COMPRESSIBLE = {".js", ".json", ".css", ".html", ".svg", ".txt"}


def create_app(settings=None, *, stats=None, camera=None, packets=None, gateway=None, auth=None,
               start_threads=True):
    cfg = settings or Settings()
    cfg.state.mkdir(parents=True, exist_ok=True)
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    sock = Sock(app)

    auth = auth or AuthStore(cfg.state, min_password=cfg.min_password, max_fails=cfg.max_fails,
                             lock_secs=cfg.lock_secs, idle_secs=cfg.idle_secs,
                             absolute_secs=cfg.absolute_secs)
    stats = stats or Stats(cfg.data_path)
    camera = camera or CameraService(forced=cfg.cam_device or None)
    packets = packets or PacketService(iface=cfg.capture_iface, capture_filter=cfg.capture_filter,
                                       own_port=cfg.port)
    gateway = gateway or Gateway(cfg)
    app.extensions["dukeyos"] = dict(cfg=cfg, auth=auth, stats=stats, camera=camera,
                                     packets=packets, gateway=gateway)
    if start_threads:
        stats.start()

    # ---- helpers -----------------------------------------------------------------
    def token():
        return request.cookies.get(COOKIE)

    def authed():
        return auth.valid(token())

    def client_ip():
        return request.remote_addr or "?"

    def deny():
        return jsonify(ok=False, error="unauthorized"), 401

    def same_origin():
        origin = request.headers.get("Origin")
        return not origin or urlparse(origin).netloc == request.host

    def set_cookie(resp, value, clear=False):
        resp.set_cookie(COOKIE, "" if clear else value, httponly=True, samesite="Strict",
                        secure=cfg.https, path="/", max_age=0 if clear else None)
        return resp

    # ---- hooks -------------------------------------------------------------------
    @app.before_request
    def guard():
        if request.path.startswith("/api/") and request.method in ("POST", "PUT", "DELETE", "PATCH"):
            # CSRF: a custom header can't be sent cross-site without a CORS preflight
            if request.headers.get("X-Requested-With") != "DukeyOS" or not same_origin():
                return jsonify(ok=False, error="bad request"), 403

    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = CSP
        if request.path.startswith(("/api/", "/ws/")):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # ---- static ------------------------------------------------------------------
    gz_cache = {}

    def serve(rel):
        full = (FRONT / rel).resolve()
        root = FRONT.resolve()
        if root not in full.parents or not full.is_file():
            abort(404)
        long_cache = rel.startswith("assets/")
        cc = "public, max-age=86400" if long_cache else "no-cache"
        ext = full.suffix.lower()
        st = full.stat()
        if ext in COMPRESSIBLE and st.st_size > 2048 and "gzip" in request.headers.get("Accept-Encoding", ""):
            etag = '"%x-%x-gz"' % (st.st_mtime_ns, st.st_size)
            if request.headers.get("If-None-Match") == etag:
                r = Response(status=304)
            else:
                key = (str(full), st.st_mtime_ns)
                body = gz_cache.get(key)
                if body is None:
                    body = gz_cache[key] = gzip.compress(full.read_bytes(), 6)
                r = Response(body, mimetype=mimetypes.guess_type(str(full))[0] or "application/octet-stream")
                r.headers["Content-Encoding"] = "gzip"
            r.headers.update({"ETag": etag, "Cache-Control": cc, "Vary": "Accept-Encoding"})
            return r
        r = send_from_directory(FRONT, rel, conditional=True, etag=True)
        r.headers["Cache-Control"] = cc
        return r

    @app.get("/")
    def index():
        return serve("index.html")

    @app.get("/<path:rel>")
    def static_files(rel):
        if rel.startswith(("api/", "ws/")):
            abort(404)
        return serve(rel)

    # ---- auth --------------------------------------------------------------------
    @app.get("/api/health")
    def health():
        return jsonify(ok=True, version=__version__)

    @app.get("/api/me")
    def me():
        return jsonify(ok=authed(), setup=auth.needs_setup())

    @app.post("/api/login")
    def login():
        ip = client_ip()
        left = auth.locked_for(ip)
        if left:
            return jsonify(ok=False, locked=left), 429
        body = request.get_json(silent=True) or {}
        pw = body.get("password")
        if not isinstance(pw, str):
            return jsonify(ok=False, error="bad request"), 400
        if auth.needs_setup():                               # first-run: choose the password
            err = auth.validate_new(pw)
            if err:
                return jsonify(ok=False, error=err), 400
            if auth.set_password(pw, only_if_unset=True):
                resp = jsonify(ok=True, first=True)
                return set_cookie(resp, auth.create_session(ip))
        if auth.verify(pw):
            auth.record_success(ip)
            return set_cookie(jsonify(ok=True), auth.create_session(ip))
        locked, remaining = auth.record_fail(ip)
        time.sleep(cfg.fail_delay)                           # slow brute force
        if locked:
            return jsonify(ok=False, locked=locked, left=0), 429
        return jsonify(ok=False, left=remaining), 401

    @app.post("/api/logout")
    def logout():
        auth.destroy(token())
        return set_cookie(jsonify(ok=True), "", clear=True)

    @app.post("/api/password")
    def change_password():
        if not authed():
            return deny()
        body = request.get_json(silent=True) or {}
        cur, new = body.get("current"), body.get("new")
        if not auth.verify(cur):
            time.sleep(cfg.fail_delay)
            return jsonify(ok=False, error="WRONG PASSWORD"), 403
        err = auth.validate_new(new)
        if err:
            return jsonify(ok=False, error=err), 400
        auth.set_password(new)
        auth.destroy_all_except(token())
        return jsonify(ok=True)

    # ---- data --------------------------------------------------------------------
    @app.get("/api/stats")
    def api_stats():
        return jsonify(stats.latest()) if authed() else deny()

    @app.get("/api/procs")
    def api_procs():
        return jsonify(stats.processes()) if authed() else deny()

    @app.get("/api/net")
    def api_net():
        return jsonify(stats.netinfo()) if authed() else deny()

    @sock.route("/ws/stats")
    def ws_stats(ws):
        tok = token()
        if not same_origin() or not auth.valid(tok):
            return
        seq = -1
        while auth.valid(tok, touch=False):
            seq, sample = stats.wait_next(seq, 3.0)
            if sample is not None:
                ws.send(json.dumps(sample))

    # ---- camera ------------------------------------------------------------------
    @app.get("/api/cam/status")
    def cam_status():
        return jsonify(camera.status()) if authed() else deny()

    @app.get("/api/cam")
    def cam_stream():
        if not authed():
            return deny()
        return Response(camera.stream(), mimetype="multipart/x-mixed-replace; boundary=frame",
                        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    # ---- packets -----------------------------------------------------------------
    @sock.route("/ws/packets")
    def ws_packets(ws):
        tok = token()
        if not same_origin() or not auth.valid(tok):
            return
        sub = packets.subscribe()
        last_status = None
        try:
            while auth.valid(tok, touch=False):
                rows, dropped = sub.drain(0.4)
                st = packets.status()
                if rows or st != last_status or dropped:
                    ws.send(json.dumps({"status": st, "rows": rows, "dropped": dropped}))
                    last_status = st
        finally:
            packets.unsubscribe(sub)

    # ---- app engine proxy (allow-listed) -----------------------------------------
    @app.route("/api/svc/<path:p>", methods=["GET", "POST", "PUT", "DELETE"])
    def svc(p):
        if not authed():
            return deny()
        try:
            r = gateway.request(request.method, p, params=request.args, data=request.get_data(),
                                headers={"Content-Type": request.headers.get("Content-Type"),
                                         "Accept": request.headers.get("Accept")})
        except PathNotAllowed:
            return jsonify(message="not allowed"), 403
        except GatewayError:
            return jsonify(message="app engine unavailable"), 502
        return Response(r.content, r.status_code,
                        content_type=r.headers.get("Content-Type", "application/json"))

    @app.errorhandler(404)
    def nf(_e):
        return jsonify(ok=False, error="not found"), 404

    return app
