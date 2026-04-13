"""Tests for auth providers."""

import pytest

from airflow_mcp.auth import (
    BasicAuthProvider,
    DHCookieAuthProvider,
    DHServiceAccountAuthProvider,
    create_auth_provider,
)


def test_basic_auth_headers():
    auth = BasicAuthProvider("admin", "secret")
    headers = auth.get_headers()
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Basic ")


def test_dh_cookie_auth_headers():
    auth = DHCookieAuthProvider("session=abc123")
    headers = auth.get_headers()
    assert headers == {"Cookie": "session=abc123"}


def test_dh_service_account_not_implemented():
    with pytest.raises(NotImplementedError, match="not yet implemented"):
        DHServiceAccountAuthProvider()


def test_create_auth_provider_basic():
    auth = create_auth_provider({"type": "basic", "username": "u", "password": "p"})
    assert isinstance(auth, BasicAuthProvider)


def test_create_auth_provider_cookie():
    auth = create_auth_provider({"type": "dh_cookie", "session_cookie": "s=1"})
    assert isinstance(auth, DHCookieAuthProvider)


def test_create_auth_provider_unknown():
    with pytest.raises(ValueError, match="Unknown auth type"):
        create_auth_provider({"type": "magic"})
