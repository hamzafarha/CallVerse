/**
 * The "Behind the scenes" panel: a timeline of what each agent did during the chat (routing decision,
 * knowledge-base search, tool calls, LLM calls, the customer's tools, the review).
 */
import { AnimatePresence, motion } from "framer-motion";
import { humanize, num } from "../lib/format";
import type { LiveState, StageEvent } from "../lib/session";
import { CALLER_LABEL, TOOL_LABEL } from "./chat";
import { Bar } from "./motion";
import { Bot, Cpu, Headset, ScanSearch, ShieldCheck, User, Wrench } from "lucide-react";

// Fallback icon per agent.
const ICON: Record<string, any> = { workforce: Headset, client: User, quality: ShieldCheck };

/**
 * Turns one stage event from the server into a timeline line (icon, title, detail), or null to skip it.
 */
function describe(stage: StageEvent): { icon: any; title: string; detail?: string } | null {
  if (stage.agent === "workforce") return { icon: Headset, title: "Workforce agent routed the chat" };
  if (stage.agent === "quality") return { icon: ShieldCheck, title: "Quality agent reviewed the chat" };
  if (stage.agent === "client") {
    if (stage.step === "offer") return null; // shown in the tools panel
    if (stage.step === "tool")
      return {
        icon: User,
        title: `Customer ${stage.name === "send_evidence" ? "used" : "checked"} ${TOOL_LABEL[stage.name] ?? stage.name} ${stage.ok ? "✓" : "✗"} · ${CALLER_LABEL[stage.caller] ?? "chosen by the AI"}`,
        detail: [stage.summary, `${num(stage.latency_ms, 0)} ms`].filter(Boolean).join(" · "),
      };
    return { icon: User, title: "Client agent answers as the customer" };
  }
  // Advisor steps: knowledge-base search (top 3 sections with their similarity scores), tool calls, LLM
  // calls.
  if (stage.step === "retrieval")
    return {
      icon: ScanSearch,
      title: "Searched the knowledge base",
      detail: (stage.hits ?? [])
        .slice(0, 3)
        .map((h: any) => `${h.section} (${Number(h.score).toFixed(2)})`)
        .join(" · "),
    };
  if (stage.step === "tool") {
    // A tool counts as failed if it raised an error, or (fact check) if the draft did not pass.
    const ok = stage.ok && stage.passed !== false;
    const who = stage.caller ? ` · ${CALLER_LABEL[stage.caller] ?? stage.caller}` : "";
    return {
      icon: stage.caller === "llm" ? Bot : stage.caller === "safety_net" ? ShieldCheck : Wrench,
      title: `${TOOL_LABEL[stage.name] ?? stage.name} ${ok ? "✓" : "✗"}${who}`,
      detail: [stage.summary, `${num(stage.latency_ms, 0)} ms`].filter(Boolean).join(" · "),
    };
  }
  if (stage.step === "generation") {
    // Which LLM call: the first one, a new round with the tool results, or a rewrite after a failed fact
    // check. The detail lists the tools offered to the model ("must call one of" when tool_choice is
    // "required").
    const title =
      stage.reason === "fact_check"
        ? "Fact check failed: the LLM rewrites its draft"
        : stage.round > 0
          ? "LLM writes again with the tool results"
          : "LLM writes the reply";
    const offered = (stage.offered ?? []).map((n: string) => TOOL_LABEL[n] ?? n).join(", ");
    const model = String(stage.model ?? "").split("/").pop();
    const offer = stage.tool_choice === "required" ? "must call one of" : "tools offered";
    return { icon: Cpu, title, detail: offered ? `${model} · ${offer}: ${offered}` : model };
  }
  return null;
}

/** "Behind the scenes" panel: what every agent did, as it happens. */
export function LiveTrace({ state }: { state: LiveState }) {
  // Keep only the stages that have something to show.
  const events = state.stages.map((s) => ({ stage: s, view: describe(s) })).filter((e) => e.view) as {
    stage: StageEvent;
    view: NonNullable<ReturnType<typeof describe>>;
  }[];
  const routing = state.routing;
  return (
    <div className="space-y-5">
      {/* The Workforce agent's decision: predicted problem type, confidence, desk, expected wait (Erlang C)
         and agents on duty. */}
      {routing && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="rounded-2xl border border-line bg-raised p-4">
          <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-muted">
            <Headset size={13} /> Workforce agent decision
          </div>
          <div className="text-sm font-semibold text-ink">{humanize(routing.predicted_intent)}</div>
          <div className="mt-1.5 flex items-center gap-2 text-[11px] text-muted">
            confidence <Bar value={routing.confidence} /> {(routing.confidence * 100).toFixed(0)}%
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <div>
              <div className="text-muted">Desk</div>
              <div className="font-medium text-ink">{routing.assigned_desk}</div>
            </div>
            <div>
              <div className="text-muted">Specialty</div>
              <div className="font-medium text-ink">{humanize(routing.desk_specialty)}</div>
            </div>
            <div>
              <div className="text-muted">Expected wait (Erlang C)</div>
              <div className="font-medium text-ink">{routing.is_live ? `${num(routing.expected_wait_seconds, 1)} s` : "closed"}</div>
            </div>
            <div>
              <div className="text-muted">Agents on duty</div>
              <div className="font-medium text-ink">{routing.agents_on_duty}</div>
            </div>
          </div>
        </motion.div>
      )}
      {/* The timeline: a vertical line with one dot per event; the latest dot pulses while an agent works. */}
      <div className="relative space-y-3 pl-6">
        <div className="absolute bottom-2 left-[9px] top-2 w-px bg-line" />
        <AnimatePresence initial={false}>
          {events.map(({ stage, view }, i) => {
            const Icon = view.icon ?? ICON[stage.agent] ?? Bot;
            const latest = i === events.length - 1 && state.activeAgent !== null;
            return (
              <motion.div key={`${stage.at}-${i}`} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} className="relative">
                <span
                  className={`absolute -left-6 top-0.5 flex h-[18px] w-[18px] items-center justify-center rounded-full border border-line bg-surface ${latest ? "animate-pulse-ring text-brand" : "text-muted"}`}
                >
                  <Icon size={10} />
                </span>
                <div className="text-[13px] font-medium text-ink">{view.title}</div>
                {view.detail && <div className="mt-0.5 text-[11px] leading-snug text-muted">{view.detail}</div>}
              </motion.div>
            );
          })}
        </AnimatePresence>
        {!events.length && <div className="text-xs text-muted">Send a message to see the agents work.</div>}
      </div>
    </div>
  );
}
