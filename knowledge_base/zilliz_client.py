"""Lazy Zilliz Cloud client factory. No network call occurs at import time."""
from functools import lru_cache

from dotenv import load_dotenv

from backend.app.config import BASE_DIR, settings

load_dotenv(BASE_DIR / ".env")


@lru_cache(maxsize=1)
def get_zilliz_client():
    if not settings.zilliz_endpoint or not settings.zilliz_token:
        raise RuntimeError("ZILLIZ_ENDPOINT and ZILLIZ_TOKEN must be configured.")
    try:
        from pymilvus import MilvusClient
    except ImportError as exc:
        raise RuntimeError("pymilvus is not installed. Install backend/requirements.txt.") from exc
    try:
        return MilvusClient(uri=settings.zilliz_endpoint, token=settings.zilliz_token)
    except Exception as exc:
        raise RuntimeError(f"Zilliz client initialization failed ({type(exc).__name__}).") from None


def test_connection():
    try:
        client = get_zilliz_client()
        return True, client.list_collections()
    except Exception as exc:
        # Never include raw upstream exception text in a client-facing result.
        return False, f"Zilliz connection failed ({type(exc).__name__})."
