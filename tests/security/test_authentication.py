import json

import pytest
from fastapi import HTTPException

from backend.app.api.routes.auth import LoginRequest, login
from backend.app.config import settings
from backend.app.security.auth import get_current_user


def test_login_issues_role_bound_jwt(monkeypatch):
    monkeypatch.setattr(
        settings,
        "auth_users_json",
        json.dumps({"director@example.com": {"password": "a-strong-test-password", "role": "DIR-MKT"}}),
    )
    monkeypatch.setattr(settings, "admin_email", "")

    response = login(LoginRequest(email="director@example.com", password="a-strong-test-password"))
    user = get_current_user(response.access_token)

    assert response.role == "DIR-MKT"
    assert user == {"sub": "director@example.com", "role": "DIR-MKT"}


def test_login_rejects_invalid_password(monkeypatch):
    monkeypatch.setattr(
        settings,
        "auth_users_json",
        json.dumps({"director@example.com": {"password": "correct-password", "role": "DIR-MKT"}}),
    )
    monkeypatch.setattr(settings, "admin_email", "")

    with pytest.raises(HTTPException) as exc:
        login(LoginRequest(email="director@example.com", password="wrong-password"))
    assert exc.value.status_code == 401


def test_expired_or_invalid_token_is_rejected():
    with pytest.raises(HTTPException) as exc:
        get_current_user("not-a-valid-jwt")
    assert exc.value.status_code == 401


def test_openai_api_key_is_masked_in_logs():
    from backend.app.security.sanitizer import sanitize_log_message, verify_text_clean_of_secrets

    fake_key = "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890_abcdefghijklmnopqrstuvwxyz"
    cleaned = sanitize_log_message(f"embedding request with key {fake_key}")
    is_clean, leaks = verify_text_clean_of_secrets(cleaned, forbidden_values=[fake_key])

    assert is_clean is True, leaks
    assert "sk-***[MASKED_API_KEY]" in cleaned


def test_startup_rejects_example_placeholder_credentials(monkeypatch):
    from backend.app.security.auth import validate_security_settings

    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "jwt_secret", "REPLACE_WITH_A_RANDOM_SECRET_OF_AT_LEAST_32_CHARACTERS")
    monkeypatch.setattr(settings, "auth_users_json", "")
    monkeypatch.setattr(settings, "admin_email", "admin@example.com")
    monkeypatch.setattr(settings, "admin_password", "REPLACE_WITH_A_STRONG_PASSWORD")

    with pytest.raises(RuntimeError, match="Unsafe application configuration"):
        validate_security_settings()
