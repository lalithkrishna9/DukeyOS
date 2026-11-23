# DukeyOS dashboard

Flask + flask-sock, served by gunicorn (1 worker, 48 threads). Front end is plain HTML/CSS/JS plus the eDEX `encom-globe` (three.js).

## Run for development

    python3 -m venv .venv && . .venv/bin/activate
    pip install -r requirements.txt            # + requirements-camera.txt for the camera
    cd backend && DUKEYOS_HTTPS=0 DUKEYOS_STATE=/tmp/dukeyos-state python app.py --dev     # http://127.0.0.1:8443

Production runs `gunicorn -c gunicorn.conf.py app:app` (see `../packaging/dukeyos-dashboard.service`).
Python 3.10+ (the server's version).

## Tests

    pip install pytest && python -m pytest -q tests      # 31 tests: auth, lockout, CSRF, sessions, proxy allow-list, camera, packets, stats, front-end helpers (the helper tests need node and are skipped without it)
    # tests/mock_gateway.py is a stand-in for the gateway + app-management API shapes

## HTTP surface

`/api/me /api/login /api/logout /api/password /api/stats /api/procs /api/net /api/cam/status /api/cam (MJPEG)`
`/ws/stats /ws/packets /api/svc/v2/app_management/*` (everything except `/api/me`, `/api/login` and static files needs a session).
