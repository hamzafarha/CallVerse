"""RAG advisor evaluation (DSO2), RAGAS-style metrics computed locally.

RAGAS normally asks an LLM to grade; here the same three questions are answered
with the bge-m3 embeddings (or TF-IDF), which is cheap and reproducible:

- context recall@k: is a policy section about the question's intent among the
  k retrieved sections? (retrieval quality; also MRR)
- faithfulness: share of the answer's sentences supported by the retrieved policy
  or the tool results (max cosine similarity >= threshold): low = invented content.
- answer relevance: cosine similarity between the question and the answer.

The baseline of the DSO document is "basic keyword search in the FAQ".
"""

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from callverse.agents.advisor.intent_classifier import BITEXT_FILE, intent_groups
from callverse.config import TRACE_DIR

SENTENCE = re.compile(r"(?<=[.!?])\s+")


def retrieval_test_set(per_intent: int = 15, seed: int = 7) -> pd.DataFrame:
    """Bitext questions of the 17 order-linked intents (never used to build the KB)."""
    data = pd.read_csv(BITEXT_FILE)
    data = data[data["intent"].isin(intent_groups())]
    data = data[~data["tags"].fillna("").str.contains("W")]
    return (
        data.groupby("intent", group_keys=False)
        .apply(lambda g: g.sample(min(per_intent, len(g)), random_state=seed))[["instruction", "intent"]]
        .reset_index(drop=True)
    )


def retrieval_metrics(retriever: Any, test_set: pd.DataFrame, k: int = 4) -> dict[str, float]:
    """Context recall@1/@k and MRR: a hit is a retrieved chunk tagged with the intent."""
    results = retriever.search_many(test_set["instruction"].tolist(), top_k=k)
    hit_at_1, hit_at_k, reciprocal = [], [], []
    for hits, intent in zip(results, test_set["intent"]):
        ranks = [h.rank for h in hits if intent in h.chunk.intents]
        hit_at_1.append(bool(ranks) and ranks[0] == 1)
        hit_at_k.append(bool(ranks))
        reciprocal.append(1 / ranks[0] if ranks else 0.0)
    return {
        "questions": float(len(test_set)),
        "context_recall_at_1": float(np.mean(hit_at_1)),
        f"context_recall_at_{k}": float(np.mean(hit_at_k)),
        "mrr": float(np.mean(reciprocal)),
    }


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE.split(text or "") if len(s.strip()) > 12]


def faithfulness_and_relevance(
    conversations: list[dict[str, Any]], embedder: Any, chunk_text: dict[str, str], threshold: float = 0.55
) -> pd.DataFrame:
    """Per advisor answer: faithfulness to its evidence and relevance to the question.

    Evidence = the tool results of that turn + the policy sections it cited or retrieved.
    """
    rows = []
    for state in conversations:
        messages = state["messages"]
        question = next((m["text"] for m in messages if m["speaker"] == "customer"), "")
        for message in messages:
            if message["speaker"] != "advisor" or message["meta"].get("stage") == "verify":
                continue
            evidence = []
            for tool in message["meta"].get("tools", []):
                evidence += _sentences(json.dumps(tool.get("result", {})).replace('"', " "))
            cited = list(message["meta"].get("sources", []))
            cited += [r["chunk_id"] for r in message["meta"].get("retrieval", [])]
            for chunk_id in dict.fromkeys(cited):
                evidence += _sentences(chunk_text.get(chunk_id, ""))
            answer = _sentences(message["text"])
            if not answer:
                continue
            if evidence:
                vectors = embedder.encode(answer + evidence)
                a, e = vectors[: len(answer)], vectors[len(answer) :]
                support = (a @ e.T).max(axis=1)
                faithful = float((support >= threshold).mean())
            else:
                faithful = float("nan")
            q, ans = embedder.encode([question, message["text"]])
            rows.append(
                {
                    "contact_id": state["profile"]["contact_id"],
                    "mode": message["meta"].get("mode"),
                    "variant": state.get("_variant", "unlabelled"),
                    "faithfulness": faithful,
                    "answer_relevance": float(q @ ans),
                }
            )
    return pd.DataFrame(rows)


def load_saved_conversations(folder: Path = TRACE_DIR / "conversations") -> list[dict[str, Any]]:
    """Transcripts written by the conversation batch runs (``_variant`` from the file name)."""
    if not folder.exists():
        return []
    conversations = []
    for path in sorted(folder.glob("*.json")):
        state = json.loads(path.read_text(encoding="utf-8"))
        state["_variant"] = path.stem.split("_", 1)[1] if "_" in path.stem else "unlabelled"
        conversations.append(state)
    return conversations


def main_answer(state: dict[str, Any]) -> str | None:
    """The advisor message that answers the problem (first one after verification)."""
    advisor = [m for m in state["messages"] if m["speaker"] == "advisor"]
    for message in advisor:
        if message["meta"].get("stage") == "answer":
            return str(message["text"])
    return str(advisor[1]["text"]) if len(advisor) > 1 else None


def answer_similarity(conversations: list[dict[str, Any]], embedder: Any) -> pd.DataFrame:
    """Judge-free answer correctness: cosine(advisor's answer, policy-approved answer).

    The approved answer is what the company rules say for this order and the true
    intent; a high similarity means the advisor conveyed the same action and facts.
    """
    rows = []
    for state in conversations:
        reference = (state.get("reference") or {}).get("answer")
        answer = main_answer(state)
        if not reference or not answer:
            continue
        vectors = embedder.encode([answer, reference])
        rows.append(
            {
                "contact_id": state["profile"]["contact_id"],
                "variant": state.get("_variant"),
                "similarity_to_policy_answer": float(vectors[0] @ vectors[1]),
            }
        )
    return pd.DataFrame(rows)
