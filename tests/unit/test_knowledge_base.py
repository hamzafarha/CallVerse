"""Unit tests for the advisor knowledge base (indexing and retrieval)."""

import re
from pathlib import Path

import numpy as np
import pytest
import yaml
from callverse.agents.advisor import (
    KnowledgeBaseConfig,
    KnowledgeRetriever,
    build_index,
    build_knowledge_base,
    chunk_document,
    load_chunks,
    parse_document,
)
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "data" / "knowledge_base" / "docs"

DOC = """---
doc_id: test_doc
title: Test Policy
doc_type: policy
version: 1
intents: [cancel_order]
---

# Test Policy

Preamble that is not indexed.

## Cancel before shipping

You can cancel the order before it ships.

## Refund timing
<!-- intents: refund_status, request_refund -->

Refunds arrive on the next card statement.
"""


class WordHashEmbedder:
    """Deterministic bag-of-words embedder: shared words give a higher cosine."""

    model_name = "fake-word-hash"

    def __init__(self, dimension: int = 256) -> None:
        self.dimension = dimension

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in re.findall(r"[a-z]+", text.lower()):
                vectors[row, sum(map(ord, word)) % self.dimension] += 1.0
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.where(norms == 0, 1, norms)


def order_linked_intents() -> set[str]:
    with open(PROJECT_ROOT / "configs" / "data.yaml", encoding="utf-8") as file:
        groups = yaml.safe_load(file)["generation"]["contacts"]["intent_groups"]
    return {intent for intents in groups.values() for intent in intents}


def make_config(tmp_path: Path, docs_dir: Path) -> KnowledgeBaseConfig:
    return KnowledgeBaseConfig(
        docs_dir=docs_dir,
        index_dir=tmp_path / "index",
        embedding_model=WordHashEmbedder.model_name,
        embedding_batch_size=8,
        max_seq_length=512,
        max_chunk_chars=1500,
        top_k=2,
        min_score=0.0,
        no_answer_score=0.5,
    )


def test_parse_document_reads_front_matter() -> None:
    meta, body = parse_document(DOC)
    assert meta.doc_id == "test_doc"
    assert meta.intents == ["cancel_order"]
    assert body.lstrip().startswith("# Test Policy")


def test_parse_document_rejects_bad_documents() -> None:
    with pytest.raises(ValueError, match="front matter"):
        parse_document("# No front matter\n")
    with pytest.raises(ValidationError):
        parse_document(DOC.replace("doc_type: policy", "doc_type: memo"))


def test_chunk_document_one_chunk_per_section_with_intent_override() -> None:
    meta, body = parse_document(DOC)
    chunks = chunk_document(meta, body, max_chars=1500)
    assert [c.section for c in chunks] == ["Cancel before shipping", "Refund timing"]
    assert chunks[0].intents == ["cancel_order"]
    assert chunks[1].intents == ["refund_status", "request_refund"]
    assert "Preamble" not in " ".join(c.text for c in chunks)
    assert "<!--" not in chunks[1].text


def test_long_sections_are_split_on_paragraphs() -> None:
    meta, _ = parse_document(DOC)
    paragraphs = "\n\n".join(f"Paragraph {i} " + "word " * 40 for i in range(5))
    chunks = chunk_document(meta, f"## Long\n\n{paragraphs}\n", max_chars=500)
    assert len(chunks) > 1
    assert all(len(c.text) <= 500 for c in chunks)
    assert chunks[0].chunk_id.endswith("_p1")
    assert "".join(c.text for c in chunks).count("Paragraph") == 5


def test_real_documents_cover_every_order_linked_intent() -> None:
    intents = order_linked_intents()
    chunks = load_chunks(DOCS_DIR, max_chars=1500, allowed_intents=intents)
    covered = {intent for chunk in chunks for intent in chunk.intents}
    assert covered == intents
    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_unknown_intent_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text(
        DOC.replace("cancel_order", "cancel_ordr"), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="cancel_ordr"):
        load_chunks(tmp_path, max_chars=1500, allowed_intents=order_linked_intents())


def test_search_ranks_matching_section_first(tmp_path: Path) -> None:
    pytest.importorskip("faiss")
    (tmp_path / "doc.md").write_text(DOC, encoding="utf-8")
    chunks = load_chunks(tmp_path, max_chars=1500)
    embedder = WordHashEmbedder()
    retriever = KnowledgeRetriever(chunks, build_index(chunks, embedder), embedder)

    hits = retriever.search("when do refunds arrive on my card statement", top_k=2)
    assert [h.rank for h in hits] == [1, 2]
    assert hits[0].chunk.section == "Refund timing"
    assert hits[0].score >= hits[1].score

    filtered = retriever.search("refunds card statement", intent="cancel_order")
    assert [h.chunk.section for h in filtered] == ["Cancel before shipping"]


def test_saved_index_round_trip_and_staleness_check(tmp_path: Path) -> None:
    pytest.importorskip("faiss")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "doc.md").write_text(DOC, encoding="utf-8")
    config = make_config(tmp_path, docs_dir)

    manifest = build_knowledge_base(config, WordHashEmbedder())
    assert manifest["n_chunks"] == 2
    retriever = KnowledgeRetriever.from_config(config, WordHashEmbedder())
    assert retriever.search("cancel the order")[0].chunk.doc_id == "test_doc"

    (docs_dir / "doc.md").write_text(DOC + "\n## New section\n\nText.\n", "utf-8")
    with pytest.raises(ValueError, match="Rebuild"):
        KnowledgeRetriever.from_config(config, WordHashEmbedder())
