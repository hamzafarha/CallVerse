"""Knowledge base document indexing and vector embeddings."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, Field

INDEX_FILE = "index.faiss"
CHUNKS_FILE = "chunks.parquet"
MANIFEST_FILE = "manifest.json"

FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
SECTION_HEADING = re.compile(r"^## +(.+?)\s*$", re.MULTILINE)
INTENTS_TAG = re.compile(r"<!--\s*intents:\s*(.*?)\s*-->")


@dataclass(frozen=True)
class KnowledgeBaseConfig:
    """Knowledge-base settings, loaded from ``configs/agents.yaml``."""

    docs_dir: Path
    index_dir: Path
    embedding_model: str
    embedding_batch_size: int
    max_seq_length: int
    max_chunk_chars: int
    top_k: int
    min_score: float
    no_answer_score: float


def load_knowledge_base_config(
    path: str | Path, project_root: str | Path | None = None
) -> KnowledgeBaseConfig:
    """Read the advisor knowledge-base settings; paths are relative to the project."""
    path = Path(path)
    with open(path, encoding="utf-8") as config_file:
        raw = yaml.safe_load(config_file)["advisor"]["knowledge_base"]
    root = Path(project_root) if project_root else path.resolve().parent.parent
    return KnowledgeBaseConfig(
        docs_dir=root / raw["docs_dir"],
        index_dir=root / raw["index_dir"],
        embedding_model=str(raw["embedding_model"]),
        embedding_batch_size=int(raw["embedding_batch_size"]),
        max_seq_length=int(raw["max_seq_length"]),
        max_chunk_chars=int(raw["max_chunk_chars"]),
        top_k=int(raw["top_k"]),
        min_score=float(raw["min_score"]),
        no_answer_score=float(raw["no_answer_score"]),
    )


class DocumentMeta(BaseModel):
    """Front matter of one knowledge-base document."""

    doc_id: str = Field(pattern=r"^[a-z0-9_]+$")
    title: str = Field(min_length=1)
    doc_type: Literal["policy", "faq", "procedure"]
    version: int = Field(ge=1)
    intents: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class Chunk:
    """One retrievable unit: a ``##`` section (or part of one) of a document."""

    chunk_id: str
    doc_id: str
    doc_title: str
    doc_type: str
    section: str
    intents: list[str]
    text: str

    def embedding_text(self) -> str:
        """Text sent to the embedding model: titles give the section its context."""
        return f"{self.doc_title} - {self.section}\n\n{self.text}"


class Embedder(Protocol):
    """Turns texts into L2-normalised float32 vectors (one row per text)."""

    model_name: str

    def encode(self, texts: list[str]) -> np.ndarray:
        """Embed texts."""
        ...


class SentenceTransformerEmbedder:
    """Local sentence-transformers model (bge-m3 by default), run on CPU or GPU."""

    def __init__(
        self, model_name: str, batch_size: int = 16, max_seq_length: int = 512
    ) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.batch_size = batch_size
        self.model = SentenceTransformer(model_name)
        self.model.max_seq_length = max_seq_length

    def encode(self, texts: list[str]) -> np.ndarray:
        """Embed texts as normalised vectors, so inner product = cosine similarity."""
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return np.asarray(vectors, dtype=np.float32)


def parse_intents(raw: str) -> list[str]:
    """Split a comma-separated intents tag."""
    return [intent.strip() for intent in raw.split(",") if intent.strip()]


def parse_document(text: str, source: str = "<text>") -> tuple[DocumentMeta, str]:
    """Split a Markdown document into validated front matter and body."""
    text = text.replace("\r\n", "\n")
    match = FRONT_MATTER.match(text)
    if not match:
        raise ValueError(f"{source}: missing '---' front matter block.")
    meta = DocumentMeta.model_validate(yaml.safe_load(match.group(1)))
    return meta, text[match.end() :]


def split_long_text(text: str, max_chars: int) -> list[str]:
    """Group paragraphs into parts of at most ``max_chars``; paragraphs are not cut."""
    parts: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", text):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if current and len(candidate) > max_chars:
            parts.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def chunk_document(meta: DocumentMeta, body: str, max_chars: int) -> list[Chunk]:
    """One chunk per ``##`` section; text before the first section is not indexed.

    A ``<!-- intents: a, b -->`` tag inside a section overrides the document's intents.
    """
    headings = list(SECTION_HEADING.finditer(body))
    chunks: list[Chunk] = []
    for number, heading in enumerate(headings, start=1):
        end = headings[number].start() if number < len(headings) else len(body)
        section_text = body[heading.end() : end]
        tag = INTENTS_TAG.search(section_text)
        intents = parse_intents(tag.group(1)) if tag else list(meta.intents)
        section_text = INTENTS_TAG.sub("", section_text).strip()
        if not section_text:
            continue
        parts = split_long_text(section_text, max_chars)
        for part_number, part in enumerate(parts, start=1):
            suffix = f"_p{part_number}" if len(parts) > 1 else ""
            chunks.append(
                Chunk(
                    chunk_id=f"{meta.doc_id}__s{number:02d}{suffix}",
                    doc_id=meta.doc_id,
                    doc_title=meta.title,
                    doc_type=meta.doc_type,
                    section=heading.group(1),
                    intents=intents,
                    text=part,
                )
            )
    return chunks


def load_chunks(
    docs_dir: str | Path,
    max_chars: int,
    allowed_intents: set[str] | None = None,
) -> list[Chunk]:
    """Parse and chunk every ``*.md`` document; checks ids and intent names."""
    paths = sorted(Path(docs_dir).glob("*.md"))
    if not paths:
        raise FileNotFoundError(f"No Markdown documents found in {docs_dir}.")
    chunks: list[Chunk] = []
    seen_doc_ids: set[str] = set()
    for path in paths:
        meta, body = parse_document(path.read_text(encoding="utf-8"), str(path))
        if meta.doc_id in seen_doc_ids:
            raise ValueError(f"{path}: duplicate doc_id '{meta.doc_id}'.")
        seen_doc_ids.add(meta.doc_id)
        doc_chunks = chunk_document(meta, body, max_chars)
        if not doc_chunks:
            raise ValueError(f"{path}: no '##' sections to index.")
        chunks.extend(doc_chunks)
    if allowed_intents is not None:
        unknown = {i for c in chunks for i in c.intents} - allowed_intents
        if unknown:
            raise ValueError(f"Unknown intents in documents: {sorted(unknown)}.")
    return chunks


def build_index(chunks: list[Chunk], embedder: Embedder) -> Any:
    """Embed chunks into an exact inner-product FAISS index (cosine on unit vectors)."""
    import faiss

    vectors = embedder.encode([chunk.embedding_text() for chunk in chunks])
    if vectors.shape[0] != len(chunks):
        raise ValueError("Embedder returned a different number of vectors.")
    if not np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-3):
        raise ValueError("Embeddings must be L2-normalised.")
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(np.ascontiguousarray(vectors, dtype=np.float32))
    return index


def docs_fingerprint(docs_dir: str | Path) -> dict[str, str]:
    """SHA-256 of every document, to detect an index older than its documents."""
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(Path(docs_dir).glob("*.md"))
    }


def save_knowledge_base(
    index_dir: str | Path, chunks: list[Chunk], index: Any, manifest: dict[str, Any]
) -> None:
    """Write the FAISS index, the chunk table and the manifest."""
    import faiss

    index_dir = Path(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_dir / INDEX_FILE))
    pd.DataFrame([asdict(chunk) for chunk in chunks]).to_parquet(
        index_dir / CHUNKS_FILE, index=False
    )
    with open(index_dir / MANIFEST_FILE, "w", encoding="utf-8") as manifest_file:
        json.dump(manifest, manifest_file, indent=2)


def build_knowledge_base(
    config: KnowledgeBaseConfig,
    embedder: Embedder | None = None,
    allowed_intents: set[str] | None = None,
) -> dict[str, Any]:
    """Parse, chunk, embed and save the knowledge base; returns the manifest."""
    chunks = load_chunks(config.docs_dir, config.max_chunk_chars, allowed_intents)
    if embedder is None:
        embedder = SentenceTransformerEmbedder(
            config.embedding_model, config.embedding_batch_size, config.max_seq_length
        )
    index = build_index(chunks, embedder)
    manifest = {
        "embedding_model": embedder.model_name,
        "dimension": int(index.d),
        "n_documents": len({chunk.doc_id for chunk in chunks}),
        "n_chunks": len(chunks),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "documents": docs_fingerprint(config.docs_dir),
    }
    save_knowledge_base(config.index_dir, chunks, index, manifest)
    return manifest
