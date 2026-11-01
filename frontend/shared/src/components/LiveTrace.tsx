import { AnimatePresence, motion } from "framer-motion";
import { humanize, num } from "../lib/format";
import type { LiveState, StageEvent } from "../lib/session";
import { TOOL_LABEL } from "./chat";
import { Bar } from "./motion";
import { Bot, Cpu, Headset, ScanSearch, ShieldCheck, User, Wrench } from "lucide-react";

const ICON: Record<string, any> = { workforce: Headset, client: User, quality: ShieldCheck };

function describe(stage: StageEvent): { icon: any; title: string; detail?: string } | null {
  if (stage.agent === "workforce") return { icon: Headset, title: "Workforce agent routed the chat" };
  if (stage.agent === "quality") return { icon: ShieldCheck, title: "Quality agent reviewed the chat" };
  if (stage.agent === "client") return { icon: User, title: "Client agent wrote as the customer" };
  if (stage.step === "retrieval")
    return {
      icon: ScanSearch,
      title: "Searched the knowledge base",
      detail: (stage.hits ?? [])
        .slice(0, 3)
        .map((h: any) => `${h.section} (${Number(h.score).toFixed(2)})`)
        .join(" · "),
    };
  if (stage.step === "tool")
    return {
      icon: Wrench,
      title: `${TOOL_LABEL[stage.name] ?? stage.name} ${stage.ok ? "✓" : "✗"}`,
      detail: stage.arguments?.order_id ? `order ${String(stage.arguments.order_id).slice(0, 10)}… · ${num(stage.latency_ms, 0)} ms` : `${num(stage.latency_ms, 0)} ms`,
    };
  if (stage.step === "generation")
    return { icon: Cpu, title: stage.round > 0 ? "LLM writes again with the tool results" : "LLM writes the reply", detail: String(stage.model ?? "").split("/").pop() };
  return null;
}

/** "Behind the scenes" panel: what every agent did, as it happens. */
export function LiveTrace({ state }: { state: LiveState }) {
  const events = state.stages.map((s) => ({ stage: s, view: describe(s) })).filter((e) => e.view) as {
    stage: StageEvent;
    view: NonNullable<ReturnType<typeof describe>>;
  }[];
  const routing = state.routing;
  return (
    <div className="space-y-5">
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
