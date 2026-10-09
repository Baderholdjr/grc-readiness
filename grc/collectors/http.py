"""Tiny JSON-over-HTTPS client (stdlib only) with retries."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request


class HTTPError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message[:200]}")
        self.status = status


def request(method: str, url: str, headers: dict | None = None, params: dict | None = None,
            body: dict | None = None, retries: int = 3, timeout: int = 60):
    from .. import sandbox
    canned = sandbox.handle(method, url, params, body)
    if canned is not sandbox.NOT_HANDLED:
        return canned
    if params:
        pairs = []
        for k, v in params.items():
            if v is None:
                continue
            for item in (v if isinstance(v, (list, tuple)) else [v]):
                pairs.append((k, str(item).lower() if isinstance(item, bool) else str(item)))
        url = f"{url}{'&' if '?' in url else '?'}{urllib.parse.urlencode(pairs)}"
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method=method)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504, 529) and attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise HTTPError(exc.code, exc.read().decode(errors="replace")) from None
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise
