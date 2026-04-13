"""Pluggable authentication providers for Airflow instances."""

from __future__ import annotations

import base64
from abc import ABC, abstractmethod


class AuthProvider(ABC):
    """Base class for Airflow authentication."""

    @abstractmethod
    def get_headers(self) -> dict[str, str]:
        """Return HTTP headers required for authentication."""


class BasicAuthProvider(AuthProvider):
    """HTTP Basic Auth — for local Airflow and simple setups."""

    def __init__(self, username: str, password: str) -> None:
        self._token = base64.b64encode(f"{username}:{password}".encode()).decode()

    def get_headers(self) -> dict[str, str]:
        return {"Authorization": f"Basic {self._token}"}


class DHCookieAuthProvider(AuthProvider):
    """Delivery Hero session cookie auth — paste cookie from browser.

    This is the quick-start approach for DH Airflow instances behind
    Google SSO + Cloudflare. The cookie expires after hours/days and
    must be manually refreshed.
    """

    def __init__(self, session_cookie: str) -> None:
        self._cookie = session_cookie

    def get_headers(self) -> dict[str, str]:
        return {"Cookie": self._cookie}


class DHServiceAccountAuthProvider(AuthProvider):
    """Placeholder for GCP service account auth.

    The right long-term solution: a GCP service account with Airflow
    viewer role gets a long-lived token. Implementation requires a
    service account key and the google-auth library.
    """

    def __init__(self, **kwargs: str) -> None:
        raise NotImplementedError(
            "Service account auth not yet implemented. "
            "Request a GCP service account with Airflow viewer role from your platform team."
        )

    def get_headers(self) -> dict[str, str]:
        raise NotImplementedError


def create_auth_provider(auth_config: dict) -> AuthProvider:
    """Factory: build an AuthProvider from a config dict."""
    auth_type = auth_config["type"]
    if auth_type == "basic":
        return BasicAuthProvider(auth_config["username"], auth_config["password"])
    elif auth_type == "dh_cookie":
        return DHCookieAuthProvider(auth_config["session_cookie"])
    elif auth_type == "dh_service_account":
        return DHServiceAccountAuthProvider(**auth_config)
    else:
        raise ValueError(f"Unknown auth type: {auth_type}")
