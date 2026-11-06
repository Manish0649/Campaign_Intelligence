import httpx
import os
from dotenv import load_dotenv

load_dotenv()  # reads .env from project root
API_URL = os.getenv("API_URL", "http://localhost:8000")

def login(email: str, password: str) -> str | None:
    """Attempt login against /auth/login and return a JWT token if successful."""
    try:
        resp = httpx.post(f"{API_URL}/auth/login", json={"email": email, "password": password}, timeout=10)
        resp.raise_for_status()
        return resp.json().get("access_token")
    except httpx.HTTPError:
        return None



def role_from_token(token: str) -> str | None:
    """Read the JWT role claim for UI presentation only (not authorization)."""
    import base64
    import json
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode("ascii"))).get("role")
    except Exception:
        return None
