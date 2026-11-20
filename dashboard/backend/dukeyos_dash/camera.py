"""Server-side webcam (the camera physically attached to the DukeyOS host).

* Auto-detects /dev/video* capture nodes (built-in or USB); nothing hard-coded.
* Prefers the most recently connected device; follows hot-plug / unplug.
* The device is only opened while somebody is watching (LED off, no CPU when idle).
* One capture thread encodes each frame once; any number of MJPEG viewers share it.
* No camera / unreadable device -> status online=False (UI shows OFFLINE)."""
import glob
import os
import re
import threading
import time
from collections import namedtuple

Device = namedtuple("Device", "path name index ctime")


def scan_devices():
    """List usable capture nodes. UVC cameras expose a second *metadata* node
    (sysfs index>0) that can never stream; it is skipped."""
    out = []
    for path in glob.glob("/dev/video*"):
        m = re.fullmatch(r"/dev/video(\d+)", path)
        if not m:
            continue
        n = int(m.group(1))
        sys = "/sys/class/video4linux/video%d" % n
        try:
            if int(open(sys + "/index").read().strip() or 0) != 0:
                continue
        except (OSError, ValueError):
            pass
        try:
            name = open(sys + "/name").read().strip()
        except OSError:
            name = "video%d" % n
        try:
            ctime = os.stat(path).st_ctime
        except OSError:
            continue
        if not os.access(path, os.R_OK):
            continue
        out.append(Device(path, name, n, ctime))
    return out


class _CvCapture:
    """Thin OpenCV wrapper: opens a V4L2 node and returns JPEG bytes."""

    def __init__(self, path, width=320, quality=70):
        import cv2
        self.cv2 = cv2
        self.width, self.quality = width, quality
        self.cap = cv2.VideoCapture(path, cv2.CAP_V4L2)
        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, 15)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def opened(self):
        return self.cap.isOpened()

    def read_jpeg(self):
        ok, frame = self.cap.read()
        if not ok or frame is None:
            return None
        h, w = frame.shape[:2]
        if w > self.width:
            frame = self.cv2.resize(frame, (self.width, int(h * self.width / w)))
        ok, buf = self.cv2.imencode(".jpg", frame, [self.cv2.IMWRITE_JPEG_QUALITY, self.quality])
        return buf.tobytes() if ok else None

    def release(self):
        self.cap.release()


class CameraService:
    def __init__(self, *, scan=scan_devices, opener=_CvCapture, forced=None, fps=12,
                 idle_release=6.0, rescan_every=4.0, broken_retry=20.0):
        self._scan, self._opener, self._forced = scan, opener, forced
        self._min_interval = 1.0 / fps
        self._idle_release, self._rescan_every, self._broken_retry = idle_release, rescan_every, broken_retry
        self._cv = threading.Condition()
        self._dlock = threading.Lock()    # guards _seen/_broken
        self._viewers = 0
        self._idle_since = time.monotonic()
        self._frame, self._seq, self._frame_ts = None, 0, 0.0
        self._dev = None                  # Device currently streaming
        self._seen = {}                   # path -> first-seen order key
        self._broken = {}                 # path -> time it failed
        self._started = time.monotonic()
        self._thread = None
        self._stop = False
        self.reason = None

    # ---- device selection ----------------------------------------------------
    def candidates(self):
        """Usable devices, most recently connected first."""
        with self._dlock:
            return self._candidates()

    def _candidates(self):
        if self._forced:
            devs = [Device(self._forced, os.path.basename(self._forced), 0, 0.0)] \
                if os.path.exists(self._forced) else []
        else:
            devs = list(self._scan())
        now = time.monotonic()
        paths = {d.path for d in devs}
        for p in list(self._seen):
            if p not in paths:
                del self._seen[p]
        for d in devs:
            # devices present at start-up share order 0 (then ctime/index decide);
            # anything that shows up later is "newer" by the time we noticed it
            self._seen.setdefault(d.path, 0.0 if now - self._started < 3 else now)
        for p in list(self._broken):
            if now - self._broken[p] > self._broken_retry or p not in paths:
                del self._broken[p]
        devs = [d for d in devs if d.path not in self._broken]
        devs.sort(key=lambda d: (self._seen.get(d.path, 0.0), d.ctime, d.index), reverse=True)
        return devs

    def status(self):
        with self._cv:
            streaming = self._dev is not None and time.monotonic() - self._frame_ts < 5
            dev = self._dev
        if streaming:
            return {"online": True, "name": dev.name, "device": dev.path, "streaming": True}
        try:
            cands = self.candidates()
        except Exception:
            cands = []
        if cands:
            return {"online": True, "name": cands[0].name, "device": cands[0].path, "streaming": False}
        return {"online": False, "name": None, "device": None, "streaming": False,
                "reason": self.reason or "no camera detected"}

    # ---- capture thread ------------------------------------------------------
    def _ensure_thread(self):
        with self._cv:
            if self._thread and self._thread.is_alive():
                return
            self._stop = False
            self._thread = threading.Thread(target=self._run, name="camera", daemon=True)
            self._thread.start()

    def close(self):
        with self._cv:
            self._stop = True
            self._cv.notify_all()

    def _open_best(self):
        for d in self.candidates():
            try:
                cap = self._opener(d.path)
                if cap.opened():
                    return cap, d
                cap.release()
            except Exception as e:                       # e.g. OpenCV missing
                self.reason = "capture failed: %s" % e.__class__.__name__
            self._mark_broken(d.path)
        return None, None

    def _mark_broken(self, path):
        with self._dlock:
            self._broken[path] = time.monotonic()

    def _set_dev(self, dev):
        with self._cv:
            self._dev = dev
            if dev is None:
                self._frame = None
            self._cv.notify_all()

    def _run(self):
        cap, dev, bad, last_scan = None, None, 0, 0.0
        while True:
            with self._cv:
                if self._stop:
                    break
                if self._viewers == 0:
                    if cap and time.monotonic() - self._idle_since >= self._idle_release:
                        cap.release()
                        cap, dev = None, None
                        self._dev, self._frame = None, None
                    self._cv.wait(1.0)
                    if self._viewers == 0:
                        continue
            if cap is None:
                cap, dev = self._open_best()
                bad, last_scan = 0, time.monotonic()
                if cap is None:
                    self._set_dev(None)
                    with self._cv:
                        self._cv.wait(2.0)
                    continue
                self._set_dev(dev)
            now = time.monotonic()
            if not self._forced and now - last_scan > self._rescan_every:
                last_scan = now
                cands = self.candidates()
                if not cands or cands[0].path != dev.path:      # unplugged, or a newer cam appeared
                    cap.release()
                    cap, dev = None, None
                    continue
            t0 = time.monotonic()
            try:
                jpg = cap.read_jpeg()
            except Exception:
                jpg = None
            if jpg is None:
                bad += 1
                if bad >= 8:
                    self._mark_broken(dev.path)
                    cap.release()
                    cap, dev = None, None
                    self._set_dev(None)
                time.sleep(0.2)
                continue
            bad = 0
            with self._cv:
                self._frame, self._frame_ts = jpg, time.monotonic()
                self._seq += 1
                self._cv.notify_all()
            spare = self._min_interval - (time.monotonic() - t0)
            if spare > 0:
                time.sleep(spare)
        if cap:
            cap.release()

    # ---- viewers -------------------------------------------------------------
    def _viewer(self, delta):
        with self._cv:
            self._viewers = max(0, self._viewers + delta)
            if self._viewers == 0:
                self._idle_since = time.monotonic()
            self._cv.notify_all()

    def stream(self, give_up_after=10.0):
        """Generator of multipart/x-mixed-replace chunks. Ends if the camera
        stays offline so the browser's <img> errors and the UI shows OFFLINE."""
        self._ensure_thread()
        self._viewer(+1)
        try:
            last, waited = -1, 0.0
            while True:
                with self._cv:
                    if self._stop:
                        return
                    if self._seq == last or self._frame is None:
                        t0 = time.monotonic()
                        self._cv.wait(2.0)
                        waited += time.monotonic() - t0
                    frame, seq = self._frame, self._seq
                if frame is not None and seq != last:
                    last, waited = seq, 0.0
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                           + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
                elif waited >= give_up_after:
                    return
        finally:
            self._viewer(-1)
