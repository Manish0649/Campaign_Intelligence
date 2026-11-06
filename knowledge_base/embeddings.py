
"""Production embedding provider using Gemini embeddings.
Fake/hash vectors are intentionally forbidden.
"""
from functools import lru_cache

from backend.app.config import settings


@lru_cache(maxsize=1)
def _client():
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is required for semantic embeddings.")

    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError("google-genai package is not installed.") from exc

    return genai.Client(api_key=settings.gemini_api_key)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("Embedding input must contain non-empty strings only.")

    try:
        from google.genai import types

        response = _client().models.embed_content(
            model=settings.embedding_model,
            contents=texts,
            config=types.EmbedContentConfig(
                output_dimensionality=settings.embedding_dimension
            ),
        )
    except Exception as exc:
        # Avoid exposing API keys or raw provider error details.
        raise RuntimeError(
            f"Embedding provider request failed ({type(exc).__name__})."
        ) from None

    if not response.embeddings:
        raise RuntimeError("Gemini returned no embeddings.")

    vectors = [embedding.values for embedding in response.embeddings]

    if len(vectors) != len(texts):
        raise RuntimeError("Embedding provider returned an unexpected vector count.")

    if any(
        vector is None or len(vector) != settings.embedding_dimension
        for vector in vectors
    ):
        raise RuntimeError("Embedding dimension does not match EMBEDDING_DIMENSION.")

    return vectors


def embed_query(query: str) -> list[float]:
    return embed_texts([query])[0]
