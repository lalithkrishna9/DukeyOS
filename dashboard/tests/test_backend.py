import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
sys.path.insert(0, str(HERE))

from dukeyos_dash.auth import AuthStore                     # noqa: E402
from dukeyos_dash.camera import CameraService, Device      # noqa: E402
from dukeyos_dash.gateway import valid_path                # noqa: E402
from dukeyos_dash.packets import PacketService, parse_line  # noqa: E402
from dukeyos_dash.server import create_app                 # noqa: E402
from dukeyos_dash.settings import Settings                 # noqa: E402
import mock_gateway                                        # noqa: E402

H = {"X-Requested-With": "DukeyOS"}
PW = "correct horse battery"


def make_env(tmp, **extra):
    env = {"DUKEYOS_STATE": str(tmp), "DUKEYOS_FAIL_DELAY": "0", "DUKEYOS_HTTPS": "0"}
    env.update(extra)
    return Settings(env)


class AuthApi(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.app = create_app(make_env(self.tmp), start_threads=False)
        self.c = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def login(self, pw=PW, client=None):
        return (client or self.c).post("/api/login", json={"password": pw}, headers=H)

    def test_first_run_then_login(self):
        self.assertEqual(self.c.get("/api/me").json, {"ok": False, "setup": True})
        self.assertEqual(self.login("short").status_code, 400)
        r = self.login()
        self.assertTrue(r.json["ok"] and r.json["first"])
        self.assertEqual(self.c.get("/api/me").json, {"ok": True, "setup": False})
        # hash on disk, mode 0600, not the plaintext
        f = self.tmp / "auth.json"
        self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)
        self.assertNotIn(PW, f.read_text())
        self.assertIn("$argon2", f.read_text())

    def test_wrong_password_and_lockout_on_fifth_attempt(self):
        self.login()
        c2 = self.app.test_client()
        for i in range(4):
            r = self.login("nope-nope-nope", c2)
            self.assertEqual((r.status_code, r.json["left"]), (401, 4 - i))
        r = self.login("nope-nope-nope", c2)                  # 5th failure triggers the lock now
        self.assertEqual(r.status_code, 429)
        self.assertGreater(r.json["locked"], 0)
        self.assertEqual(self.login(PW, c2).status_code, 429)  # even the right password is refused

    def test_sessions_are_server_side(self):
        self.login()
        cookie = self.c.get_cookie("dk_sid").value
        self.assertEqual(self.c.get("/api/stats").status_code, 200)
        self.c.post("/api/logout", headers=H)
        other = self.app.test_client()
        other.set_cookie("dk_sid", cookie)                      # stolen cookie replay
        self.assertEqual(other.get("/api/stats").status_code, 401)

    def test_csrf_header_required(self):
        self.assertEqual(self.c.post("/api/login", json={"password": PW}).status_code, 403)
        r = self.c.post("/api/login", json={"password": PW},
                        headers=dict(H, Origin="https://evil.example"))
        self.assertEqual(r.status_code, 403)

    def test_cookie_flags(self):
        r = self.login()
        sc = r.headers["Set-Cookie"]
        self.assertIn("HttpOnly", sc)
        self.assertIn("SameSite=Strict", sc)

    def test_unauthenticated_api_is_denied(self):
        for p in ("/api/stats", "/api/procs", "/api/net", "/api/cam", "/api/cam/status",
                  "/api/svc/v2/app_management/web/appgrid"):
            self.assertEqual(self.c.get(p).status_code, 401, p)

    def test_change_password_kills_other_sessions(self):
        self.login()
        other = self.app.test_client()
        self.login(client=other)
        r = self.c.post("/api/password", json={"current": PW, "new": "another-long-password"}, headers=H)
        self.assertTrue(r.json["ok"])
        self.assertEqual(other.get("/api/stats").status_code, 401)
        self.assertEqual(self.c.get("/api/stats").status_code, 200)
        self.assertTrue(AuthStore(self.tmp).verify("another-long-password"))

    def test_first_run_cannot_be_hijacked_after_setup(self):
        self.login()
        r = self.login("attacker-password-1", self.app.test_client())
        self.assertEqual(r.status_code, 401)

    def test_security_headers_and_static(self):
        r = self.c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertEqual(self.c.get("/../backend/app.py").status_code, 404)
        self.assertEqual(self.c.get("/%2e%2e/backend/app.py").status_code, 404)
        g = self.c.get("/assets/encom-globe.js", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(g.headers.get("Content-Encoding"), "gzip")
        self.assertLess(len(g.data), 600_000)
        g2 = self.c.get("/assets/encom-globe.js", headers={"Accept-Encoding": "gzip",
                                                          "If-None-Match": g.headers["ETag"]})
        self.assertEqual(g2.status_code, 304)


class Proxy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock, cls.srv = mock_gateway.serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        url = "http://127.0.0.1:%d" % self.srv.server_port
        self.app = create_app(make_env(self.tmp, DUKEYOS_GATEWAY_URL=url), start_threads=False)
        self.c = self.app.test_client()
        self.c.post("/api/login", json={"password": PW}, headers=H)
        self.mock.state["calls"].clear()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_allowed_get(self):
        r = self.c.get("/api/svc/v2/app_management/web/appgrid")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json["data"]), 3)

    def test_yaml_body_and_content_type_survive(self):
        y = self.c.get("/api/svc/v2/app_management/apps/nginx/compose", headers={"Accept": "application/yaml"})
        self.assertIn("x-casaos", y.get_data(as_text=True))
        r = self.c.post("/api/svc/v2/app_management/compose?check_port_conflict=true", data=y.data,
                        headers=dict(H, **{"Content-Type": "application/yaml"}))
        self.assertEqual(r.status_code, 200)
        call = self.mock.state["calls"][-1]
        self.assertEqual(call[0], "install")
        self.assertIn("application/yaml", call[1])
        self.assertIn("name: demo", call[2])

    def test_status_and_uninstall(self):
        r = self.c.put("/api/svc/v2/app_management/compose/paused/status", data='"start"',
                       headers=dict(H, **{"Content-Type": "application/json"}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.mock.state["calls"][-1], ("status", "paused", "start"))
        self.c.delete("/api/svc/v2/app_management/compose/paused?delete_config_folder=false", headers=H)
        self.assertEqual(self.mock.state["calls"][-1], ("uninstall", "paused", "false"))

    def test_install_errors_reach_the_browser_intact(self):
        """The UI shows the engine's own message (ports in use, already installing); the proxy must not swallow it."""
        h = dict(H, **{"Content-Type": "application/yaml"})
        try:
            self.mock.state["install_mode"] = "ports"
            r = self.c.post("/api/svc/v2/app_management/compose", data="name: demo", headers=h)
            self.assertEqual(r.status_code, 400)
            self.assertEqual(r.json["data"]["ports_in_use"]["TCP"], ["8080"])
            self.mock.state["install_mode"] = "conflict"
            r = self.c.post("/api/svc/v2/app_management/compose", data="name: demo", headers=h)
            self.assertEqual(r.status_code, 409)
            self.assertIn("already being installed", r.json["message"])
        finally:
            self.mock.state["install_mode"] = "instant"

    def test_status_strings_match_docker_compose_format(self):
        grid = self.c.get("/api/svc/v2/app_management/web/appgrid").json["data"]
        self.assertIn("running(1)", [a["status"] for a in grid])

    def test_everything_else_is_blocked(self):
        for p in ("v1/users/status", "v2/app_management/../../v1/users/status",
                  "v2/app_management/%2e%2e/%2e%2e/v1/users/status", "v1/sys/wsssh",
                  "v2/app_management/..%252f..%252fv1/users/status"):
            r = self.c.get("/api/svc/" + p)
            self.assertIn(r.status_code, (403, 404), p)
            self.assertNotIn(b"secret", r.data, p)

    def test_unreachable_gateway_is_502_not_500(self):
        app = create_app(make_env(self.tmp, DUKEYOS_GATEWAY_URL="http://127.0.0.1:9"), start_threads=False)
        c = app.test_client()
        c.post("/api/login", json={"password": PW}, headers=H)
        self.assertEqual(c.get("/api/svc/v2/app_management/web/appgrid").status_code, 502)

    def test_valid_path_unit(self):
        self.assertTrue(valid_path("v2/app_management/compose"))
        self.assertFalse(valid_path("v2/app_management/../x"))
        self.assertFalse(valid_path("v1/anything"))


class Camera(unittest.TestCase):
    class Cap:
        def __init__(self, path, fail=False):
            self.path, self.fail, self.released = path, fail, False

        def opened(self):
            return True

        def read_jpeg(self):
            return None if self.fail else b"\xff\xd8" + self.path.encode()

        def release(self):
            self.released = True

    def make(self, devs, **kw):
        self.devs = devs
        self.caps = []

        def opener(path):
            c = self.Cap(path)
            self.caps.append(c)
            return c
        return CameraService(scan=lambda: list(self.devs), opener=opener, fps=100,
                             idle_release=0.3, rescan_every=0.1, **kw)

    def first_frame(self, svc):
        g = svc.stream(give_up_after=3)
        return g, next(g)

    def test_offline_when_no_device(self):
        svc = self.make([])
        self.assertFalse(svc.status()["online"])
        g = svc.stream(give_up_after=0.5)
        self.assertEqual(list(g), [])                            # ends instead of hanging / erroring

    def test_picks_device_and_shares_frames(self):
        svc = self.make([Device("/dev/video0", "Built-in", 0, 1.0)])
        self.assertTrue(svc.status()["online"])
        g1, f1 = self.first_frame(svc)
        g2, f2 = self.first_frame(svc)
        self.assertIn(b"/dev/video0", f1)
        self.assertEqual(len(self.caps), 1)                      # one capture shared by two viewers
        g1.close(); g2.close(); svc.close()

    def test_prefers_newly_plugged_usb_and_follows_unplug(self):
        svc = self.make([Device("/dev/video0", "Built-in", 0, 1.0)])
        svc._started -= 10                                       # initial scan window is over
        g, f = self.first_frame(svc)
        self.assertIn(b"/dev/video0", f)
        self.devs.append(Device("/dev/video2", "USB Cam", 2, 2.0))   # hot-plug
        seen = None
        for _ in range(200):
            chunk = next(g)
            if b"/dev/video2" in chunk:
                seen = chunk
                break
        self.assertIsNotNone(seen, "did not switch to the newly connected camera")
        self.devs.pop()                                          # unplug it again
        for _ in range(400):
            if b"/dev/video0" in next(g):
                break
        else:
            self.fail("did not fall back to the built-in camera")
        g.close(); svc.close()

    def test_device_released_when_idle(self):
        svc = self.make([Device("/dev/video0", "Built-in", 0, 1.0)])
        g, _ = self.first_frame(svc)
        g.close()
        time.sleep(2.5)
        self.assertTrue(self.caps[0].released)
        svc.close()

    def test_unreadable_device_marked_broken(self):
        svc = CameraService(scan=lambda: [Device("/dev/video0", "x", 0, 1.0)],
                            opener=lambda p: self.Cap(p, fail=True), fps=100)
        g = svc.stream(give_up_after=2)
        self.assertEqual(list(g), [])
        self.assertFalse(svc.status()["online"])
        svc.close()


class Packets(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.old_path = os.environ["PATH"]

    def tearDown(self):
        os.environ["PATH"] = self.old_path
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake(self, body):
        p = self.tmp / "tshark"
        p.write_text("#!/bin/sh\n" + body)
        p.chmod(0o755)
        os.environ["PATH"] = "%s:%s" % (self.tmp, self.old_path)

    def collect(self, svc, secs):
        sub = svc.subscribe()
        rows, end = [], time.time() + secs
        while time.time() < end:
            r, _ = sub.drain(0.2)
            rows += r
        st = svc.status()
        svc.unsubscribe(sub)
        return rows, st

    def test_parse_line_ipv4_ipv6_arp_and_icmp(self):
        row = parse_line("7\t0.123456789\t10.0.0.2\t\t\taa:bb\t1.1.1.1\t\t\tcc:dd\tDNS\t74\tStandard query A x.com\n")
        self.assertEqual((row["no"], row["src"], row["dst"], row["proto"], row["len"]),
                         (7, "10.0.0.2", "1.1.1.1", "DNS", "74"))
        v6 = parse_line("8\t1.0\t\tfe80::1\t\t\t\tff02::1\t\t\tICMPv6\t86\tRouter Solicitation\n")
        self.assertEqual((v6["src"], v6["dst"]), ("fe80::1", "ff02::1"))
        arp = parse_line("9\t1.0\t\t\t10.0.0.5\t\t\t\t10.0.0.1\t\tARP\t42\tWho has 10.0.0.1?\n")
        self.assertEqual((arp["src"], arp["dst"]), ("10.0.0.5", "10.0.0.1"))
        self.assertIsNone(parse_line("garbage\n"))

    def test_streams_rows_and_goes_live(self):
        self.fake("""i=1
while [ $i -le 5 ]; do
printf '%s\\t0.%s\\t10.0.0.2\\t\\t\\taa\\t1.1.1.1\\t\\t\\tbb\\tTCP\\t60\\tinfo\\n' $i $i
i=$((i+1)); sleep 0.05; done
sleep 30
""")
        svc = PacketService(iface="lo", idle_stop=0.5)
        rows, st = self.collect(svc, 2.2)
        self.assertEqual([r["no"] for r in rows], [1, 2, 3, 4, 5])
        self.assertEqual(st["state"], "live")
        svc.close()

    def test_missing_tshark_is_offline_never_fake_data(self):
        os.environ["PATH"] = str(self.tmp)                       # empty dir: no tshark
        svc = PacketService(iface="lo", tshark="tshark-does-not-exist")
        rows, st = self.collect(svc, 0.8)
        self.assertEqual(rows, [])
        self.assertEqual(st["state"], "offline")
        self.assertIn("not installed", st["reason"])
        svc.close()

    def test_permission_denied_is_offline_with_reason(self):
        self.fake("echo \"tshark: You don't have permission to capture on that device\" >&2; exit 2\n")
        svc = PacketService(iface="lo")
        rows, st = self.collect(svc, 1.0)
        self.assertEqual(rows, [])
        self.assertEqual(st["state"], "offline")
        self.assertEqual(st["reason"], "no capture permission")
        svc.close()

    def test_flips_field_name_variant_for_tshark_4(self):
        self.fake("""case "$*" in *_ws.col.Protocol*) echo "tshark: Some fields aren't valid" >&2; exit 2;; esac
printf '1\\t0.1\\t1.2.3.4\\t\\t\\ta\\t5.6.7.8\\t\\t\\tb\\tUDP\\t10\\tx\\n'
sleep 30
""")
        svc = PacketService(iface="lo", idle_stop=0.5)
        rows, st = self.collect(svc, 2.5)
        self.assertEqual(len(rows), 1)
        svc.close()

    def test_stops_tshark_when_last_viewer_leaves(self):
        self.fake("echo $$ > %s/pid; sleep 60\n" % self.tmp)
        svc = PacketService(iface="lo", idle_stop=0.5)
        sub = svc.subscribe()
        time.sleep(1.0)
        pid = int((self.tmp / "pid").read_text())
        svc.unsubscribe(sub)
        time.sleep(3.0)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        svc.close()


class StatsSampler(unittest.TestCase):
    def test_sample_shape(self):
        from dukeyos_dash.stats import Stats
        s = Stats("/")
        s.sample()
        time.sleep(0.2)
        x = s.sample()
        for k in ("cpu", "cores", "ram", "rx", "tx", "uptime", "host", "temp", "disk"):
            self.assertIn(k, x)
        self.assertTrue(0 <= x["cpu"] <= 100)
        self.assertTrue(len(s.processes()) > 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
