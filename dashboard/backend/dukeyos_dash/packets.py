"""Real packet capture via tshark (view-only; no shell, no interactivity).

* tshark is started when the first viewer connects and stopped ~20 s after the
  last one leaves (an idle capture would burn CPU on an old laptop for nothing).
* If tshark is missing / lacks capture permission the status is `offline` with a
  reason - fake or placeholder packets are never produced.
* The dashboard's own port is excluded by a capture filter so watching the
  panel does not feed back into the panel."""
import atexit
import os
import shutil
import signal
import subprocess
import threading
import time
from collections import deque

from .stats import default_iface

FIELDS = ["frame.number", "frame.time_relative",
          "ip.src", "ipv6.src", "arp.src.proto_ipv4", "eth.src",
          "ip.dst", "ipv6.dst", "arp.dst.proto_ipv4", "eth.dst",
          "@PROTO", "frame.len", "@INFO"]


def build_cmd(exe, iface, cap_filter, variant):
    names = {"upper": ("_ws.col.Protocol", "_ws.col.Info"), "lower": ("_ws.col.protocol", "_ws.col.info")}[variant]
    cmd = [exe, "-l", "-n", "-i", iface]
    if cap_filter:
        cmd += ["-f", cap_filter]
    cmd += ["-T", "fields", "-E", "separator=\t", "-E", "occurrence=f"]
    for f in FIELDS:
        cmd += ["-e", names[0] if f == "@PROTO" else names[1] if f == "@INFO" else f]
    return cmd


def parse_line(line):
    f = line.rstrip("\n").split("\t")
    if len(f) < 13:
        return None
    first = lambda *v: next((x for x in v if x), "")      # noqa: E731
    try:
        no = int(f[0])
    except ValueError:
        return None
    return {"no": no, "t": f[1][:9],
            "src": first(f[2], f[3], f[4], f[5]), "dst": first(f[6], f[7], f[8], f[9]),
            "proto": f[10], "len": f[11], "info": "\t".join(f[12:])[:140]}


class Subscription:
    def __init__(self, maxlen=500):
        self.rows = deque(maxlen=maxlen)
        self.dropped = 0
        self.cv = threading.Condition()

    def push(self, row):
        with self.cv:
            if len(self.rows) == self.rows.maxlen:
                self.dropped += 1
            self.rows.append(row)
            self.cv.notify()

    def drain(self, timeout):
        with self.cv:
            if not self.rows:
                self.cv.wait(timeout)
            rows, dropped = list(self.rows), self.dropped
            self.rows.clear()
            self.dropped = 0
            return rows, dropped


class PacketService:
    def __init__(self, *, iface="", capture_filter="", own_port=8443, idle_stop=20.0, tshark="tshark"):
        self._iface, self._tshark = iface, tshark
        self._filter = capture_filter or "not tcp port %d" % own_port
        self._idle_stop = idle_stop
        self._cv = threading.Condition()
        self._subs = set()
        self._state, self._reason, self._used_iface = "idle", None, None
        self._proc = None
        self._variant = "upper"
        self._thread = None
        self._empty_since = time.monotonic()
        self._stop = False
        atexit.register(self.close)

    # ---- public --------------------------------------------------------------
    def subscribe(self):
        sub = Subscription()
        with self._cv:
            self._subs.add(sub)
            if self._state == "idle":
                self._state = "starting"
            if not (self._thread and self._thread.is_alive()):
                self._stop = False
                self._thread = threading.Thread(target=self._run, name="tshark", daemon=True)
                self._thread.start()
            self._cv.notify_all()
        return sub

    def unsubscribe(self, sub):
        with self._cv:
            self._subs.discard(sub)
            if not self._subs:
                self._empty_since = time.monotonic()
            self._cv.notify_all()

    def status(self):
        with self._cv:
            return {"state": self._state, "reason": self._reason, "iface": self._used_iface}

    def close(self):
        with self._cv:
            self._stop = True
            self._cv.notify_all()
        self._kill()

    # ---- internals -----------------------------------------------------------
    def _set(self, state, reason=None):
        with self._cv:
            self._state, self._reason = state, reason

    @staticmethod
    def _signal(p, sig):
        """Signal tshark and anything it spawned (dumpcap) via its process group."""
        try:
            os.killpg(p.pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                p.send_signal(sig)
            except OSError:
                pass

    def _kill(self):
        p, self._proc = self._proc, None
        if p and p.poll() is None:
            self._signal(p, signal.SIGTERM)
            try:
                p.wait(3)
            except subprocess.TimeoutExpired:
                self._signal(p, signal.SIGKILL)

    def _fan_out(self, row):
        with self._cv:
            subs = list(self._subs)
        for s in subs:
            s.push(row)

    def _wait_subscribers(self):
        with self._cv:
            while not self._subs and not self._stop:
                self._state = "idle"
                self._cv.wait()
            if self._stop:
                return False
            if self._state == "idle":
                self._state = "starting"
        return True

    def _watchdog(self, p):
        """Stops tshark once nobody has been watching for a while."""
        while p.poll() is None:
            with self._cv:
                if self._stop:
                    break
                idle = not self._subs and time.monotonic() - self._empty_since > self._idle_stop
                if not idle:
                    self._cv.wait(1.0)
                    continue
            break
        if p.poll() is None:
            self._signal(p, signal.SIGTERM)

    def _run(self):
        while True:
            if not self._wait_subscribers():
                return
            exe = shutil.which(self._tshark)
            if not exe:
                self._set("offline", "tshark is not installed")
                self._sleep_retry(15)
                continue
            iface = self._iface or default_iface() or "any"
            cmd = build_cmd(exe, iface, self._filter, self._variant)
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, bufsize=1, errors="replace",
                                     start_new_session=True)
            except OSError as e:
                self._set("offline", "cannot start tshark: %s" % e.strerror)
                self._sleep_retry(15)
                continue
            self._proc, self._used_iface = p, iface
            err = deque(maxlen=30)
            threading.Thread(target=lambda: [err.append(x.strip()) for x in p.stderr],
                             daemon=True).start()
            threading.Timer(1.5, lambda: self._set("live") if p.poll() is None else None).start()
            threading.Thread(target=self._watchdog, args=(p,), daemon=True).start()
            for line in p.stdout:
                row = parse_line(line)
                if row:
                    self._fan_out(row)
            p.wait()
            self._proc = None
            with self._cv:
                if self._stop:
                    return
                had_subs = bool(self._subs)
            text = " ".join(err).lower()
            if "not a valid field" in text or "isn't a valid" in text or "some fields aren't valid" in text:
                self._variant = "lower" if self._variant == "upper" else "upper"
                continue
            if had_subs:
                self._set("offline", self._reason_from(text))
                self._sleep_retry(10)
            else:
                self._set("idle")

    @staticmethod
    def _reason_from(text):
        if "permission" in text or "don't have permission" in text or "operation not permitted" in text:
            return "no capture permission"
        if "no such device" in text or "no interfaces" in text:
            return "capture interface not found"
        return "capture stopped"

    def _sleep_retry(self, secs):
        end = time.monotonic() + secs
        with self._cv:
            while not self._stop and self._subs and time.monotonic() < end:
                self._cv.wait(0.5)
