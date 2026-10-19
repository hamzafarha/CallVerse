"""Quality Analyst agent (DSO2): grades every conversation with the scorecard.

Main idea A: LLM-as-judge. A model from a *different family* than the advisor
(Llama vs Qwen) reads the transcript, the rubric and the reference answer (the
policy-correct outcome computed by the company rules) and returns JSON scores.

Backup: a checklist reviewer (rules + a small sentiment lexicon). It is cheap,
deterministic, and used when Ollama is not running.
"""

import json
import re
from typing import Any

from callverse.agents.quality.rubric import CRITERIA, Scorecard, rubric
from callverse.llm import LLMClient, LLMUnavailableError

POSITIVE = {
    "thank",
    "thanks",
    "great",
    "perfect",
    "clear",
    "ok",
    "okay",
    "good",
    "alright",
    "appreciate",
    "helpful",
    "bye",
    "fine",
}
NEGATIVE = {
    "not",
    "never",
    "unacceptable",
    "angry",
    "terrible",
    "worst",
    "supervisor",
    "still",
    "really",
    "bad",
    "useless",
    "ridiculous",
    "upset",
    "hope",
    "need",
}
FORBIDDEN = re.compile(r"card number|security code|cvv|password", re.I)
VERIFY = re.compile(r"order number|order id|e-mail|email", re.I)

JUDGE_SYSTEM = """You are a strict quality analyst of a customer-service center.
Grade the conversation with this scorecard (integers 1-5, 5 = excellent):
{rubric}

Reference (what company policy says the correct outcome is): {reference}

Be strict:
- "correct" is true ONLY if the advisor gave the same outcome AND the same timing / next step
  as the reference. Missing the key fact, or a different action, is false.
- Lower "compliance" for invented promises, timings or compensations that are not in the
  reference, for answering without checking the order, or for asking for card data.
- Lower "resolution" when the customer leaves without a clear next step.

Return ONLY a JSON object:
{{"compliance": int, "relevance": int, "satisfaction": int, "sentiment": int, "resolution": int,
"correct": true/false (does the advisor's answer match the reference outcome?),
"resolved": true/false (solved in the chat, or correctly handed over with a clear next step),
"rationale": "one short sentence"}}"""


def lexicon_sentiment(text: str) -> int:
    """1-5 mood of a message from a small positive/negative word list."""
    words = re.findall(r"[a-z']+", text.lower())
    score = sum(w.strip("'") in POSITIVE for w in words) - sum(w in NEGATIVE for w in words)
    if "!" in text and score <= 0:
        score -= 1
    return int(max(1, min(5, 3 + score)))


def transcript(messages: list[dict[str, Any]]) -> str:
    return "\n".join(f"{m['speaker'].upper()}: {m['text']}" for m in messages)


class QualityReviewer:
    """Scores conversations with an LLM judge (or the checklist backup)."""

    def __init__(self, llm: LLMClient | None = None, mode: str = "auto") -> None:
        self.llm = llm
        self.mode = mode

    def use_llm(self) -> bool:
        if self.mode == "rules" or self.llm is None:
            return False
        return self.mode == "llm" or self.llm.available()

    def review(
        self,
        messages: list[dict[str, Any]],
        reference: dict[str, Any] | None = None,
        advisor_meta: dict[str, Any] | None = None,
    ) -> Scorecard:
        """Scorecard of one conversation.

        ``reference`` holds the policy-correct ``outcome``, ``kb_chunk_id`` and
        ``answer`` text; ``advisor_meta`` what the advisor did (sources, outcome,
        handover) for the checklist.
        """
        if self.use_llm():
            try:
                return self._llm_review(messages, reference)
            except (LLMUnavailableError, ValueError, KeyError):
                pass
        return self._rule_review(messages, reference, advisor_meta or {})

    # -------------------------------------------------------------- checklist
    def _rule_review(
        self, messages: list[dict[str, Any]], reference: dict[str, Any] | None, meta: dict[str, Any]
    ) -> Scorecard:
        advisor = [str(m["text"]) for m in messages if m["speaker"] == "advisor"]
        customer = [str(m["text"]) for m in messages if m["speaker"] == "customer"]
        sources = set(meta.get("sources", []))
        tools = meta.get("tools", [])
        verified = any(VERIFY.search(t) for t in advisor[:2]) or any(
            t["name"] == "lookup_order" and t["ok"] for t in tools
        )
        looked_up = any(t["name"] == "lookup_order" and t["ok"] for t in tools)
        forbidden = any(FORBIDDEN.search(t) for t in advisor)
        policy_cited = bool(sources - {"advisor_playbook__s01", "advisor_playbook__s05"})
        correct = None
        if reference:
            correct = bool(
                reference.get("kb_chunk_id") in sources
                or (meta.get("outcome") and meta.get("outcome") == reference.get("outcome"))
            )
        compliance = 1 + 2 * verified + 1 * looked_up + 1 * policy_cited - 3 * forbidden
        relevance = 5 if correct else (3 if policy_cited else 2)
        if correct is None:
            relevance = 4 if policy_cited else 2
        mood = lexicon_sentiment(customer[-1]) if customer else 3
        handover = meta.get("handed_to")
        escalated = any("supervisor" in t.lower() for t in customer)
        if escalated:
            resolution = 2
        elif handover:
            resolution = 3
        else:
            resolution = 5 if looked_up and policy_cited else 3
        satisfaction = round((mood + resolution + (5 if correct else 3)) / 3)
        scores = {
            "compliance": compliance,
            "relevance": relevance,
            "satisfaction": satisfaction,
            "sentiment": mood,
            "resolution": resolution,
        }
        scores = {k: int(max(1, min(5, v))) for k, v in scores.items()}
        rationale = (
            f"verified={verified}, order looked up={looked_up}, policy cited={policy_cited}, "
            f"matches reference={correct}, handover={handover or 'none'}"
        )
        return Scorecard(
            scores,
            correct,
            resolution >= 3 and not escalated,
            rationale,
            "rules",
            details={
                "verified": verified,
                "looked_up": looked_up,
                "policy_cited": policy_cited,
                "forbidden": forbidden,
            },
        )

    # ------------------------------------------------------------------ judge
    def _llm_review(self, messages: list[dict[str, Any]], reference: dict[str, Any] | None) -> Scorecard:
        assert self.llm is not None
        criteria = "\n".join(f"- {name}: {text}" for name, text in rubric().items())
        reference_text = "not available"
        if reference:
            reference_text = f"outcome '{reference.get('outcome')}': {reference.get('answer', '')}"
        chat = [
            {"role": "system", "content": JUDGE_SYSTEM.format(rubric=criteria, reference=reference_text)},
            {"role": "user", "content": "CONVERSATION:\n" + transcript(messages)},
        ]
        response = self.llm.chat("judge", chat, json_mode=True, agent="quality", temperature=0.0)
        data = response.json()
        scores = {c: int(max(1, min(5, int(data[c])))) for c in CRITERIA}
        correct = data.get("correct")
        return Scorecard(
            scores,
            None if correct is None else bool(correct),
            bool(data.get("resolved", scores["resolution"] >= 3)),
            str(data.get("rationale", ""))[:300],
            "llm",
            response.model,
            response.latency_ms,
            {"raw": json.dumps(data)[:500]},
        )
