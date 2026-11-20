"""System statistics: one shared 1 Hz sampler (psutil) + network helpers."""
import os
import socket
import threading
import time

import psutil

_VIRTUAL_PREFIXES = ("lo", "docker", "veth", "br-", "virbr", "tun", "tap", "dummy",
                     "tailscale", "wg", "zt", "ifb", "bond")


def physical_nics():
    """NICs whose byte counters represent real traffic (no loopback/docker/overlay,
    which would double count)."""
    names = list(psutil.net_io_counters(pernic=True))
    if os.path.isdir("/sys/class/net"):
        phys = [n for n in names if os.path.exists("/sys/class/net/%s/device" % n)]
        if phys:
            return phys
    return [n for n in names if not n.startswith(_VIRTUAL_PREFIXES)]


def default_iface():
    """Interface of the default IPv4 route (lowest metric), or None."""
    best = None
    try:
        with open("/proc/net/route") as f:
            next(f, None)
            for ln in f:
                p = ln.split()
                if len(p) >= 8 and p[1] == "00000000" and int(p[3], 16) & 2:
                    metric = int(p[6])
                    if best is None or metric < best[0]:
                        best = (metric, p[0])
    except (OSError, ValueError):
        pass
    return best[1] if best else None


def primary_ipv4():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("1.1.1.1", 53))          # UDP connect: no packet is sent
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        pass
    for name, addrs in psutil.net_if_addrs().items():
        if name.startswith(_VIRTUAL_PREFIXES):
            continue
        for a in addrs:
            if a.family == socket.AF_INET and not a.address.startswith("127."):
                return a.address
    return None


def vpn_ipv4():
    for name, addrs in psutil.net_if_addrs().items():
        if name.startswith(("tailscale", "wg")):
            for a in addrs:
                if a.family == socket.AF_INET:
                    return a.address
    return None


def cpu_temp():
    try:
        temps = psutil.sensors_temperatures()
    except (AttributeError, OSError):
        return None
    vals = []
    for key in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
        vals = [t.current for t in temps.get(key, []) if t.current]
        if vals:
            break
    return round(max(vals), 1) if vals else None


class Stats:
    def __init__(self, data_path="/DATA", interval=1.0):
        self.data_path = data_path
        self.interval = interval
        self._cv = threading.Condition()
        self._latest = None
        self._seq = 0
        self._thread = None
        self._net_prev = None
        self._procs_cache = (0.0, [])
        self._net_cache = (0.0, None)
        self.hostname = socket.gethostname()

    # ---- sampler -----------------------------------------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        psutil.cpu_percent(percpu=True)          # prime: first reading is meaningless
        self._thread = threading.Thread(target=self._run, name="stats", daemon=True)
        self._thread.start()

    def _run(self):
        while True:
            try:
                s = self.sample()
                with self._cv:
                    self._latest, self._seq = s, self._seq + 1
                    self._cv.notify_all()
            except Exception:       # never let the sampler die
                pass
            time.sleep(self.interval)

    def sample(self):
        per = psutil.cpu_percent(percpu=True)
        vm = psutil.virtual_memory()
        now = time.monotonic()
        nics = physical_nics()
        counters = psutil.net_io_counters(pernic=True)
        rx = sum(counters[n].bytes_recv for n in nics if n in counters)
        tx = sum(counters[n].bytes_sent for n in nics if n in counters)
        rx_rate = tx_rate = 0.0
        if self._net_prev:
            dt = max(now - self._net_prev[0], 1e-3)
            rx_rate = max(0.0, (rx - self._net_prev[1]) / dt)
            tx_rate = max(0.0, (tx - self._net_prev[2]) / dt)
        self._net_prev = (now, rx, tx)
        try:
            du = psutil.disk_usage(self.data_path if os.path.isdir(self.data_path) else "/")
            disk = {"percent": du.percent, "free": du.free, "total": du.total}
        except OSError:
            disk = None
        try:
            load = os.getloadavg()[0]
        except (OSError, AttributeError):
            load = None
        return {
            "t": time.time(),
            "cpu": round(sum(per) / len(per), 1) if per else 0.0,
            "cores": [round(c, 1) for c in per],
            "ram": vm.percent, "ram_used": vm.used, "ram_total": vm.total,
            "rx": round(rx_rate), "tx": round(tx_rate),
            "temp": cpu_temp(),
            "uptime": int(time.time() - psutil.boot_time()),
            "host": self.hostname,
            "disk": disk, "load": load,
        }

    def latest(self):
        with self._cv:
            return self._latest or self.sample()

    def wait_next(self, last_seq, timeout=3.0):
        """Block until a sample newer than last_seq exists. Returns (seq, sample)."""
        with self._cv:
            if self._seq == last_seq:
                self._cv.wait(timeout)
            return self._seq, self._latest

    # ---- process list (computed on demand, cached 2 s) ---------------------
    def processes(self, n=12):
        ts, cached = self._procs_cache
        if time.monotonic() - ts < 2.0:
            return cached
        rows = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            i = p.info
            rows.append({"pid": i["pid"], "name": i["name"] or "?",
                         "cpu": round(i["cpu_percent"] or 0.0, 1),
                         "mem": round(i["memory_percent"] or 0.0, 1)})
        rows.sort(key=lambda r: (r["cpu"], r["mem"]), reverse=True)
        rows = rows[:n]
        self._procs_cache = (time.monotonic(), rows)
        return rows

    # ---- network status (cached 5 s so viewers don't multiply probes) ------
    def netinfo(self):
        ts, cached = self._net_cache
        if cached and time.monotonic() - ts < 5.0:
            return cached
        ping = None
        for host in (("1.1.1.1", 53), ("8.8.8.8", 53)):
            t0 = time.perf_counter()
            try:
                socket.create_connection(host, timeout=1.5).close()
                ping = round((time.perf_counter() - t0) * 1000)
                break
            except OSError:
                continue
        info = {"online": ping is not None, "ping": ping,
                "ipv4": primary_ipv4(), "vpn": vpn_ipv4(), "iface": default_iface()}
        self._net_cache = (time.monotonic(), info)
        return info
