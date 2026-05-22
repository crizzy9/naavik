"""Plan 64 / 0.2.7.11 — `scraper.proxy` resolver + Pydantic + redaction tests.

Pure-function tests; no DB, no fixtures, no Crawl4AI mock. Covers:

- `ProxyURLConfig` validator: 12 cases (http / https / socks5 / IPv4 / IPv6 /
  Basic-auth / no-auth / unsupported-scheme / missing-host / port-OOR /
  query-rejected / fragment-rejected).
- `resolve_proxy_config` resolver: LinkedIn-env-set / LinkedIn-env-unset /
  non-LinkedIn-source.
- `safe_proxy_host` redaction: 5 cases.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models import JobSource
from scraper.proxy import ProxyURLConfig, resolve_proxy_config, safe_proxy_host

pytestmark = pytest.mark.uses_sample_data_shims

# ── ProxyURLConfig validator ──────────────────────────────────────────────


class TestProxyURLConfigValidator:
    def test_http_basic_auth_accepted(self):
        c = ProxyURLConfig(url="http://user:pass@gate.example.com:7000")
        assert c.url == "http://user:pass@gate.example.com:7000"

    def test_https_basic_auth_accepted(self):
        c = ProxyURLConfig(url="https://u:p@proxy.brightdata.com:33335")
        assert c.url.startswith("https://")

    def test_socks5_accepted(self):
        c = ProxyURLConfig(url="socks5://user:pass@geo.iproyal.com:12321")
        assert c.url.startswith("socks5://")

    def test_no_auth_accepted(self):
        c = ProxyURLConfig(url="http://gate.example.com:7000")
        assert c.url == "http://gate.example.com:7000"

    def test_ipv4_host_accepted(self):
        c = ProxyURLConfig(url="http://203.0.113.1:8080")
        assert c.url == "http://203.0.113.1:8080"

    def test_ipv6_bracketed_host_accepted(self):
        c = ProxyURLConfig(url="http://[2001:db8::1]:7000")
        assert c.url.startswith("http://")

    def test_basic_auth_with_url_encoded_chars_accepted(self):
        # Provider passwords often contain special chars; pre-encoded is fine.
        c = ProxyURLConfig(url="http://user-session-XYZ:pass%21word@gate.smartproxy.com:7000")
        assert "%21" in c.url

    @pytest.mark.parametrize(
        "bad_scheme",
        [
            "javascript:alert(1)",
            "file:///etc/passwd",
            "ftp://user:pass@host:21",
            "data:text/plain,bad",
            "gopher://x:6379/_INFO",
        ],
    )
    def test_unsupported_scheme_rejected(self, bad_scheme: str):
        with pytest.raises(ValidationError):
            ProxyURLConfig(url=bad_scheme)

    def test_missing_host_rejected(self):
        # Scheme present but no host segment.
        with pytest.raises(ValidationError):
            ProxyURLConfig(url="http://:7000")

    def test_missing_port_rejected(self):
        with pytest.raises(ValidationError):
            ProxyURLConfig(url="http://gate.example.com")

    def test_port_out_of_range_rejected(self):
        # urlsplit raises ValueError on >65535, which our validator converts.
        with pytest.raises(ValidationError):
            ProxyURLConfig(url="http://gate.example.com:99999")

    def test_query_string_rejected(self):
        with pytest.raises(ValidationError):
            ProxyURLConfig(url="http://gate.example.com:7000?session=abc")

    def test_fragment_rejected(self):
        with pytest.raises(ValidationError):
            ProxyURLConfig(url="http://gate.example.com:7000#section")

    def test_provider_hint_optional(self):
        c = ProxyURLConfig(url="http://x:y@gate.example.com:7000")
        assert c.provider_hint is None

    def test_provider_hint_capped_at_64_chars(self):
        with pytest.raises(ValidationError):
            ProxyURLConfig(
                url="http://x:y@gate.example.com:7000",
                provider_hint="x" * 65,
            )

    def test_to_crawl4ai_returns_proxy_config(self):
        c = ProxyURLConfig(url="http://user:pass@gate.example.com:7000")
        pc = c.to_crawl4ai()
        # Crawl4AI's ProxyConfig exposes the server URL via .server.
        assert pc.server == "http://gate.example.com:7000"
        assert pc.username == "user"
        assert pc.password == "pass"

    # ── Plan 64 PR #165 delta-fix LOW-2: reject degenerate userinfo ──────

    def test_empty_password_in_userinfo_rejected(self):
        """`user:@host:port` — empty password after the colon."""
        with pytest.raises(ValidationError):
            ProxyURLConfig(url="http://user:@gate.example.com:7000")

    def test_empty_username_in_userinfo_rejected(self):
        """`:pass@host:port` — empty username before the colon."""
        with pytest.raises(ValidationError):
            ProxyURLConfig(url="http://:pass@gate.example.com:7000")

    # ── Plan 64 PR #165 delta-fix LOW-1: __repr__ must not leak creds ────

    def test_repr_does_not_expose_basic_auth_credentials(self):
        """`repr(cfg)` must NOT contain `user:pass`.

        Pydantic's default repr re-emits every field value. If any future log
        site does `log.warning("config: %r", cfg)` the credentials leak. The
        override produces host:port-only via `safe_proxy_host`.
        """
        c = ProxyURLConfig(url="http://verysecretuser:verysecretpass@gate.example.com:7000")
        r = repr(c)
        assert "verysecretuser" not in r
        assert "verysecretpass" not in r
        # But the safe form IS in the repr.
        assert "gate.example.com:7000" in r

    def test_repr_includes_provider_hint(self):
        c = ProxyURLConfig(
            url="http://user:pass@gate.example.com:7000",
            provider_hint="smartproxy",
        )
        r = repr(c)
        assert "smartproxy" in r
        assert "user" not in r
        assert "pass" not in r

    def test_repr_shape_is_stable(self):
        """The repr shape stays human-readable for forensics."""
        c = ProxyURLConfig(url="http://u:p@gate.example.com:7000")
        r = repr(c)
        assert r.startswith("ProxyURLConfig(")
        assert "url=" in r
        assert "provider_hint=" in r


# ── safe_proxy_host redaction ─────────────────────────────────────────────


class TestSafeProxyHost:
    def test_basic_auth_stripped(self):
        assert (
            safe_proxy_host("http://leakeduser:leakedpassword@gate.example.com:7000")
            == "gate.example.com:7000"
        )

    def test_no_auth_preserves_host(self):
        assert safe_proxy_host("http://gate.example.com:7000") == "gate.example.com:7000"

    def test_unusual_port_preserved(self):
        assert safe_proxy_host("http://x:y@brd.superproxy.io:33335") == "brd.superproxy.io:33335"

    def test_socks5_scheme_stripped_host_kept(self):
        assert safe_proxy_host("socks5://u:p@geo.iproyal.com:12321") == "geo.iproyal.com:12321"

    def test_none_returns_no_proxy_sentinel(self):
        assert safe_proxy_host(None) == "<no-proxy>"
        assert safe_proxy_host("") == "<no-proxy>"

    def test_unparseable_returns_sentinel(self):
        # urlsplit is permissive; force a real failure via a backslash-laden
        # netloc that urlsplit raises on.
        assert safe_proxy_host("http://[::1") == "<unparseable-proxy>"

    def test_userinfo_only_no_port_returns_host_sans_port(self):
        # `user:pass@host` with no port — return host alone (no `:port`).
        assert safe_proxy_host("http://u:p@gate.example.com") == "gate.example.com"

    def test_credentials_never_leak(self):
        out = safe_proxy_host("http://verysecretuser123:verysecretpassword456@host.example:7000")
        assert "verysecretuser123" not in out
        assert "verysecretpassword456" not in out


# ── resolve_proxy_config resolver ─────────────────────────────────────────


class TestResolveProxyConfig:
    def test_linkedin_env_set_returns_config(self, monkeypatch):
        from config import settings as app_settings

        monkeypatch.setattr(
            app_settings,
            "linkedin_proxy_url",
            "http://user:pass@gate.example.com:7000",
        )
        monkeypatch.setattr(app_settings, "linkedin_proxy_provider_hint", "smartproxy")
        result = resolve_proxy_config(JobSource.LINKEDIN)
        assert result is not None
        assert result.url == "http://user:pass@gate.example.com:7000"
        assert result.provider_hint == "smartproxy"

    def test_linkedin_env_unset_returns_none(self, monkeypatch):
        from config import settings as app_settings

        monkeypatch.setattr(app_settings, "linkedin_proxy_url", None)
        monkeypatch.setattr(app_settings, "linkedin_proxy_provider_hint", None)
        assert resolve_proxy_config(JobSource.LINKEDIN) is None

    def test_linkedin_env_empty_string_returns_none(self, monkeypatch):
        from config import settings as app_settings

        monkeypatch.setattr(app_settings, "linkedin_proxy_url", "")
        monkeypatch.setattr(app_settings, "linkedin_proxy_provider_hint", None)
        assert resolve_proxy_config(JobSource.LINKEDIN) is None

    @pytest.mark.parametrize(
        "source",
        [
            JobSource.WORKDAY,
            JobSource.GREENHOUSE,
            JobSource.LEVER,
            JobSource.ASHBY,
            JobSource.INDEED,
            JobSource.COMPANY_DIRECT,
            JobSource.RSSHUB,
        ],
    )
    def test_non_linkedin_source_always_returns_none(self, monkeypatch, source):
        from config import settings as app_settings

        monkeypatch.setattr(
            app_settings,
            "linkedin_proxy_url",
            "http://user:pass@gate.example.com:7000",
        )
        monkeypatch.setattr(app_settings, "linkedin_proxy_provider_hint", None)
        assert resolve_proxy_config(source) is None


# ── Boot-time fail-loud (plan 64 § D.6) ───────────────────────────────────


class TestConfigFailLoud:
    def test_invalid_proxy_url_raises_on_settings_construction(self, monkeypatch):
        """Settings field_validator runs ProxyURLConfig validation FAIL LOUD."""
        from pydantic import ValidationError

        from config import Settings

        monkeypatch.setenv("LINKEDIN_PROXY_URL", "javascript:alert(1)")
        # Bypass the SECRET_KEY validator so this test focuses on proxy.
        monkeypatch.setenv("NAAVIK_DEBUG", "1")
        with pytest.raises(ValidationError):
            Settings()

    def test_unset_proxy_url_does_not_raise(self, monkeypatch):
        from config import Settings

        monkeypatch.delenv("LINKEDIN_PROXY_URL", raising=False)
        monkeypatch.setenv("NAAVIK_DEBUG", "1")
        # Should not raise.
        s = Settings()
        assert s.linkedin_proxy_url is None
