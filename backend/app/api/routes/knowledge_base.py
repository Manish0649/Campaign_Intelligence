"""Knowledge base retrieval and RAG answer generation API backed by Zilliz and Gemini."""
from fastapi import APIRouter, HTTPException, Depends
from backend.app.security.auth import get_current_user
from pydantic import BaseModel, Field, field_validator
from knowledge_base.rag_service import generate_rag_answer

from knowledge_base.retriever import retrieve_policy_context

router = APIRouter(prefix="/knowledge-base", tags=["Knowledge Base"], dependencies=[Depends(get_current_user)])


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    top_k: int = Field(default=4, ge=1, le=20)
    category: str | None = Field(default=None, max_length=128)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("query must contain at least 3 non-whitespace characters")
        return value


@router.post("/search")
def search_policy_knowledge(request: KnowledgeSearchRequest):
    try:
        results = retrieve_policy_context(
            query_str=request.query,
            top_k=request.top_k,
            category_filter=request.category,
        )
    except Exception as exc:
        # Provider errors may echo credential fragments. Never return raw
        # upstream exception text to the caller.
        raise HTTPException(
            status_code=503,
            detail="Knowledge retrieval is temporarily unavailable. Verify Zilliz and embedding configuration.",
        ) from exc
    return {
        "query": request.query,
        "result_count": len(results),
        "results": results,
    }

@router.post("/ask")
def ask_knowledge_base(request: KnowledgeSearchRequest):
    try:
        result = generate_rag_answer(
            query=request.query,
            top_k=request.top_k,
            category_filter=request.category,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Knowledge-based answer generation is temporarily unavailable. Verify Gemini, Zilliz, and embedding configuration.",
        ) from exc

    return result
