from knowledge_base.setup_milvus_zilliz import chunk_markdown_file


def test_markdown_chunk_ids_are_deterministic(tmp_path):
    path = tmp_path / "policy.md"
    path.write_text("# Budget Policy\n\nCampaign budgets must be approved before launch.", encoding="utf-8")

    first = chunk_markdown_file(path)
    second = chunk_markdown_file(path)

    assert first == second
    assert first[0]["doc_name"] == "policy.md"
    assert first[0]["section_title"] == "Budget Policy"
    assert len(first[0]["id"]) == 64


def test_markdown_chunker_splits_oversized_paragraphs(tmp_path):
    path = tmp_path / "long_policy.md"
    path.write_text("# Long Policy\n\n" + ("policy details " * 500), encoding="utf-8")

    chunks = chunk_markdown_file(path)

    assert len(chunks) > 1
    assert len({chunk["id"] for chunk in chunks}) == len(chunks)
    assert all(len(chunk["content"]) <= 1800 for chunk in chunks)
