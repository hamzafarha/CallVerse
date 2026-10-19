"""Knowledge retrieval engine over contact center documentation."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from callverse.agents.advisor.indexing import (
    CHUNKS_FILE,
    INDEX_FILE,
    MANIFEST_FILE,
    Chunk,
    Embedder,
    KnowledgeBaseConfig,
    SentenceTransformerEmbedder,
    docs_fingerprint,
)


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk returned for a query, with its cosine score and rank (1 = best)."""

    chunk: Chunk
    score: float
    rank: int


class KnowledgeRetriever:
    """Exact cosine search over the knowledge-base chunks."""

    def __init__(
        self,
        chunks: list[Chunk],
        index: Any,
        embedder: Embedder,
        top_k: int = 4,
        min_score: float = 0.0,
    ) -> None:
        if index.ntotal != len(chunks):
            raise ValueError("Index size does not match the number of chunks.")
        self.chunks = chunks
        self.index = index
        self.embedder = embedder
        self.top_k = top_k
        self.min_score = min_score

    @classmethod
    def from_config(
        cls,
        config: KnowledgeBaseConfig,
        embedder: Embedder | None = None,
        check_freshness: bool = True,
    ) -> "KnowledgeRetriever":
        """Load the index built by ``build_knowledge_base``."""
        import faiss

        index_dir = Path(config.index_dir)
        if not (index_dir / INDEX_FILE).exists():
            raise FileNotFoundError(
                f"No index in {index_dir}. Run scripts/build_knowledge_base.py first."
            )
        with open(index_dir / MANIFEST_FILE, encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)
        if manifest["embedding_model"] != config.embedding_model:
            raise ValueError(
                f"Index was built with {manifest['embedding_model']}, "
                f"config asks for {config.embedding_model}. Rebuild the index."
            )
        if check_freshness and manifest["documents"] != docs_fingerprint(
            config.docs_dir
        ):
            raise ValueError("Documents changed since the index was built. Rebuild.")
        if embedder is None:
            embedder = SentenceTransformerEmbedder(
                config.embedding_model,
                config.embedding_batch_size,
                config.max_seq_length,
            )
        rows = pd.read_parquet(index_dir / CHUNKS_FILE).to_dict("records")
        chunks = [Chunk(**{**row, "intents": list(row["intents"])}) for row in rows]
        index = faiss.read_index(str(index_dir / INDEX_FILE))
        return cls(chunks, index, embedder, config.top_k, config.min_score)

    def search(
        self, query: str, top_k: int | None = None, intent: str | None = None
    ) -> list[RetrievedChunk]:
        """Best chunks for one query, optionally only those tagged with ``intent``."""
        return self.search_many([query], top_k, intent)[0]

    def search_many(
        self,
        queries: list[str],
        top_k: int | None = None,
        intent: str | None = None,
    ) -> list[list[RetrievedChunk]]:
        """Best chunks for each query; queries are embedded in one batch."""
        top_k = top_k or self.top_k
        vectors = np.ascontiguousarray(self.embedder.encode(queries), dtype=np.float32)
        # With an intent filter, rank every chunk and keep the matching ones;
        # the corpus is small, so this costs nothing.
        depth = self.index.ntotal if intent else min(top_k, self.index.ntotal)
        scores, positions = self.index.search(vectors, depth)
        results = []
        for query_scores, query_positions in zip(scores, positions):
            hits: list[RetrievedChunk] = []
            for score, position in zip(query_scores, query_positions):
                if position < 0 or score < self.min_score:
                    continue
                chunk = self.chunks[position]
                if intent and intent not in chunk.intents:
                    continue
                hits.append(RetrievedChunk(chunk, float(score), len(hits) + 1))
                if len(hits) == top_k:
                    break
            results.append(hits)
        return results


class KeywordRetriever:
    """Keyword search (TF-IDF) over the same chunks: the DSO2 baseline.

    Also the offline fallback when the bge-m3 model cannot be loaded.
    """

    model_name = "tfidf-keyword-baseline"

    def __init__(self, chunks: list[Chunk], top_k: int = 4) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.chunks = chunks
        self.top_k = top_k
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
        self.matrix = self.vectorizer.fit_transform([c.embedding_text() for c in chunks])

    @classmethod
    def from_config(cls, config: KnowledgeBaseConfig) -> "KeywordRetriever":
        """Chunks from the built index, or parsed from the Markdown documents."""
        from callverse.agents.advisor.indexing import load_chunks

        chunk_file = Path(config.index_dir) / CHUNKS_FILE
        if chunk_file.exists():
            rows = pd.read_parquet(chunk_file).to_dict("records")
            chunks = [Chunk(**{**row, "intents": list(row["intents"])}) for row in rows]
        else:
            chunks = load_chunks(config.docs_dir, config.max_chunk_chars)
        return cls(chunks, config.top_k)

    def search(
        self, query: str, top_k: int | None = None, intent: str | None = None
    ) -> list[RetrievedChunk]:
        return self.search_many([query], top_k, intent)[0]

    def search_many(
        self, queries: list[str], top_k: int | None = None, intent: str | None = None
    ) -> list[list[RetrievedChunk]]:
        top_k = top_k or self.top_k
        scores = (self.vectorizer.transform(queries) @ self.matrix.T).toarray()
        results = []
        for row in scores:
            hits: list[RetrievedChunk] = []
            for position in np.argsort(-row):
                chunk = self.chunks[position]
                if intent and intent not in chunk.intents:
                    continue
                hits.append(RetrievedChunk(chunk, float(row[position]), len(hits) + 1))
                if len(hits) == top_k:
                    break
            results.append(hits)
        return results
