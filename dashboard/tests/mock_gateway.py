"""Tiny stand-in for dukeyos-gateway + app-management, mirroring the real v2 API
shapes (api/app_management/openapi.yaml). Used by tests and the browser E2E run."""
import threading
import time
from flask import Flask, Response, jsonify, request

def _icon(c1, c2):          # small coloured data-URI icons so the browser run can check colours are kept
    return ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
            "<stop offset='0' stop-color='%s'/><stop offset='1' stop-color='%s'/></linearGradient></defs>"
            "<rect width='64' height='64' rx='14' fill='url(%%23g)'/><circle cx='32' cy='32' r='12' fill='white'/></svg>") % (c1, c2)


ICON_RED, ICON_GREEN, ICON_BLUE = _icon("%23ff3b30", "%23ff9500"), _icon("%2334c759", "%2330d5c8"), _icon("%230a84ff", "%235e5ce6")

YAML = "name: demo\nservices:\n  demo:\n    image: nginx\nx-casaos:\n  main: demo\n"


def make_mock():
    app = Flask("mock")
    state = {"apps": {
        "jellyfin": {"app_type": "v2app", "name": "jellyfin", "title": {"en_us": "Jellyfin"},
                     "icon": ICON_RED, "port": "8096", "index": "/", "status": "running(1)", "scheme": "http",
                     "hostname": "", "store_app_id": "jellyfin"},
        "paused": {"app_type": "v2app", "name": "paused", "title": {"en_us": "Paused App"},
                   "icon": ICON_GREEN, "port": "9000", "index": "/", "status": "exited(1)", "scheme": "http",
                   "hostname": "", "store_app_id": "paused"},
        "legacy": {"app_type": "v1app", "name": "legacy", "title": {"en_us": "Legacy"},
                   "icon": "", "port": "7000", "index": "", "status": "running"},
    }, "calls": [], "install_mode": "instant", "install_delay": 0.0, "pending": {}}
    app.state = state

    @app.get("/v2/app_management/web/appgrid")
    def grid():
        now = time.time()                                   # installs that were "slow" finish when their time is up
        for name, t in list(state["pending"].items()):
            if now >= t:
                state["pending"].pop(name)
                state["apps"][name] = {"app_type": "v2app", "name": name, "title": {"en_us": name.title()}, "icon": "",
                                       "port": "8080", "index": "/", "status": "running(1)", "store_app_id": name}
        # like the real engine: a nil slice is encoded as JSON null when nothing is installed
        return jsonify(message="ok", data=list(state["apps"].values()) or None)

    @app.get("/v2/app_management/apps")
    def store():
        return jsonify(message="ok", data={
            "installed": ["jellyfin"],
            "list": {
                "jellyfin": {"store_app_id": "jellyfin", "title": {"en_us": "Jellyfin"}, "icon": ICON_RED,
                             "tagline": {"en_us": "Media system"}, "category": "Media"},
                "nginx": {"store_app_id": "nginx", "title": {"en_us": "Nginx"}, "icon": ICON_BLUE,
                          "tagline": {"en_us": "Web server"}, "category": "Developer"},
            }})

    @app.get("/v2/app_management/apps/<id>/compose")
    def compose_yaml(id):
        return Response(YAML, mimetype="application/yaml")

    @app.post("/v2/app_management/compose")
    def install():
        state["calls"].append(("install", request.headers.get("Content-Type"), request.get_data(as_text=True)))
        mode = state["install_mode"]
        if mode == "ports":
            return jsonify(message="there are ports in use", data={"ports_in_use": {"TCP": ["8080"], "UDP": []}}), 400
        if mode == "conflict":
            return jsonify(message="compose app `demo` is already being installed"), 409
        if mode == "stuck":                                 # accepted, but the pull never finishes (no internet, disk full...)
            return jsonify(message="compose app is being installed asynchronously")
        if mode == "slow":
            state["pending"]["demo"] = time.time() + state["install_delay"]
            return jsonify(message="compose app is being installed asynchronously")
        state["apps"]["demo"] = {"app_type": "v2app", "name": "demo", "title": {"en_us": "Demo"},
                                 "icon": "", "port": "8080", "index": "/", "status": "running(1)", "store_app_id": "demo"}
        return jsonify(message="compose app is being installed asynchronously")

    @app.put("/v2/app_management/compose/<id>/status")
    def set_status(id):
        body = request.get_json(force=True)
        state["calls"].append(("status", id, body))
        if id in state["apps"]:
            state["apps"][id]["status"] = {"start": "running(1)", "stop": "exited(1)", "restart": "running(1)"}[body]
        return jsonify(message="ok")

    @app.delete("/v2/app_management/compose/<id>")
    def uninstall(id):
        state["calls"].append(("uninstall", id, request.args.get("delete_config_folder")))
        state["apps"].pop(id, None)
        return jsonify(message="ok")

    @app.get("/v1/users/status")           # must stay unreachable through the dashboard proxy
    def secret():
        return jsonify(secret=True)

    return app


def serve(port=0):
    from werkzeug.serving import make_server
    app = make_mock()
    srv = make_server("127.0.0.1", port, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return app, srv
