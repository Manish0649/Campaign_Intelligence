# Campaign Intelligence Policy Knowledge Base

This directory contains the source Markdown policies and the Zilliz semantic retrieval pipeline. Structured campaign, inventory, supplier and financial facts remain in PostgreSQL; Zilliz is only for unstructured policy/playbook retrieval.

## Files

- `campaign_planning_policy.md` — budget, cost and targeting rules
- `inventory_and_safety_stock_rules.md` — inventory availability and safety stock
- `supplier_replenishment_and_lead_time_protocols.md` — supplier readiness, lead time and MOQ
- `campaign_playbooks_and_scenario_guidelines.md` — campaign scenarios and playbooks
- `decision_system_and_approval_hierarchy.md` — decision and approval governance
- `embeddings.py` — real OpenAI embedding provider (no hash-vector fallback)
- `setup_milvus_zilliz.py` — safe, repeatable ingestion
- `retriever.py` — semantic search function used by FastAPI and LangGraph
- `zilliz_client.py` — lazy Zilliz connection factory

## Configuration

Set these values in the project-root `.env` file:

```env
ZILLIZ_ENDPOINT=https://YOUR-ZILLIZ-ENDPOINT
ZILLIZ_TOKEN=YOUR_ZILLIZ_TOKEN
ZILLIZ_COLLECTION=campaign_intelligence_kb
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSION=1536
```

## Ingest or update documents

Run from the project root:

```powershell
python -m knowledge_base.setup_milvus_zilliz
```

Ingestion uses deterministic chunk IDs and `upsert`, so repeat runs do not append duplicate copies of unchanged chunks. Existing collections are not dropped implicitly. If an existing collection has an incompatible schema, back it up and intentionally run:

```powershell
python -m knowledge_base.setup_milvus_zilliz --recreate
```

`--recreate` drops the configured collection and is destructive.

## Retrieve policies

The Python API is:

```python
from knowledge_base.retriever import retrieve_policy_context

passages = retrieve_policy_context(
    "What is the minimum supplier readiness required before activation?",
    top_k=4,
)
```

Authenticated API endpoint: `POST /knowledge-base/search` with `query`, optional `top_k`, and optional `category`. The Streamlit dashboard exposes the same search capability.

LangGraph orchestration retrieves a small set of advisory policy references when Zilliz is configured. Retrieval failure does not stop deterministic planning, and retrieved text never overrides SQL facts or hard feasibility constraints.
