"""Plan 91 Phase 3.4 — apply_site_resolver network layer via MockTransport.

`test_apply_site_resolver.py` wholesale-AsyncMocks `_fetch` /
`_redirect_probe`, so the actual network behaviours — HEAD→GET fallback,
manual redirect walking with relative-Location joins, the redirect budget,
and per-hop SSRF re-checks — were untested. These run the real functions
over `httpx.MockTransport`; DNS is the only thing faked
(`scraper.url_guard._resolve_host`), so `is_safe_destination` itself runs.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from services import apply_site_resolver as resolver

_PUBLIC_IP = "93.184.216.34"


def _mock_client_factory(handler):
    """Replacement for httpx.AsyncClient that injects a MockTransport."""
    real = httpx.AsyncClient

    def make(**kw):
        kw.pop("transport", None)
        return real(transport=httpx.MockTransport(handler), **kw)

    return make


def _public_dns(monkeypatch, mapping=None):
    """Fake DNS only: every host resolves public unless mapping says otherwise."""
    from scraper import url_guard

    def fake_resolve(host):
        if mapping and host in mapping:
            return [mapping[host]]
        return [_PUBLIC_IP]

    monkeypatch.setattr(url_guard, "_resolve_host", fake_resolve)


# ── _fetch ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_returns_terminal_response(monkeypatch):
    _public_dns(monkeypatch)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"jobs": []})

    with patch("httpx.AsyncClient", new=_mock_client_factory(handler)):
        resp = await resolver._fetch("https://boards-api.greenhouse.io/v1/boards/acme/jobs")

    assert resp is not None and resp.status_code == 200
    assert seen == ["https://boards-api.greenhouse.io/v1/boards/acme/jobs"]
    assert resp.request.headers["Accept"] == "application/json"


@pytest.mark.asyncio
async def test_fetch_follows_relative_redirect_manually(monkeypatch):
    """302 with a RELATIVE Location is joined against the current URL and the
    walk continues; the terminal 404 comes back as-is (caller classifies)."""
    _public_dns(monkeypatch)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path == "/old":
            return httpx.Response(302, headers={"location": "/new"})
        return httpx.Response(404)

    with patch("httpx.AsyncClient", new=_mock_client_factory(handler)):
        resp = await resolver._fetch("https://api.lever.co/old")

    assert resp is not None and resp.status_code == 404
    assert seen == ["https://api.lever.co/old", "https://api.lever.co/new"]


@pytest.mark.asyncio
async def test_fetch_redirect_without_location_returns_none(monkeypatch):
    _public_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302)  # no Location header

    with patch("httpx.AsyncClient", new=_mock_client_factory(handler)):
        assert await resolver._fetch("https://api.lever.co/x") is None


@pytest.mark.asyncio
async def test_fetch_gives_up_after_redirect_budget(monkeypatch):
    """An endless redirect loop stops at _MAX_REDIRECTS+1 requests → None."""
    _public_dns(monkeypatch)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        nxt = int(request.url.path.strip("/") or 0) + 1
        return httpx.Response(302, headers={"location": f"/{nxt}"})

    with patch("httpx.AsyncClient", new=_mock_client_factory(handler)):
        assert await resolver._fetch("https://api.lever.co/0") is None
    assert len(seen) == resolver._MAX_REDIRECTS + 1


@pytest.mark.asyncio
async def test_fetch_blocks_private_destination_before_any_request(monkeypatch):
    _public_dns(monkeypatch, mapping={"internal.example": "10.0.0.5"})
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        seen.append(str(request.url))
        return httpx.Response(200)

    with patch("httpx.AsyncClient", new=_mock_client_factory(handler)):
        assert await resolver._fetch("https://internal.example/api") is None
    assert seen == []  # never touched the wire


@pytest.mark.asyncio
async def test_fetch_rechecks_ssrf_on_every_hop(monkeypatch):
    """A public host 302ing onto a private one is cut off mid-walk."""
    _public_dns(monkeypatch, mapping={"metadata.internal": "169.254.169.254"})
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://metadata.internal/creds"})

    with patch("httpx.AsyncClient", new=_mock_client_factory(handler)):
        assert await resolver._fetch("https://api.lever.co/x") is None
    assert seen == ["https://api.lever.co/x"]  # the private hop was never requested


@pytest.mark.asyncio
async def test_fetch_propagates_transport_errors_to_caller(monkeypatch):
    """_fetch doesn't swallow httpx errors — its callers do."""
    _public_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow upstream")

    with patch("httpx.AsyncClient", new=_mock_client_factory(handler)):
        with pytest.raises(httpx.ConnectTimeout):
            await resolver._fetch("https://api.lever.co/x")


# ── _redirect_probe ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_redirect_probe_uses_head_when_supported():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(302, headers={"location": "https://x.example/next"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        resp = await resolver._redirect_probe(client, "https://x.example/a", {})

    assert resp is not None and resp.status_code == 302
    assert calls == ["HEAD"]  # no GET needed


@pytest.mark.asyncio
@pytest.mark.parametrize("head_status", [405, 501])
async def test_redirect_probe_falls_back_to_get_on_method_not_allowed(head_status):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "HEAD":
            return httpx.Response(head_status)
        return httpx.Response(302, headers={"location": "https://x.example/next"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        resp = await resolver._redirect_probe(client, "https://x.example/a", {})

    assert resp is not None and resp.status_code == 302
    assert calls == ["HEAD", "GET"]


@pytest.mark.asyncio
async def test_redirect_probe_falls_back_to_get_when_head_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            raise httpx.ConnectError("HEAD refused")
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        resp = await resolver._redirect_probe(client, "https://x.example/a", {})

    assert resp is not None and resp.status_code == 200


@pytest.mark.asyncio
async def test_redirect_probe_returns_none_when_both_methods_fail():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("nobody home")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await resolver._redirect_probe(client, "https://x.example/a", {}) is None


# ── normalize_apply_url over the real transport stack ───────────────────


@pytest.mark.asyncio
async def test_normalize_apply_url_end_to_end_over_transport(monkeypatch):
    """careers page → 302 → Workday: probe + join + classify, all real."""
    _public_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "careers.acme.com":
            return httpx.Response(
                302, headers={"location": "https://acme.wd5.myworkdayjobs.com/en-US/j/1"}
            )
        return httpx.Response(200)

    with patch("httpx.AsyncClient", new=_mock_client_factory(handler)):
        final, kind = await resolver.normalize_apply_url("https://careers.acme.com/j/1")

    assert final == "https://acme.wd5.myworkdayjobs.com/en-US/j/1"
    assert kind == "workday"
