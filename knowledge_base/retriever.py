"""Semantic retrieval from the Campaign Intelligence policy collection."""
from __future__ import annotations

from knowledge_base.embeddings import embed_query
from knowledge_base.zilliz_client import get_zilliz_client
from backend.app.config import settings


def retrieve_policy_context(query_str: str, top_k: int = 4, category_filter: str | None = None) -> list[dict]:
    query = (query_str or "").strip()
    if not query:
        raise ValueError("query_str must be a non-empty string.")
    if top_k < 1 or top_k > 20:
        raise ValueError("top_k must be between 1 and 20.")

    client = get_zilliz_client()
    client.load_collection(collection_name=settings.zilliz_collection)
    query_vector = embed_query(query)
    params = {
        "collection_name": settings.zilliz_collection,
        "data": [query_vector],
        "limit": top_k,
        "output_fields": ["doc_name", "section_title", "content", "category"],
    }
    if category_filter:
        safe_category = category_filter.replace('\\', '\\\\').replace('"', '\\"')
        params["filter"] = f'category == "{safe_category}"'

    results = client.search(**params)
    hits = results[0] if results else []
    if not hits and category_filter:
        params.pop("filter", None)
        results = client.search(**params)
        hits = results[0] if results else []

    return [
        {
            "doc_name": hit.get("entity", {}).get("doc_name"),
            "section_title": hit.get("entity", {}).get("section_title"),
            "content": hit.get("entity", {}).get("content"),
            "category": hit.get("entity", {}).get("category"),
            "similarity_score": float(hit.get("distance", 0.0)),
        }
        for hit in hits
    ]
