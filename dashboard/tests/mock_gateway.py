"""Tiny stand-in for dukeyos-gateway + app-management, mirroring the real v2 API
shapes (api/app_management/openapi.yaml). Used by tests and the browser E2E run."""
import threading
from flask import Flask, Response, jsonify, request

YAML = "name: demo\nservices:\n  demo:\n    image: nginx\nx-casaos:\n  main: demo\n"


def make_mock():
    app = Flask("mock")
    state = {"apps": {
        "jellyfin": {"app_type": "v2app", "name": "jellyfin", "title": {"en_us": "Jellyfin"},
                     "icon": "", "port": "8096", "index": "/", "status": "running", "scheme": "http",
                     "hostname": "", "store_app_id": "jellyfin"},
        "paused": {"app_type": "v2app", "name": "paused", "title": {"en_us": "Paused App"},
                   "icon": "", "port": "9000", "index": "/", "status": "stopped", "scheme": "http",
                   "hostname": "", "store_app_id": "paused"},
        "legacy": {"app_type": "v1app", "name": "legacy", "title": {"en_us": "Legacy"},
                   "icon": "", "port": "7000", "index": "", "status": "running"},
    }, "calls": []}
    app.state = state

    @app.get("/v2/app_management/web/appgrid")
    def grid():
        return jsonify(message="ok", data=list(state["apps"].values()))

    @app.get("/v2/app_management/apps")
    def store():
        return jsonify(message="ok", data={
            "installed": ["jellyfin"],
            "list": {
                "jellyfin": {"store_app_id": "jellyfin", "title": {"en_us": "Jellyfin"}, "icon": "",
                             "tagline": {"en_us": "Media system"}, "category": "Media"},
                "nginx": {"store_app_id": "nginx", "title": {"en_us": "Nginx"}, "icon": "",
                          "tagline": {"en_us": "Web server"}, "category": "Developer"},
            }})

    @app.get("/v2/app_management/apps/<id>/compose")
    def compose_yaml(id):
        return Response(YAML, mimetype="application/yaml")

    @app.post("/v2/app_management/compose")
    def install():
        state["calls"].append(("install", request.headers.get("Content-Type"), request.get_data(as_text=True)))
        state["apps"]["demo"] = {"app_type": "v2app", "name": "demo", "title": {"en_us": "Demo"},
                                 "icon": "", "port": "8080", "index": "/", "status": "running"}
        return jsonify(message="compose app is being installed asynchronously")

    @app.put("/v2/app_management/compose/<id>/status")
    def set_status(id):
        body = request.get_json(force=True)
        state["calls"].append(("status", id, body))
        if id in state["apps"]:
            state["apps"][id]["status"] = {"start": "running", "stop": "stopped", "restart": "running"}[body]
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
