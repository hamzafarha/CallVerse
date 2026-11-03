"""Customer Advisor agent (DSO2): Ask -> Retrieve -> LLM (+ tools) -> Reply.

Main idea A (agentic RAG): the advisor retrieves the relevant policy sections
(bge-m3 + FAISS), then a mid-size LLM with tool calling looks up the order in the
SQLite store, opens follow-up tickets, and writes the reply.

Backup (DSO2): question sorting + approved templates. The intent classifier
predicts the problem type, the order tools give the facts, the company rules
choose the outcome and an approved template is filled in. No generation, so no
invented answers. It also runs when no LLM can answer (no key, no quota, no GPU).

Variants of the LLM advisor: ``rag`` (the LLM decides alone with tools, ablation),
``rag_policy`` (pipeline steps open the order and run the rules engine, the LLM
writes) and ``agentic`` (the LLM chooses its tools in a ReAct loop with gating; the
rules engine still decides, safety nets catch what the LLM forgot and every draft is
fact-checked before it is sent).
"""

# How to read this file:
# - AdvisorMemory: what the advisor remembers during one chat (intent, order number, decision...).
# - AdvisorReply: one advisor message, with its sources, tools and timing.
# - AdvisorAgent.reply(): the entry point. It predicts the intent, finds the order number, then answers with
#   one of 4 strategies: templates (offline backup), rag, rag_policy (Hybrid) or agentic.
# - _template_reply(): rules + approved texts, no LLM at all.
# - _llm_reply(): the "rag" and "rag_policy" variants.
# - _agentic_reply(): the ReAct loop with gating, required tool calls, safety nets and the fact check
#   (reflection).
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from callverse.agents.advisor.draft_check import looks_portuguese
from callverse.agents.advisor.intent_classifier import IntentClassifier
from callverse.agents.advisor.prompts import (
    ADVISOR_SYSTEM,
    AGENTIC_RULES,
    ENGLISH_ONLY,
    NO_CONTEXT,
    REWRITE_DRAFT,
    SAFETY_NET_NOTE,
    format_context,
)
from callverse.agents.advisor.tools import AdvisorTools, agentic_tool_schemas, tool_schemas
from callverse.agents.client.evidence import attachments_text
from callverse.data.conversations import (
    BANK_CODE_OK,
    BANK_CODE_UNKNOWN,
    CLOSINGS,
    ESCALATION_CHUNK,
    EVIDENCE_THANKS,
    GREETINGS,
    SUPERVISOR_PROMISE,
    SUPERVISOR_REPLIES,
    SUPERVISOR_SUMMARY,
    VERIFY_CHUNK,
    VERIFY_REQUESTS,
    answer_and_summary,
)
from callverse.data.tickets import REFUND_INTENTS, decide_outcome
from callverse.llm import LLMClient, LLMUnavailableError

# The 3 LLM variants (see the docstring above).
VARIANTS = ("rag", "rag_policy", "agentic")
BANK_POLICY_CHUNK = "refund_policy__s05"  # boleto refunds: bank transfer after the bank details
# An Olist order number: exactly 32 hexadecimal characters.
ORDER_ID = re.compile(r"\b[0-9a-f]{32}\b")
ASKS_ORDER = re.compile(r"order (number|id|no)", re.I)
# A bank code written by the customer ("my bank code is 341"), for the boleto refund check
BANK_CODE = re.compile(r"\b(?:bank|code)\b\D{0,25}?\b(\d{1,5})\b", re.I)
# Extra system notes, added to the prompt in some situations.
NO_ORDER_YET = (
    "You do not have the order number yet. Greet the customer and ask for the order number "
    "before anything else. Never invent an order number."
)
# The rules engine's decision, given to the LLM to put into words (it must not change the facts).
POLICY_DECISION = (
    "POLICY DECISION from the company rules engine (already applied to this order; follow it "
    'exactly):\n- action: {action}\n- hand over to: {handover}\n- approved answer: "{answer}"\n'
    "If you have not given this answer yet, rewrite it for the customer in a warm, natural way, "
    "keeping every fact, date, timing and next step and adding nothing. If you already gave it, "
    "reply to the customer's latest message consistently with it (close politely if they thank you)."
)
# Words that mean "I want a human" (a supervisor request).
SUPERVISOR_WORDS = re.compile(r"supervisor|manager|someone (more )?senior|not acceptable", re.I)
# Playbook: a legal complaint, the consumer-protection agency (PROCON) or the press
LEGAL_WORDS = re.compile(
    r"\b(procon|lawyer|attorney|legal action|sue|court|press|journalist|newspaper|reclame aqui)\b", re.I
)


def escalation_due(last: str, answered_before: bool) -> bool:
    """Playbook "When to escalate": a legal threat at any time, or a supervisor request
    once the advisor has offered a solution."""
    return bool(LEGAL_WORDS.search(last)) or (answered_before and bool(SUPERVISOR_WORDS.search(last)))


@dataclass
class AdvisorMemory:
    """What the advisor remembers between turns of one conversation."""

    # intent: the predicted problem type (e.g. track_order); order_id: once the customer gives it; answered:
    # the solution was given; summary: a one-sentence recap used in the closing; outcome:
    # the rules engine's action; handed_to: the team that got a ticket; escalated: a supervisor was called;
    # decision: the full rules-engine decision.
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

    # stage: verify, answer, escalate, bank_check, evidence or close; sources: the policy sections used (for
    # the judge and the faithfulness metric).
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
        # retriever: the knowledge-base search (bge-m3 or TF-IDF); classifier: predicts the intent; top_k: how
        # many policy sections to read; max_tool_rounds: the limit of the ReAct loop.
        self.retriever = retriever
        self.classifier = classifier
        self.llm = llm
        self.mode = mode
        self.top_k = top_k
        self.max_tool_rounds = max_tool_rounds
        self.no_answer_score = no_answer_score
        self.rng = np.random.default_rng(seed)
        if variant not in VARIANTS:
            raise ValueError(f"Unknown advisor variant '{variant}' ({', '.join(VARIANTS)}).")
        self.variant = variant

    def use_llm(self) -> bool:
        """True when the LLM should be used (template mode, or no LLM -> rules only)."""
        if self.mode == "template" or self.llm is None:
            return False
        return self.mode == "llm" or self.llm.available()

    # ------------------------------------------------------------------ public
    def reply(
        self,
        messages: list[dict[str, Any]],
        memory: AdvisorMemory,
        tools: AdvisorTools,
        on_token: Callable[[str], None] | None = None,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> AdvisorReply:
        """Next advisor message given the conversation so far.

        ``on_token`` streams the LLM's visible text; ``on_event`` reports pipeline
        steps (``retrieval``, ``tool``, ``generation``) for the live UI.
        """
        # on_event: report each tool call to the live UI (Tools panel, trace) as soon as it runs.
        previous = tools.listener
        if on_event is not None:
            tools.listener = lambda call: on_event(
                "tool",
                {
                    "name": call.name,
                    "arguments": call.arguments,
                    "ok": call.ok,
                    "caller": call.caller,
                    "summary": call.summary,
                    "latency_ms": round(call.latency_ms, 1),
                    **({"passed": call.result["passed"]} if "passed" in call.result else {}),
                },
            )
        try:
            return self._reply(messages, memory, tools, on_token, on_event)
        finally:
            tools.listener = previous

    def _reply(
        self,
        messages: list[dict[str, Any]],
        memory: AdvisorMemory,
        tools: AdvisorTools,
        on_token: Callable[[str], None] | None,
        on_event: Callable[[str, dict[str, Any]], None] | None,
    ) -> AdvisorReply:
        # Step 1: predict the problem type from the customer's first message (once per chat).
        if memory.intent is None:
            first = next(m["text"] for m in messages if m["speaker"] == "customer")
            prediction = self.classifier.predict(str(first))
            memory.intent, memory.intent_group = prediction.intent, prediction.intent_group
            memory.intent_confidence = prediction.confidence
        # Step 2: find the 32-character order number in the customer's messages.
        memory.order_id = memory.order_id or find_order_id(messages)
        calls_before = len(tools.calls)
        # Step 3: answer with the LLM variant, or with templates (offline, or after an LLM failure).
        if self.use_llm():
            try:
                if self.variant == "agentic":
                    reply = self._agentic_reply(messages, memory, tools, on_token, on_event)
                else:
                    reply = self._llm_reply(messages, memory, tools, on_token, on_event)
            except LLMUnavailableError:
                reply = self._template_reply(messages, memory, tools)
                reply.mode = "template_fallback"
        else:
            reply = self._template_reply(messages, memory, tools)
        # Step 4: attach the tool calls made during this turn (for the UI, the judge and the KPIs).
        reply.tool_calls = [
            {
                "name": c.name,
                "arguments": c.arguments,
                "ok": c.ok,
                "result": c.result,
                "caller": c.caller,
                "summary": c.summary,
                "latency_ms": round(c.latency_ms, 1),
            }
            for c in tools.calls[calls_before:]
        ]
        return reply

    # --------------------------------------------------------------- retrieval
    def retrieve(self, messages: list[dict[str, Any]], intent: str | None) -> list:
        """Search the policy knowledge base with the customer's first and last messages."""
        customer = [str(m["text"]) for m in messages if m["speaker"] == "customer"]
        query = " ".join(customer[:1] + customer[-1:]) if customer else ""
        return self.retriever.search(query, top_k=self.top_k) if self.retriever else []

    # ------------------------------------------------------------- template mode
    def _pick(self, options: list[str]) -> str:
        """One template sentence at random (seeded, so reproducible)."""
        return options[int(self.rng.integers(len(options)))]

    def _template_reply(
        self, messages: list[dict[str, Any]], memory: AdvisorMemory, tools: AdvisorTools
    ) -> AdvisorReply:
        # The OFFLINE advisor: no LLM. It follows the playbook with rules and approved texts, so it can never
        # invent a fact.
        started = time.perf_counter()
        last = str(messages[-1]["text"]) if messages else ""
        # Rule 1: a supervisor request after the answer -> escalate.
        if memory.answered and SUPERVISOR_WORDS.search(last) and not memory.escalated:
            tools.escalate_to_human("customer asked for a supervisor", memory.order_id or "")
            memory.escalated = True
            memory.summary += SUPERVISOR_SUMMARY
            return AdvisorReply(
                self._pick(SUPERVISOR_REPLIES),
                "template",
                "escalate",
                [ESCALATION_CHUNK],
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        # Rule 2: no order number yet -> greet the customer and ask for it.
        if memory.order_id is None:
            return AdvisorReply(
                f"{self._pick(GREETINGS)} {self._pick(VERIFY_REQUESTS)}",
                "template",
                "verify",
                [VERIFY_CHUNK],
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        # Rule 3, the first answer: open the order, check refund eligibility if needed, let the rules engine
        # decide (decide_outcome) and fill in the approved answer.
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
        # Rule 4: the customer wrote a bank code (boleto refund) -> check it.
        bank_reply = self._bank_code_reply(last, tools)
        if bank_reply is not None:
            return AdvisorReply(
                bank_reply,
                "template",
                "bank_check",
                [BANK_POLICY_CHUNK],
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        # Rule 5: the customer sent the photos or the screenshot -> thank them.
        files = (messages[-1].get("meta") or {}).get("attachments") if messages else None
        if files:  # the customer sent the photos or the screenshot that were asked for
            labels = [str(f["label"]).lower() for f in files]
            names = labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]
            return AdvisorReply(
                EVIDENCE_THANKS.format(files=names),
                "template",
                "evidence",
                ["advisor_playbook__s05"],
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        # Rule 6: otherwise, close the chat with a summary.
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
        # Pipeline steps chosen by code (not by the LLM): open the order, check refunds, run the rules engine.
        if not memory.order_id:
            return None
        if memory.decision is not None:
            return memory.decision
        if "error" in tools.lookup_order(memory.order_id):
            return None
        if memory.intent in REFUND_INTENTS or memory.intent == "cancel_order":
            tools.check_refund_eligibility(memory.order_id)
        return self._forced_decision(memory, tools)

    def _forced_decision(self, memory: AdvisorMemory, tools: AdvisorTools) -> dict[str, Any] | None:
        """Rules engine, always run by code once the order is open (DSO2: the small LLM must
        not choose the action); opens the policy hand-over ticket."""
        if memory.decision is not None:
            return memory.decision
        # recommend_resolution = the company rules engine (the same rules as the ticket history).
        result = tools.recommend_resolution(memory.order_id, memory.intent or "track_order")
        if "error" in result:
            return None
        memory.outcome = result["recommended_action"]
        memory.handed_to = result["hand_over_to"] or memory.handed_to
        # Some actions belong to another team (carrier, seller, payments): open a ticket for them.
        if result["hand_over_to"]:
            tools.open_ticket(
                memory.order_id, result["recommended_action"].replace("_", " "), result["hand_over_to"]
            )
        memory.answered = True
        memory.summary = result["summary"] + (SUPERVISOR_SUMMARY if memory.escalated else "")
        # Remember the decision: it is given to the LLM in every later turn.
        memory.decision = {
            "action": result["recommended_action"],
            "handover": result["hand_over_to"] or "nobody",
            "answer": result["approved_answer"],
            "policy_section": result["policy_section"],
        }
        return memory.decision

    def _policy_context(self, hits: list) -> str:
        """Retrieved policy extracts, or the "no answer" note when the best match is weak."""
        # If the best search score is too low, say "no policy covers this" instead of weak extracts.
        if (
            self.no_answer_score is not None
            and hits
            and hits[0].score < self.no_answer_score
            and type(self.retriever).__name__ == "KnowledgeRetriever"
        ):
            return NO_CONTEXT
        return format_context(hits)

    def _llm_reply(
        self,
        messages: list[dict[str, Any]],
        memory: AdvisorMemory,
        tools: AdvisorTools,
        on_token: Callable[[str], None] | None = None,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> AdvisorReply:
        assert self.llm is not None
        # 1) Retrieve the policy sections (RAG) and show them in the live trace.
        hits = self.retrieve(messages, memory.intent)
        if on_event is not None:
            on_event(
                "retrieval",
                {"hits": [{"section": h.chunk.section, "score": round(h.score, 3)} for h in hits]},
            )
        context = self._policy_context(hits)
        # 2) The system prompt: today's date (the twin replays history), the intent and the policy extracts.
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
            chat.append({"role": role, "content": attachments_text(message)})  # text + attached files

        # 3) The tool loop: call the LLM; if it asks for tools, run them, add their results to the chat and
        # call it again (at most max_tool_rounds times).
        total_tokens, latency, model = 0, 0.0, None
        for round_number in range(self.max_tool_rounds + 1):
            if on_event is not None:
                on_event(
                    "generation",
                    {
                        "round": round_number,
                        "model": self.llm.resolve_model("advisor"),
                        "offered": [t["function"]["name"] for t in offered],
                    },
                )
            response = self.llm.chat(
                "advisor", chat, tools=offered or None, agent="advisor", on_token=on_token
            )
            total_tokens += response.prompt_tokens + response.completion_tokens
            latency += response.latency_ms
            model = response.model
            # No tool call: this is the final answer.
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
            # Run each requested tool and remember what it changes (sources, ticket team, decision).
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
        # The loop ran out of rounds without a final answer.
        else:
            text = ""
        if text and looks_portuguese(text):
            # Language guardrail: regenerate once in English (no tools, same context).
            if on_event is not None:
                on_event("generation", {"round": round_number + 1, "model": model, "reason": "english"})
            chat += [{"role": "assistant", "content": text}, {"role": "user", "content": ENGLISH_ONLY}]
            retry = self.llm.chat("advisor", chat, agent="advisor", on_token=on_token)
            total_tokens += retry.prompt_tokens + retry.completion_tokens
            latency += retry.latency_ms
            text = retry.content.strip() if not looks_portuguese(retry.content) else ""
        # No usable text: the caller falls back to the template advisor.
        if not text:
            raise LLMUnavailableError("The advisor model returned no usable answer.")
        if self.variant == "rag_policy" and memory.order_id is None and not ASKS_ORDER.search(text):
            # Compliance guardrail (playbook rule 1): verify the order before helping further.
            text = f"{text}\n\n{self._pick(VERIFY_REQUESTS)}"
        # The answer counts as given once the order was really looked up.
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

    # -------------------------------------------------------------- agentic mode
    @staticmethod
    def _stage(memory: AdvisorMemory) -> str:
        """``verify`` (no order number), ``investigate`` (no decision yet) or ``follow_up``."""
        if not memory.order_id:
            return "verify"
        return "investigate" if memory.decision is None else "follow_up"

    @staticmethod
    def _looked_up(memory: AdvisorMemory, tools: AdvisorTools) -> bool:
        """True when lookup_order already ran successfully on THIS order number."""
        return any(
            c.name == "lookup_order"
            and c.ok
            and str(c.arguments.get("order_id", "")).strip() == memory.order_id
            for c in tools.calls
        )

    @staticmethod
    def _paid_by_boleto(tools: AdvisorTools) -> bool:
        """True when the order lookup showed a boleto payment (refund by bank transfer)."""
        return any(c.ok and c.result.get("payment_type") == "boleto" for c in tools.calls)

    @staticmethod
    def _mark_escalated(memory: AdvisorMemory, sources: list[str]) -> None:
        """Remember that a supervisor now handles the case."""
        memory.escalated = True
        memory.handed_to = memory.handed_to or "supervisor"
        memory.summary += SUPERVISOR_SUMMARY
        sources.append(ESCALATION_CHUNK)

    def _remember(
        self, name: str, arguments: dict[str, Any], result: str, memory: AdvisorMemory, sources: list[str]
    ) -> None:
        """What a tool call chosen by the LLM changes in the conversation memory."""
        data = eval_json(result)
        if name == "search_knowledge_base":
            sources += [r["chunk_id"] for r in data.get("results", [])]
        elif name == "open_ticket" and "error" not in data:
            memory.handed_to = arguments.get("handed_to") or memory.handed_to
        elif name == "escalate_to_human" and "error" not in data and not memory.escalated:
            self._mark_escalated(memory, sources)

    def _inject_decision(
        self,
        memory: AdvisorMemory,
        tools: AdvisorTools,
        chat: list[dict[str, Any]],
        sources: list[str],
        note: str | None = None,
    ) -> bool:
        """Forced step: once the order is open, the rules engine decides and its decision
        joins the chat for the LLM to put into words."""
        decision = self._forced_decision(memory, tools)
        if decision is None:
            return False
        sources.append(decision["policy_section"])
        text = POLICY_DECISION.format(**decision)
        chat.append({"role": "system", "content": f"{note}\n{text}" if note else text})
        return True

    def _bank_code_reply(self, last: str, tools: AdvisorTools) -> str | None:
        """Boleto refund: the customer wrote a bank code, so check it (external API) and
        answer with the approved text. Used by the template backup and as a safety net."""
        # Find a 1-5 digit number after "bank" or "code" in the customer's message.
        match = BANK_CODE.search(last)
        if match is None or not self._paid_by_boleto(tools):
            return None
        # validate_bank_code checks the BrasilAPI bank list (cached on disk).
        result = tools.validate_bank_code(match.group(1))
        if "error" in result:
            return None
        if result["valid"]:
            return BANK_CODE_OK.format(code=result["bank_code"], bank=result["bank_name"])
        return BANK_CODE_UNKNOWN.format(code=result["bank_code"])

    def _safe_text(self, memory: AdvisorMemory, decided_now: bool, escalated_now: bool) -> str:
        """Approved text when the LLM's draft cannot be used (empty or failed the check twice)."""
        if memory.order_id is None:
            return f"{self._pick(GREETINGS)} {self._pick(VERIFY_REQUESTS)}"
        if decided_now and memory.decision:
            return memory.decision["answer"] + (f" {SUPERVISOR_PROMISE}" if escalated_now else "")
        if escalated_now:
            return self._pick(SUPERVISOR_REPLIES)
        if memory.decision:
            return self._pick(CLOSINGS).format(summary=memory.summary)
        return "I could not find this order number. Could you check it and send it again, please?"

    def _agentic_reply(
        self,
        messages: list[dict[str, Any]],
        memory: AdvisorMemory,
        tools: AdvisorTools,
        on_token: Callable[[str], None] | None = None,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> AdvisorReply:
        """Agentic variant: a ReAct loop (think -> call tools -> read the results -> answer).

        Each round the LLM only sees the tools of the current stage (gating) and chooses
        which ones to call; while the order is not opened yet a tool call is required
        (tool_choice "required": SmolLM3 never called a tool on its own). Code keeps three
        duties: the rules engine decides as soon as the order is open (forced); safety nets
        open the order, check a bank code or escalate when the LLM forgot or failed; every
        draft is fact-checked before it is sent (reflection: one rewrite, then the
        approved text).
        """
        assert self.llm is not None
        llm = self.llm
        # --- Preparation: retrieval, system prompt, chat history, and what must happen this turn.
        hits = self.retrieve(messages, memory.intent)
        if on_event is not None:
            on_event(
                "retrieval",
                {"hits": [{"section": h.chunk.section, "score": round(h.score, 3)} for h in hits]},
            )
        system = ADVISOR_SYSTEM.format(
            today=tools.as_of.strftime("%Y-%m-%d"), intent=memory.intent, context=self._policy_context(hits)
        )
        chat: list[dict[str, Any]] = [{"role": "system", "content": f"{system}\n{AGENTIC_RULES}"}]
        order_note = f"The customer's order number is {memory.order_id}." if memory.order_id else NO_ORDER_YET
        chat.append({"role": "system", "content": order_note})
        if memory.decision:
            chat.append({"role": "system", "content": POLICY_DECISION.format(**memory.decision)})
        for message in messages:
            role = "user" if message["speaker"] == "customer" else "assistant"
            chat.append({"role": role, "content": attachments_text(message)})  # text + attached files
        sources = [h.chunk.chunk_id for h in hits]
        last = next((str(m["text"]) for m in reversed(messages) if m["speaker"] == "customer"), "")
        decided_before, escalated_before = memory.decision is not None, memory.escalated
        # Playbook check: must this turn escalate (a legal threat, or a supervisor request after an answer)?
        escalate = not memory.escalated and escalation_due(last, decided_before)
        calls_before = len(tools.calls)
        usage: dict[str, Any] = {"tokens": 0, "latency": 0.0, "model": None}

        # generate(): one LLM call, reported to the live UI, with tokens and time added up.
        def generate(
            round_number: int, schemas: list[dict[str, Any]] | None, choice: str | None = None, **event: Any
        ) -> Any:
            if on_event is not None:
                data = {"round": round_number, "model": llm.resolve_model("advisor"), "tool_choice": choice}
                on_event("generation", {**data, **event})
            response = llm.chat(
                "advisor", chat, tools=schemas or None, agent="advisor", on_token=on_token, tool_choice=choice
            )
            usage["tokens"] += response.prompt_tokens + response.completion_tokens
            usage["latency"] += response.latency_ms
            usage["model"] = response.model
            return response

        # --- The ReAct loop: Reason (the LLM thinks) -> Act (calls tools) -> Observe (reads the results) ->
        # ... -> Answer.
        text, round_number = "", 0
        for round_number in range(self.max_tool_rounds + 1):
            # GATING: the tools offered depend on the stage: verify (no order number), investigate (order not
            # opened or not decided yet) or follow_up.
            stage = self._stage(memory)
            offered = agentic_tool_schemas(stage, memory.intent_group, self._paid_by_boleto(tools))
            names = [t["function"]["name"] for t in offered]
            # A tool call is required when the playbook demands an action: open the order before
            # answering (investigate), or escalate (first round). The LLM still chooses which
            # of the offered tools to call, and its arguments.
            must_escalate = escalate and round_number == 0 and not memory.escalated
            choice = "required" if stage == "investigate" or must_escalate else None
            response = generate(round_number, offered, choice, stage=stage, offered=names)
            if response.tool_calls:  # Act: run the tools the LLM chose, then let it read the results
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
                    self._remember(call["name"], dict(call["arguments"]), result, memory, sources)
                    chat.append({"role": "tool", "content": result, "tool_name": call["name"]})
                # FORCED STEP: once the order is open, the rules engine decides (code, not the LLM).
                if stage == "investigate" and self._looked_up(memory, tools):
                    self._inject_decision(memory, tools, chat, sources)
                continue
            text = response.content.strip()
            if stage == "investigate" and not self._looked_up(memory, tools):
                # Safety net: the LLM answered without opening the order, so code opens it.
                with tools.called_by("safety_net"):
                    opened = "error" not in tools.lookup_order(memory.order_id)
                if opened and self._inject_decision(memory, tools, chat, sources, SAFETY_NET_NOTE):
                    text = ""
                    continue
            elif stage == "investigate" and self._inject_decision(memory, tools, chat, sources):
                text = ""  # opened in an earlier turn but not decided yet: decide, then write
                continue
            break
        else:
            text = ""

        # --- Safety nets: code does what the playbook requires when the LLM forgot.
        mode = "llm"
        if escalate and not memory.escalated:
            # Safety net: the playbook says to escalate and the LLM did not.
            legal = bool(LEGAL_WORDS.search(last))
            reason = "legal threat (PROCON, lawyer or press)" if legal else "customer asked for a supervisor"
            with tools.called_by("safety_net"):
                tools.escalate_to_human(reason, memory.order_id or "", "high" if legal else "normal")
            self._mark_escalated(memory, sources)
            if text and "supervisor" not in text.lower():
                text = f"{text} {SUPERVISOR_PROMISE}"
        bank_checked = any(c.name == "validate_bank_code" for c in tools.calls[calls_before:])
        if decided_before and not bank_checked and BANK_CODE.search(last) and self._paid_by_boleto(tools):
            # Safety net: the customer gave a bank code and the LLM did not check it.
            with tools.called_by("safety_net"):
                bank_text = self._bank_code_reply(last, tools)
            if bank_text:
                text, mode, bank_checked = bank_text, "template_fallback", True

        # Reflection: every draft is fact-checked; one rewrite, then the approved text.
        decided_now = memory.decision is not None and not decided_before
        escalated_now = memory.escalated and not escalated_before
        approved = memory.decision["answer"] if memory.decision else ""
        policy = [h.chunk.text for h in hits]
        if not text:
            text, mode = self._safe_text(memory, decided_now, escalated_now), "template_fallback"
        elif mode == "llm":
            check = tools.check_draft_reply(text, approved, policy, memory.order_id)
            if not check["passed"]:
                problems = "\n".join(f"- {p}" for p in check["problems"])
                chat += [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": REWRITE_DRAFT.format(problems=problems)},
                ]
                retry = generate(round_number + 1, None, reason="fact_check", problems=check["problems"])
                text = retry.content.strip()
                if not text or not tools.check_draft_reply(text, approved, policy, memory.order_id)["passed"]:
                    text, mode = self._safe_text(memory, decided_now, escalated_now), "template_fallback"
        if memory.order_id is None and not ASKS_ORDER.search(text):
            # Compliance guardrail (playbook rule 1): verify the order before helping further.
            text = f"{text}\n\n{self._pick(VERIFY_REQUESTS)}"
        if memory.order_id is None:
            stage = "verify"
        elif escalated_now:
            stage = "escalate"
        else:
            stage = "bank_check" if bank_checked else "answer"
        return AdvisorReply(
            text,
            mode,
            stage,
            list(dict.fromkeys(sources)),
            [
                {"chunk_id": h.chunk.chunk_id, "section": h.chunk.section, "score": round(h.score, 3)}
                for h in hits
            ],
            model=usage["model"],
            latency_ms=usage["latency"],
            tokens=usage["tokens"],
        )


def eval_json(text: str) -> dict[str, Any]:
    """Parse a tool result (JSON) without failing."""
    import json

    try:
        return json.loads(text)
    except ValueError:
        return {}
