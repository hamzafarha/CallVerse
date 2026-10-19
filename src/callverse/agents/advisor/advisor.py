"""Customer Advisor agent (DSO2): Ask -> Retrieve -> LLM (+ tools) -> Reply.

Main idea A (agentic RAG): the advisor retrieves the relevant policy sections
(bge-m3 + FAISS), then a mid-size LLM with tool calling looks up the order in the
SQLite store, opens follow-up tickets, and writes the reply.

Backup (DSO2): question sorting + approved templates. The intent classifier
predicts the problem type, the order tools give the facts, the company rules
choose the outcome and an approved template is filled in. No generation, so no
invented answers. It also runs when Ollama is not available.
"""

import re
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from callverse.agents.advisor.intent_classifier import IntentClassifier
from callverse.agents.advisor.prompts import ADVISOR_SYSTEM, NO_CONTEXT, format_context
from callverse.agents.advisor.tools import AdvisorTools, tool_schemas
from callverse.data.conversations import (
    CLOSINGS,
    ESCALATION_CHUNK,
    GREETINGS,
    SUPERVISOR_REPLIES,
    SUPERVISOR_SUMMARY,
    VERIFY_CHUNK,
    VERIFY_REQUESTS,
    answer_and_summary,
)
from callverse.data.tickets import REFUND_INTENTS, decide_outcome
from callverse.llm import LLMClient, LLMUnavailableError

ORDER_ID = re.compile(r"\b[0-9a-f]{32}\b")
ASKS_ORDER = re.compile(r"order (number|id|no)", re.I)
NO_ORDER_YET = (
    "You do not have the order number yet. Greet the customer and ask for the order number "
    "before anything else. Never invent an order number."
)
POLICY_DECISION = (
    "POLICY DECISION from the company rules engine (already applied to this order; follow it "
    'exactly):\n- action: {action}\n- hand over to: {handover}\n- approved answer: "{answer}"\n'
    "If you have not given this answer yet, rewrite it for the customer in a warm, natural way, "
    "keeping every fact, date, timing and next step and adding nothing. If you already gave it, "
    "reply to the customer's latest message consistently with it (close politely if they thank you)."
)
SUPERVISOR_WORDS = re.compile(r"supervisor|manager|someone (more )?senior|not acceptable", re.I)


@dataclass
class AdvisorMemory:
    """What the advisor remembers between turns of one conversation."""

    intent: str | None = None
    intent_group: str | None = None
    intent_confidence: float = 0.0
    order_id: str | None = None
    answered: bool = False
    summary: str = ""
    outcome: str | None = None
    handed_to: str | None = None
    escalated: bool = False
    decision: dict[str, Any] | None = None


@dataclass
class AdvisorReply:
    """One advisor message with everything needed for traces and evaluation."""

    text: str
    mode: str
    stage: str
    sources: list[str] = field(default_factory=list)
    retrieval: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    model: str | None = None
    latency_ms: float = 0.0
    tokens: int = 0


def find_order_id(messages: list[dict[str, Any]]) -> str | None:
    """Order number quoted by the customer, if any."""
    for message in reversed(messages):
        if message["speaker"] == "customer":
            match = ORDER_ID.search(str(message["text"]))
            if match:
                return match.group(0)
    return None


class AdvisorAgent:
    """Answers customers with the knowledge base, the order tools and an LLM."""

    def __init__(
        self,
        retriever: Any,
        classifier: IntentClassifier,
        llm: LLMClient | None = None,
        mode: str = "auto",
        top_k: int = 3,
        max_tool_rounds: int = 4,
        no_answer_score: float | None = None,
        seed: int = 0,
        variant: str = "rag_policy",
    ) -> None:
        self.retriever = retriever
        self.classifier = classifier
        self.llm = llm
        self.mode = mode
        self.top_k = top_k
        self.max_tool_rounds = max_tool_rounds
        self.no_answer_score = no_answer_score
        self.rng = np.random.default_rng(seed)
        self.variant = variant

    def use_llm(self) -> bool:
        if self.mode == "template" or self.llm is None:
            return False
        return self.mode == "llm" or self.llm.available()

    # ------------------------------------------------------------------ public
    def reply(
        self, messages: list[dict[str, Any]], memory: AdvisorMemory, tools: AdvisorTools
    ) -> AdvisorReply:
        """Next advisor message given the conversation so far."""
        if memory.intent is None:
            first = next(m["text"] for m in messages if m["speaker"] == "customer")
            prediction = self.classifier.predict(str(first))
            memory.intent, memory.intent_group = prediction.intent, prediction.intent_group
            memory.intent_confidence = prediction.confidence
        memory.order_id = memory.order_id or find_order_id(messages)
        calls_before = len(tools.calls)
        if self.use_llm():
            try:
                reply = self._llm_reply(messages, memory, tools)
            except LLMUnavailableError:
                reply = self._template_reply(messages, memory, tools)
                reply.mode = "template_fallback"
        else:
            reply = self._template_reply(messages, memory, tools)
        reply.tool_calls = [
            {
                "name": c.name,
                "arguments": c.arguments,
                "ok": c.ok,
                "result": c.result,
                "latency_ms": round(c.latency_ms, 1),
            }
            for c in tools.calls[calls_before:]
        ]
        return reply

    # --------------------------------------------------------------- retrieval
    def retrieve(self, messages: list[dict[str, Any]], intent: str | None) -> list:
        customer = [str(m["text"]) for m in messages if m["speaker"] == "customer"]
        query = " ".join(customer[:1] + customer[-1:]) if customer else ""
        return self.retriever.search(query, top_k=self.top_k) if self.retriever else []

    # ------------------------------------------------------------- template mode
    def _pick(self, options: list[str]) -> str:
        return options[int(self.rng.integers(len(options)))]

    def _template_reply(
        self, messages: list[dict[str, Any]], memory: AdvisorMemory, tools: AdvisorTools
    ) -> AdvisorReply:
        started = time.perf_counter()
        last = str(messages[-1]["text"]) if messages else ""
        if memory.answered and SUPERVISOR_WORDS.search(last) and not memory.escalated:
            tools.open_ticket(memory.order_id or "unknown", "customer asked for a supervisor", "supervisor")
            memory.escalated = True
            memory.summary += SUPERVISOR_SUMMARY
            return AdvisorReply(
                self._pick(SUPERVISOR_REPLIES),
                "template",
                "escalate",
                [ESCALATION_CHUNK],
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        if memory.order_id is None:
            return AdvisorReply(
                f"{self._pick(GREETINGS)} {self._pick(VERIFY_REQUESTS)}",
                "template",
                "verify",
                [VERIFY_CHUNK],
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        if not memory.answered:
            lookup = tools.lookup_order(memory.order_id)
            facts = tools.order_facts(memory.order_id, memory.intent)
            if facts is None:
                return AdvisorReply(
                    "I could not find this order number. Could you check it and send it again, please?",
                    "template",
                    "verify",
                    [VERIFY_CHUNK],
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            if memory.intent in REFUND_INTENTS or memory.intent == "cancel_order":
                tools.check_refund_eligibility(memory.order_id)
            row = pd.Series({**facts, "intent": memory.intent})
            outcome, chunk, handed_to = decide_outcome(row)
            row["outcome"] = outcome
            answer, summary = answer_and_summary(row)
            if handed_to:
                tools.open_ticket(memory.order_id, outcome.replace("_", " "), handed_to)
            memory.answered, memory.summary = True, summary
            memory.outcome, memory.handed_to = outcome, handed_to
            _ = lookup
            return AdvisorReply(
                answer, "template", "answer", [chunk], latency_ms=(time.perf_counter() - started) * 1000
            )
        return AdvisorReply(
            self._pick(CLOSINGS).format(summary=memory.summary),
            "template",
            "close",
            ["advisor_playbook__s05"],
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    # ------------------------------------------------------------------ LLM mode
    def _policy_decision(self, memory: AdvisorMemory, tools: AdvisorTools) -> dict[str, Any] | None:
        """Hybrid variant: order lookup + rules engine as deterministic pipeline steps."""
        if not memory.order_id:
            return None
        if memory.decision is not None:
            return memory.decision
        if "error" in tools.lookup_order(memory.order_id):
            return None
        if memory.intent in REFUND_INTENTS or memory.intent == "cancel_order":
            tools.check_refund_eligibility(memory.order_id)
        result = tools.recommend_resolution(memory.order_id, memory.intent or "track_order")
        if "error" in result:
            return None
        memory.outcome, memory.handed_to = result["recommended_action"], result["hand_over_to"]
        if result["hand_over_to"]:
            tools.open_ticket(
                memory.order_id, result["recommended_action"].replace("_", " "), result["hand_over_to"]
            )
        memory.answered, memory.summary = True, result["summary"]
        memory.decision = {
            "action": result["recommended_action"],
            "handover": result["hand_over_to"] or "nobody",
            "answer": result["approved_answer"],
            "policy_section": result["policy_section"],
        }
        return memory.decision

    def _llm_reply(
        self, messages: list[dict[str, Any]], memory: AdvisorMemory, tools: AdvisorTools
    ) -> AdvisorReply:
        assert self.llm is not None
        hits = self.retrieve(messages, memory.intent)
        context = format_context(hits)
        if (
            self.no_answer_score is not None
            and hits
            and hits[0].score < self.no_answer_score
            and type(self.retriever).__name__ == "KnowledgeRetriever"
        ):
            context = NO_CONTEXT
        system = ADVISOR_SYSTEM.format(
            today=tools.as_of.strftime("%Y-%m-%d"), intent=memory.intent, context=context
        )
        sources = [h.chunk.chunk_id for h in hits]
        chat: list[dict[str, Any]] = [{"role": "system", "content": system}]
        # Tool gating: order tools exist only once the customer gave an order number,
        # so a small model cannot call them with invented ids.
        offered = tool_schemas(self.variant)
        if memory.order_id:
            chat.append({"role": "system", "content": f"The customer's order number is {memory.order_id}."})
        else:
            offered = [t for t in offered if t["function"]["name"] == "search_knowledge_base"]
            chat.append({"role": "system", "content": NO_ORDER_YET})
        if self.variant == "rag_policy":
            # Hybrid: the rules engine decides (deterministic pipeline steps), the LLM writes.
            allowed = {"search_knowledge_base", "open_ticket"}
            offered = [t for t in offered if t["function"]["name"] in allowed]
            decision = self._policy_decision(memory, tools)
            if decision:
                sources.append(decision["policy_section"])
                chat.append({"role": "system", "content": POLICY_DECISION.format(**decision)})
        for message in messages:
            role = "user" if message["speaker"] == "customer" else "assistant"
            chat.append({"role": role, "content": str(message["text"])})

        total_tokens, latency, model = 0, 0.0, None
        for _ in range(self.max_tool_rounds + 1):
            response = self.llm.chat("advisor", chat, tools=offered or None, agent="advisor")
            total_tokens += response.prompt_tokens + response.completion_tokens
            latency += response.latency_ms
            model = response.model
            if not response.tool_calls:
                text = response.content.strip()
                break
            chat.append(
                {
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": [
                        {"function": {"name": c["name"], "arguments": c["arguments"]}}
                        for c in response.tool_calls
                    ],
                }
            )
            for call in response.tool_calls:
                result = tools.execute(call["name"], dict(call["arguments"]))
                if call["name"] == "search_knowledge_base":
                    sources += [r["chunk_id"] for r in eval_json(result).get("results", [])]
                if call["name"] == "open_ticket":
                    memory.handed_to = dict(call["arguments"]).get("handed_to")
                if call["name"] == "recommend_resolution":
                    decision = eval_json(result)
                    memory.outcome = decision.get("recommended_action", memory.outcome)
                    memory.handed_to = decision.get("hand_over_to") or memory.handed_to
                    if decision.get("policy_section"):
                        sources.append(decision["policy_section"])
                chat.append({"role": "tool", "content": result, "tool_name": call["name"]})
        else:
            text = ""
        if not text:
            raise LLMUnavailableError("The advisor model returned no answer.")
        if self.variant == "rag_policy" and memory.order_id is None and not ASKS_ORDER.search(text):
            # Compliance guardrail (playbook rule 1): verify the order before helping further.
            text = f"{text}\n\n{self._pick(VERIFY_REQUESTS)}"
        if memory.order_id and any(c.name == "lookup_order" and c.ok for c in tools.calls):
            memory.answered = True
        stage = "answer" if memory.answered else ("verify" if memory.order_id is None else "answer")
        return AdvisorReply(
            text,
            "llm",
            stage,
            list(dict.fromkeys(sources)),
            [
                {"chunk_id": h.chunk.chunk_id, "section": h.chunk.section, "score": round(h.score, 3)}
                for h in hits
            ],
            model=model,
            latency_ms=latency,
            tokens=total_tokens,
        )


def eval_json(text: str) -> dict[str, Any]:
    """Parse a tool result (JSON) without failing."""
    import json

    try:
        return json.loads(text)
    except ValueError:
        return {}
