import secrets
import json

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from backend.app.config import settings
from backend.app.security.auth import create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("A valid email address is required.")
        return value


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str


@router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest):
    """Authenticate a configured account and issue a role-bound JWT."""
    users = {}
    if settings.auth_users_json:
        try:
            users = json.loads(settings.auth_users_json)
            if not isinstance(users, dict):
                raise ValueError("AUTH_USERS_JSON must be a JSON object.")
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=500, detail="AUTH_USERS_JSON configuration is invalid.") from exc

    configured = users.get(data.email.lower())
    if (
        configured is None
        and settings.proposal_user_email
        and data.email.lower() == settings.proposal_user_email.lower()
    ):
        configured = {
            "password": settings.proposal_user_password,
            "role": "PROPOSAL-SUBMITTER",
        }
    if configured is None and settings.admin_email:
        if secrets.compare_digest(data.email.lower().encode("utf-8"), settings.admin_email.lower().encode("utf-8")):
            configured = {"password": settings.admin_password, "role": settings.admin_role}

    expected_password = configured.get("password", "") if isinstance(configured, dict) else ""
    role = configured.get("role", "") if isinstance(configured, dict) else ""
    valid_password = (
        isinstance(expected_password, str)
        and bool(expected_password)
        and secrets.compare_digest(
            data.password.encode("utf-8"), expected_password.encode("utf-8")
        )
    )
    if not valid_password or not isinstance(role, str) or not role.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(data.email, role)
    return LoginResponse(
        access_token=token,
        expires_in=settings.jwt_exp_seconds,
        role=role,
    )
