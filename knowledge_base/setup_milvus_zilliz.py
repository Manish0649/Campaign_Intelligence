"""Safe, repeatable Markdown ingestion into Zilliz Cloud.

Existing collections are never dropped implicitly. Use --recreate only after
confirming that replacing the configured collection is intended.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

from backend.app.config import BASE_DIR, settings
from knowledge_base.embeddings import embed_texts
from knowledge_base.zilliz_client import get_zilliz_client

KB_DIR = BASE_DIR / "knowledge_base"
COLLECTION_NAME = settings.zilliz_collection
VECTOR_DIM = settings.embedding_dimension
BATCH_SIZE = 64
CHUNK_CHARS = 1400
CHUNK_OVERLAP = 180


def _split_long_text(text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > CHUNK_CHARS:
            if current:
                chunks.append(current)
                current = ""
            start = 0
            while start < len(paragraph):
                end = min(len(paragraph), start + CHUNK_CHARS)
                chunks.append(paragraph[start:end].strip())
                if end == len(paragraph):
                    break
                start = max(start + 1, end - CHUNK_OVERLAP)
            continue
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= CHUNK_CHARS:
            current = candidate
        else:
            chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return chunks


def chunk_markdown_file(file_path: Path) -> list[dict]:
    raw = file_path.read_text(encoding="utf-8")
    sections = re.split(r"(?m)(?=^#{1,3}\s+)", raw)
    records = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        lines = section.splitlines()
        title = lines[0].lstrip("# ").strip() if lines[0].startswith("#") else file_path.stem
        body = "\n".join(lines[1:]).strip() if lines[0].startswith("#") else section
        if not body:
            continue
        for chunk_index, chunk in enumerate(_split_long_text(body)):
            content = f"{title}\n\n{chunk}".strip()
            stable_id = hashlib.sha256(
                f"{file_path.name}\0{title}\0{chunk_index}\0{content}".encode("utf-8")
            ).hexdigest()
            records.append({
                "id": stable_id,
                "doc_name": file_path.name,
                "section_title": title[:256],
                "content": content,
                "category": file_path.stem[:128],
            })
    return records


def _ensure_collection(client, recreate: bool = False) -> None:
    from pymilvus import DataType

    if client.has_collection(COLLECTION_NAME):
        if not recreate:
            description = client.describe_collection(COLLECTION_NAME)
            fields = {field.get("name") for field in description.get("fields", [])}
            if not {"id", "vector", "doc_name", "section_title", "content", "category"}.issubset(fields):
                raise RuntimeError(
                    f"Existing collection '{COLLECTION_NAME}' has an incompatible schema. "
                    "Back it up, then rerun with --recreate to replace it explicitly."
                )
            vector_field = next(
                (field for field in description.get("fields", []) if field.get("name") == "vector"),
                {},
            )
            vector_dimension = vector_field.get("params", {}).get("dim")
            if vector_dimension is not None and int(vector_dimension) != VECTOR_DIM:
                raise RuntimeError(
                    f"Existing collection vector dimension is {vector_dimension}; configured dimension is {VECTOR_DIM}. "
                    "Back it up and explicitly recreate/migrate the collection."
                )
            return
        client.drop_collection(COLLECTION_NAME)

    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=64)
    schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=VECTOR_DIM)
    schema.add_field(field_name="doc_name", datatype=DataType.VARCHAR, max_length=256)
    schema.add_field(field_name="section_title", datatype=DataType.VARCHAR, max_length=256)
    schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=8192)
    schema.add_field(field_name="category", datatype=DataType.VARCHAR, max_length=128)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        index_type="AUTOINDEX",
        metric_type="COSINE",
    )
    client.create_collection(
        collection_name=COLLECTION_NAME,
        schema=schema,
        index_params=index_params,
    )


def ingest_knowledge_base(recreate: bool = False) -> int:
    client = get_zilliz_client()
    _ensure_collection(client, recreate=recreate)
    files = sorted(
        path for path in KB_DIR.glob("*.md")
        if path.name.lower() != "readme.md"
    )
    if not files:
        raise RuntimeError(f"No Markdown knowledge base documents found in {KB_DIR}.")

    chunks = [record for path in files for record in chunk_markdown_file(path)]
    if not chunks:
        raise RuntimeError("No non-empty knowledge base chunks were produced.")

    inserted = 0
    for start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[start:start + BATCH_SIZE]
        vectors = embed_texts([record["content"] for record in batch])
        rows = [{**record, "vector": vector} for record, vector in zip(batch, vectors)]
        result = client.upsert(collection_name=COLLECTION_NAME, data=rows)
        inserted += int(result.get("upsert_count", len(rows)))
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the configured collection. Destructive; use only intentionally.",
    )
    args = parser.parse_args()
    count = ingest_knowledge_base(recreate=args.recreate)
    print(f"Upserted {count} knowledge chunks into '{COLLECTION_NAME}'.")


if __name__ == "__main__":
    main()
