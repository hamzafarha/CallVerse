import { motion } from "framer-motion";
import { Bot, Cog, ShieldCheck, XCircle } from "lucide-react";
import type { StageEvent } from "../lib/session";
import { CALLER_LABEL, TOOL_LABEL } from "./chat";
import { clsx } from "./ui";

/** Every tool of the Advisor agent, by kind, with what it does in a few words. */
const TOOLBOX: { kind: string; tools: { name: string; what: string }[] }[] = [
  {
    kind: "Data",
    tools: [
      { name: "lookup_order", what: "status, dates and payment of the order" },
      { name: "get_ticket_history", what: "earlier tickets on this order" },
      { name: "get_customer_history", what: "the customer's other orders and tickets" },
      { name: "search_knowledge_base", what: "company policy sections (RAG)" },
    ],
  },
  {
    kind: "Rules",
    tools: [
      { name: "check_refund_eligibility", what: "which refund or return option applies" },
      { name: "recommend_resolution", what: "the rules engine chooses the action" },
    ],
  },
  { kind: "External API", tools: [{ name: "validate_bank_code", what: "bank code check (BrasilAPI, cached)" }] },
  {
    kind: "Actions",
    tools: [
      { name: "open_ticket", what: "hand the case to another team" },
      { name: "escalate_to_human", what: "pass the chat to a supervisor" },
    ],
  },
  { kind: "Checks", tools: [{ name: "check_draft_reply", what: "fact check of every draft" }] },
];

/** The four tools added for agentic tool calling. */
export const NEW_TOOLS = new Set(["get_customer_history", "validate_bank_code", "escalate_to_human", "check_draft_reply"]);

const CALLER_ICON: Record<string, any> = { llm: Bot, code: Cog, safety_net: ShieldCheck };
const CALLER_SHORT: Record<string, string> = { llm: "AI", code: "pipeline", safety_net: "safety net" };

interface Usage {
  counts: Record<string, number>; // by caller: llm, code, safety_net
  summary?: string;
  ok: boolean;
  thisTurn: boolean;
}

function modeHint(variant: string | undefined, offline: boolean): string {
  if (offline) return "Offline backup: tools run as fixed pipeline steps (no AI choice). The bank check and the escalation still run.";
  if (variant === "rag_policy") return "Hybrid: the pipeline opens the order and the rules engine decides; the AI only sees 2 tools. Choose Agentic to let the AI pick its tools and use the 4 new ones.";
  if (variant === "rag") return "Pure RAG: the AI decides alone with 5 tools, without the rules engine (ablation).";
  return "Agentic: the AI chooses among the offered tools; the rules engine, the safety nets and the fact check back it up.";
}

/** Live view of the Advisor agent's tools: what is offered now, what was used, by whom. */
export function ToolBox({ stages, variant, offline = false }: { stages: StageEvent[]; variant?: string; offline?: boolean }) {
  const advisor = stages.filter((s) => s.agent === "advisor");
  let turnStart = -1;
  advisor.forEach((s, i) => {
    if (s.step === "start") turnStart = i;
  });
  const usage: Record<string, Usage> = {};
  advisor.forEach((s, i) => {
    if (s.step !== "tool") return;
    const entry = (usage[s.name] ??= { counts: {}, ok: true, thisTurn: false });
    const caller = s.caller ?? "code";
    entry.counts[caller] = (entry.counts[caller] ?? 0) + 1;
    entry.summary = s.summary;
    entry.ok = !!s.ok && s.passed !== false;
    if (i > turnStart) entry.thisTurn = true;
  });
  let offered = new Set<string>();
  let required = false;
  for (let i = advisor.length - 1; i > turnStart; i--) {
    const s = advisor[i];
    if (s.step === "generation" && Array.isArray(s.offered)) {
      offered = new Set(s.offered);
      required = s.tool_choice === "required";
      break;
    }
  }
  const used = Object.values(usage).reduce((n, u) => n + Object.values(u.counts).reduce((a, b) => a + b, 0), 0);
  const byAi = Object.values(usage).reduce((n, u) => n + (u.counts.llm ?? 0), 0);

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Advisor tools</div>
        <div className="flex items-center gap-2 text-[10px] text-muted">
          {Object.entries(CALLER_ICON).map(([caller, Icon]) => (
            <span key={caller} className="inline-flex items-center gap-0.5">
              <Icon size={10} className={caller === "llm" ? "text-brand" : undefined} /> {CALLER_SHORT[caller]}
            </span>
          ))}
        </div>
      </div>
      <p className="mb-2.5 text-[11px] leading-snug text-ink2">
        {modeHint(variant, offline)} <span className="text-muted">{used ? `${used} call(s) so far, ${byAi} chosen by the AI.` : "No tool used yet."}</span>
      </p>
      <div className="space-y-2.5">
        {TOOLBOX.map((group) => (
          <div key={group.kind}>
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted">{group.kind}</div>
            <div className="space-y-1">
              {group.tools.map((tool) => (
                <ToolRow key={tool.name} name={tool.name} what={tool.what} usage={usage[tool.name]} offered={offered.has(tool.name)} required={required} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ToolRow({ name, what, usage, offered, required }: { name: string; what: string; usage?: Usage; offered: boolean; required: boolean }) {
  const active = usage?.thisTurn;
  const style = active
    ? { borderColor: "var(--brand)", background: "color-mix(in srgb, var(--brand) 7%, transparent)" }
    : offered
      ? { borderColor: "color-mix(in srgb, var(--brand) 45%, transparent)", borderStyle: "dashed" as const }
      : undefined;
  const line = usage?.summary || what;
  return (
    <motion.div layout className="rounded-lg border border-line px-2.5 py-1.5 text-xs transition-colors" style={style}>
      <div className="flex items-center gap-1.5">
        {usage && !usage.ok && <XCircle size={11} className="shrink-0 text-bad" />}
        <span className={clsx("truncate font-medium", usage || offered ? "text-ink" : "text-muted")}>{TOOL_LABEL[name] ?? name}</span>
        {NEW_TOOLS.has(name) && (
          <span className="shrink-0 rounded px-1 text-[9px] font-semibold uppercase text-brand" style={{ background: "color-mix(in srgb, var(--brand) 12%, transparent)" }}>
            new
          </span>
        )}
        <span className="ml-auto flex shrink-0 items-center gap-1.5 text-[10px] text-muted">
          {offered && <span className="font-semibold text-brand">{required ? "must choose" : "offered"}</span>}
          {usage &&
            Object.entries(usage.counts).map(([caller, count]) => {
              const Icon = CALLER_ICON[caller] ?? Cog;
              return (
                <span key={caller} className="inline-flex items-center gap-0.5" title={CALLER_LABEL[caller] ?? caller}>
                  <Icon size={10} className={caller === "llm" ? "text-brand" : undefined} />
                  {count}
                </span>
              );
            })}
        </span>
      </div>
      <div className={clsx("truncate text-[11px]", usage ? "text-ink2" : "text-muted")} title={line}>
        {line}
      </div>
    </motion.div>
  );
}
