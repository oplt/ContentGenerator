"""Remember-me cookie persistence for auth sessions."""

from __future__ import annotations

from starlette.responses import Response

from backend.modules.identity_access.router import _set_auth_cookies
from backend.modules.identity_access.schemas import SignInRequest


def _cookie_header_map(response: Response) -> dict[str, str]:
    headers = response.headers.getlist("set-cookie")
    return {header.split("=", 1)[0]: header for header in headers}


def test_sign_in_request_defaults_remember_me_true() -> None:
    payload = SignInRequest(email="demo@example.com", password="secret-password")
    assert payload.remember_me is True


def test_persistent_cookies_include_max_age_and_persist_flag() -> None:
    response = Response()
    _set_auth_cookies(
        response,
        access_token="access",
        refresh_token="refresh",
        csrf_token="csrf",
        remember_me=True,
    )
    cookies = _cookie_header_map(response)
    assert "Max-Age=" in cookies["access_token"]
    assert "Max-Age=" in cookies["refresh_token"]
    assert "Max-Age=" in cookies["csrf_token"]
    assert cookies["sf_persist"].startswith("sf_persist=1")
    assert "Max-Age=" in cookies["sf_persist"]


def test_session_cookies_omit_max_age_and_mark_persist_off() -> None:
    response = Response()
    _set_auth_cookies(
        response,
        access_token="access",
        refresh_token="refresh",
        csrf_token="csrf",
        remember_me=False,
    )
    cookies = _cookie_header_map(response)
    assert "Max-Age=" not in cookies["access_token"]
    assert "Max-Age=" not in cookies["refresh_token"]
    assert "Max-Age=" not in cookies["csrf_token"]
    assert cookies["sf_persist"].startswith("sf_persist=0")
    assert "Max-Age=" not in cookies["sf_persist"]
