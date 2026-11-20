"""Password storage (argon2), server-side sessions and login lockout."""
import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MAX_PW = 256
COOKIE = "dk_sid"


class AuthStore:
    def __init__(self, state_dir, *, min_password=10, max_fails=5, lock_secs=300,
                 idle_secs=12 * 3600, absolute_secs=7 * 86400, clock=time.time):
        self.path = Path(state_dir) / "auth.json"
        self.min_password = min_password
        self.max_fails = max_fails
        self.lock_secs = lock_secs
        self.idle_secs = idle_secs
        self.absolute_secs = absolute_secs
        self.clock = clock
        self._lock = threading.RLock()
        self._ph = PasswordHasher()
        self._sessions = {}          # sha256(token) -> {created,last,ip}
        self._fails = {}             # ip -> {"n","until","level","last"}
        self._hash = self._load()

    # ---- persistence -------------------------------------------------------
    def _load(self):
        try:
            return json.loads(self.path.read_text()).get("hash") or None
        except (OSError, ValueError):
            return None

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"hash": self._hash, "updated": int(self.clock())}, f)
        os.replace(tmp, self.path)

    # ---- password ----------------------------------------------------------
    def needs_setup(self):
        return not self._hash

    def validate_new(self, pw):
        if not isinstance(pw, str) or len(pw) < self.min_password:
            return "MIN %d CHARS" % self.min_password
        if len(pw) > MAX_PW:
            return "TOO LONG"
        return None

    def set_password(self, pw, *, only_if_unset=False):
        """Returns True if stored. only_if_unset makes first-run atomic."""
        with self._lock:
            if only_if_unset and self._hash:
                return False
            self._hash = self._ph.hash(pw)
            self._save()
            return True

    def verify(self, pw):
        with self._lock:
            h = self._hash
        if not h or not isinstance(pw, str) or len(pw) > MAX_PW:
            return False
        try:
            self._ph.verify(h, pw)
        except (VerificationError, InvalidHashError):
            return False
        if self._ph.check_needs_rehash(h):
            self.set_password(pw)
        return True

    # ---- lockout -----------------------------------------------------------
    def locked_for(self, ip):
        with self._lock:
            f = self._fails.get(ip)
            if not f:
                return 0
            return max(0, int(f["until"] - self.clock() + 0.999))

    def record_fail(self, ip):
        """Returns (seconds_locked_now, attempts_left)."""
        with self._lock:
            now = self.clock()
            self._prune(now)
            f = self._fails.setdefault(ip, {"n": 0, "until": 0, "level": 0, "last": now})
            f["n"] += 1
            f["last"] = now
            if f["n"] >= self.max_fails:
                secs = min(self.lock_secs * (2 ** f["level"]), 3600)
                f["until"] = now + secs
                f["level"] += 1
                f["n"] = 0
                return int(secs), 0
            return 0, self.max_fails - f["n"]

    def record_success(self, ip):
        with self._lock:
            self._fails.pop(ip, None)

    def _prune(self, now):
        for ip in [k for k, f in self._fails.items() if f["until"] < now and now - f["last"] > 3600]:
            del self._fails[ip]

    # ---- sessions ----------------------------------------------------------
    @staticmethod
    def _key(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def create_session(self, ip):
        token = secrets.token_urlsafe(32)
        now = self.clock()
        with self._lock:
            self._sessions[self._key(token)] = {"created": now, "last": now, "ip": ip}
        return token

    def valid(self, token, touch=True):
        if not token:
            return False
        k = self._key(token)
        with self._lock:
            s = self._sessions.get(k)
            if not s:
                return False
            now = self.clock()
            if now - s["last"] > self.idle_secs or now - s["created"] > self.absolute_secs:
                del self._sessions[k]
                return False
            if touch:
                s["last"] = now
            return True

    def destroy(self, token):
        if token:
            with self._lock:
                self._sessions.pop(self._key(token), None)

    def destroy_all_except(self, token=None):
        keep = self._key(token) if token else None
        with self._lock:
            for k in [k for k in self._sessions if k != keep]:
                del self._sessions[k]
