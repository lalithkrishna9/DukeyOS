"""Allow-listed client for the local dukeyos-gateway (which fronts app-management).

The dashboard is the only caller. The gateway listens on loopback only and
trusts loopback callers (same as every stock internal service), so no token is
needed; if one is ever demanded (HTTP 401) and service credentials are
configured we log in once and retry."""
import re
import threading
import time
from urllib.parse import unquote

import requests

ALLOWED_PREFIXES = ("v2/app_management/",)
ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE"}
FORWARD_HEADERS = ("Content-Type", "Accept")


class GatewayError(Exception):
    pass


class PathNotAllowed(GatewayError):
    pass


def valid_path(path):
    """Only plain paths under an allowed prefix; no traversal, no encoded tricks."""
    if not path or "\\" in path or "\x00" in path:
        return False
    for form in (path, unquote(path), unquote(unquote(path))):
        if any(seg in (".", "..") for seg in form.split("/")):
            return False
    return path.startswith(ALLOWED_PREFIXES)


class Gateway:
    def __init__(self, settings):
        self.s = settings
        self._url_cache = (0.0, None)
        self._token = (0.0, None)
        self._lock = threading.Lock()

    def base_url(self):
        if self.s.gateway_url:
            return self.s.gateway_url.rstrip("/")
        ts, url = self._url_cache
        if url and time.monotonic() - ts < 30:
            return url
        port = "80"
        try:
            sect = ""
            for ln in self.s.gateway_ini.read_text().splitlines():
                ln = ln.strip()
                m = re.match(r"^\[(.+)\]$", ln)
                if m:
                    sect = m.group(1).lower()
                elif sect == "gateway" and ln.lower().startswith("port"):
                    v = ln.split("=", 1)[-1].strip()
                    if v.isdigit():
                        port = v
        except OSError:
            pass
        url = "http://127.0.0.1:%s" % port
        self._url_cache = (time.monotonic(), url)
        return url

    def _login(self):
        if not (self.s.svc_user and self.s.svc_pass):
            return None
        with self._lock:
            ts, tok = self._token
            if tok and time.monotonic() - ts < 3000:
                return tok
            try:
                r = requests.post(self.base_url() + "/v1/users/login", timeout=5,
                                  json={"username": self.s.svc_user, "password": self.s.svc_pass})
                tok = r.json()["data"]["token"]["access_token"]
            except (requests.RequestException, KeyError, ValueError, TypeError):
                return None
            self._token = (time.monotonic(), tok)
            return tok

    def request(self, method, path, *, params=None, data=None, headers=None, timeout=60):
        if method not in ALLOWED_METHODS or not valid_path(path):
            raise PathNotAllowed("path not allowed")
        hdrs = {k: v for k, v in (headers or {}).items() if k in FORWARD_HEADERS and v}
        url = "%s/%s" % (self.base_url(), path)
        try:
            tok = self._token[1]
            r = requests.request(method, url, params=params, data=data, timeout=timeout,
                                 headers=dict(hdrs, **({"Authorization": tok} if tok else {})))
            if r.status_code == 401:
                tok = self._login()
                if tok:
                    r = requests.request(method, url, params=params, data=data, timeout=timeout,
                                         headers=dict(hdrs, Authorization=tok))
            return r
        except requests.RequestException as e:
            raise GatewayError(str(e)) from e
