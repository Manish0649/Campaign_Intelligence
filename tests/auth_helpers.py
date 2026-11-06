from backend.app.security.auth import create_access_token


def auth_headers(role="SYS-ADMIN", subject="test-user"):
    return {"Authorization": f"Bearer {create_access_token(subject, role)}"}
