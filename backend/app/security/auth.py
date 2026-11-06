
"""JWT authentication and role authorization helpers."""

from datetime import datetime, timedelta, timezone
from typing import Callable
import json
import os

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.app.config import settings


# Extract JWT from the Authorization: Bearer header.
bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(subject: str, role: str) -> str:
    if not settings.jwt_secret or len(settings.jwt_secret) < 32:
        raise RuntimeError(
            "JWT_SECRET must contain at least 32 characters."
        )

    now = datetime.now(timezone.utc)

    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=settings.jwt_exp_seconds),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )



def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
) -> dict:

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Support both FastAPI HTTPBearer credentials and direct JWT strings.
    if isinstance(credentials, str):
        token = credentials.strip()
    else:
        token = credentials.credentials

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={
                "require": ["exp", "sub", "role", "iss", "aud"]
            },
        )

    except (jwt.InvalidTokenError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    subject = payload.get("sub")
    role = payload.get("role")

    if (
        not isinstance(subject, str)
        or not subject.strip()
        or not isinstance(role, str)
        or not role.strip()
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication claims.",
        )

    return {
        "sub": subject,
        "role": role,
    }



def require_roles(*allowed_roles: str) -> Callable:

    allowed = set(allowed_roles)

    def dependency(
        user: dict = Depends(get_current_user),
    ) -> dict:

        if user.get("role") not in allowed:
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions.",
            )

        return user

    return dependency


def validate_security_settings() -> None:
    """Fail startup when a non-test deployment has unsafe placeholder settings."""

    if settings.environment.lower() in {"test", "testing"}:
        return

    problems = []

    placeholders = (
        "replace_",
        "change_me",
        "your_",
        "example.com",
    )

    jwt_secret = settings.jwt_secret.strip()

    if (
        len(jwt_secret) < 32
        or any(marker in jwt_secret.lower() for marker in placeholders)
    ):
        problems.append(
            "JWT_SECRET must be a non-placeholder random value "
            "of at least 32 characters"
        )

    if bool(settings.proposal_user_email) != bool(settings.proposal_user_password):
        problems.append(
            "PROPOSAL_USER_EMAIL and PROPOSAL_USER_PASSWORD must be configured together"
        )

    if settings.proposal_user_password and (
        len(settings.proposal_user_password) < 12
        or any(marker in settings.proposal_user_password.lower() for marker in placeholders)
    ):
        problems.append("PROPOSAL_USER_PASSWORD must be at least 12 characters and not a placeholder")

    if not settings.auth_users_json:
        if not settings.admin_email or not settings.admin_password:
            problems.append(
                "Configure ADMIN_EMAIL/ADMIN_PASSWORD or AUTH_USERS_JSON"
            )

        elif (
            "example.com" in settings.admin_email.lower()
            or any(
                marker in settings.admin_password.lower()
                for marker in placeholders
            )
        ):
            problems.append(
                "ADMIN_EMAIL/ADMIN_PASSWORD still contains "
                "example placeholder values"
            )

    if settings.auth_users_json:
        try:
            users = json.loads(settings.auth_users_json)

            if not isinstance(users, dict) or not users:
                raise ValueError(
                    "must be a non-empty JSON object"
                )

            for email, account in users.items():

                if not isinstance(email, str) or not isinstance(account, dict):
                    raise ValueError(
                        "each user must map an email to an account object"
                    )

                password = account.get("password", "")
                role = account.get("role", "")

                if (
                    not isinstance(password, str)
                    or not password
                    or not isinstance(role, str)
                    or not role
                ):
                    raise ValueError(
                        "each user must define string password and role values"
                    )

                if (
                    "example.com" in email.lower()
                    or any(
                        marker in password.lower()
                        for marker in placeholders
                    )
                ):
                    raise ValueError(
                        "user entries still contain placeholder values"
                    )

        except (json.JSONDecodeError, ValueError) as exc:
            problems.append(
                f"AUTH_USERS_JSON is invalid ({exc})"
            )

    sqlite_enabled = (
        os.getenv("USE_SQLITE", "").strip().lower()
        in {"1", "true", "yes"}
    )

    database_url = settings.database_url.strip().lower()

    database_placeholders = (
        "replace_",
        "your_",
        "host/dbname",
        "user:password",
    )

    if not sqlite_enabled and any(
        marker in database_url
        for marker in database_placeholders
    ):
        problems.append(
            "DATABASE_URL still contains example placeholders"
        )

    if (
        settings.environment.lower() == "production"
        and not database_url
    ):
        problems.append(
            "DATABASE_URL must be configured with a real PostgreSQL connection string"
        )

    if problems:
        raise RuntimeError(
            "Unsafe application configuration: "
            + "; ".join(problems)
        )
