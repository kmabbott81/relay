from __future__ import annotations

import json


def make_httpx_mock(json_payload: dict, status_code: int = 200):
    """Create an httpx MockTransport handler if httpx is available."""
    try:
        import httpx
    except ImportError:
        return None

    def handler(request: httpx.Request) -> httpx.Response:  # type: ignore
        return httpx.Response(
            status_code,
            request=request,
            content=json.dumps(json_payload).encode("utf-8"),
            headers={"content-type": "application/json"},
        )

    return handler


def install_httpx_transport(monkeypatch, handler):
    """Install httpx MockTransport for all httpx clients."""
    import httpx

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: httpx.Client(transport=transport))
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: httpx.AsyncClient(transport=transport))


def install_requests_fake(monkeypatch, json_payload: dict, status_code: int = 200):
    """Install a fake requests.Session.request method for mocking HTTP calls."""
    import requests

    def _fake(self, method, url, **kwargs):
        class R:
            def __init__(self):
                self.status_code = status_code
                self._json = json_payload
                self.text = json.dumps(json_payload)

            def json(self):
                return self._json

            def raise_for_status(self):
                if not (200 <= self.status_code < 400):
                    raise requests.HTTPError(f"{self.status_code}")

        return R()

    monkeypatch.setattr("requests.Session.request", _fake, raising=True)
