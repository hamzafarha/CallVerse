import { motion } from "framer-motion";
import { Bot, Check, Database, Gauge, Headset, ScanSearch, ShieldCheck, Sparkles, User, type LucideIcon } from "lucide-react";
import { Fragment } from "react";
import type { AgentName, StageEvent } from "../lib/session";
import { clsx } from "./ui";

type NodeId = AgentName | "kpi";

const NODES: { id: NodeId; label: string; sub: string; icon: LucideIcon; color: string }[] = [
  { id: "client", label: "Client agent", sub: "plays the customer", icon: User, color: "var(--series-2)" },
  { id: "workforce", label: "Workforce agent", sub: "predicts intent · routes", icon: Headset, color: "var(--series-4)" },
  { id: "advisor", label: "Advisor agent", sub: "RAG · tools · LLM", icon: Bot, color: "var(--brand)" },
  { id: "quality", label: "Quality agent", sub: "LLM judge", icon: ShieldCheck, color: "var(--series-3)" },
  { id: "kpi", label: "KPI engine", sub: "BO2 indicators", icon: Gauge, color: "var(--series-1)" },
];

/** The LangGraph flow of one conversation, lit up as the agents work.
 *
 * `active` is the agent working now; `visited` the agents that already ran;
 * `stages` (optional) adds the advisor's current sub-steps under its node. */
export function AgentPipeline({
  active,
  visited,
  stages = [],
  done = false,
  humanCustomer = false,
  vertical = false,
}: {
  active: AgentName | null;
  visited: AgentName[];
  stages?: StageEvent[];
  done?: boolean;
  humanCustomer?: boolean;
  vertical?: boolean;
}) {
  const lastStart = stages.map((s) => s.agent === "advisor" && s.step === "start").lastIndexOf(true);
  const turn = lastStart >= 0 ? stages.slice(lastStart) : [];
  const steps = {
    retrieval: turn.find((s) => s.step === "retrieval"),
    tools: turn.filter((s) => s.step === "tool"),
    generation: turn.find((s) => s.step === "generation"),
  };
  const state = (id: NodeId): "active" | "done" | "idle" => {
    if (id === "kpi") return done ? "done" : "idle";
    if (active === id) return "active";
    return visited.includes(id) || done ? "done" : "idle";
  };
  return (
    <div className={clsx("flex flex-col", !vertical && "gap-2 md:flex-row md:items-stretch md:gap-0")}>
      {NODES.map((node, index) => {
        const s = state(node.id);
        const next = NODES[index + 1];
        const flowing = next && state(next.id) === "active";
        const Icon = node.icon;
        return (
          <Fragment key={node.id}>
            <motion.div
              animate={{ scale: s === "active" ? 1.03 : 1 }}
              transition={{ type: "spring", bounce: 0.4 }}
              className={clsx(
                "relative flex min-w-0 flex-1 flex-col rounded-2xl border p-3.5 transition-colors",
                s === "active" ? "ring-gradient border-transparent bg-surface shadow-glow" : "border-line bg-surface",
                s === "idle" && "opacity-60",
              )}
            >
              <div className="flex items-center gap-2.5">
                <div
                  className={clsx("relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-white", s === "active" && "animate-pulse-ring")}
                  style={{ background: s === "idle" ? "var(--surface-3)" : node.color, color: s === "idle" ? "var(--text-muted)" : "white", ["--ring-color" as any]: node.color }}
                >
                  <Icon size={17} />
                  {s === "done" && (
                    <motion.span
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      className="absolute -bottom-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full border-2 border-[var(--surface-1)] bg-good text-white"
                    >
                      <Check size={9} strokeWidth={4} />
                    </motion.span>
                  )}
                </div>
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-semibold text-ink">
                    {node.id === "client" && humanCustomer ? "You (customer)" : node.label}
                  </div>
                  <div className="truncate text-[11px] text-muted">{node.sub}</div>
                </div>
              </div>
              {node.id === "advisor" && (
                <div className="mt-2.5 flex flex-wrap gap-1">
                  <SubStep icon={ScanSearch} label="bge-m3" on={!!steps.retrieval} hot={active === "advisor" && !!steps.retrieval && !steps.generation} />
                  <SubStep icon={Database} label={steps.tools.length ? `${steps.tools.length} tool${steps.tools.length > 1 ? "s" : ""}` : "tools"} on={steps.tools.length > 0} hot={false} />
                  <SubStep icon={Sparkles} label="LLM" on={!!steps.generation} hot={active === "advisor" && !!steps.generation} />
                </div>
              )}
            </motion.div>
            {next && <Connector flowing={!!flowing} lit={state(next.id) !== "idle"} vertical={vertical} />}
          </Fragment>
        );
      })}
    </div>
  );
}

function SubStep({ icon: Icon, label, on, hot }: { icon: LucideIcon; label: string; on: boolean; hot: boolean }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium transition-colors",
        on ? "bg-[var(--brand-soft)] text-brand" : "bg-sunken text-muted",
        hot && "animate-pulse",
      )}
    >
      <Icon size={10} /> {label}
    </span>
  );
}

function Connector({ flowing, lit, vertical }: { flowing: boolean; lit: boolean; vertical: boolean }) {
  const stroke = lit ? "var(--brand)" : "var(--baseline)";
  const dash = flowing ? { animation: "flow 0.6s linear infinite" } : undefined;
  return (
    <div className={clsx("relative flex items-center justify-center", vertical ? "h-5" : "h-5 md:h-auto md:w-8")}>
      <svg className="h-full w-full overflow-visible" preserveAspectRatio="none" viewBox="0 0 32 20">
        {!vertical && (
          <line x1="0" y1="10" x2="32" y2="10" className="hidden md:block" stroke={stroke} strokeWidth="2" strokeDasharray="4 4" vectorEffect="non-scaling-stroke" style={dash} />
        )}
        <line x1="16" y1="0" x2="16" y2="20" className={vertical ? "" : "md:hidden"} stroke={stroke} strokeWidth="2" strokeDasharray="4 4" vectorEffect="non-scaling-stroke" style={dash} />
      </svg>
      {flowing && (
        <motion.span
          className={clsx("absolute h-2 w-2 rounded-full", vertical ? "left-[calc(50%-4px)]" : "hidden md:block")}
          style={{ background: "var(--brand-2)", boxShadow: "0 0 10px 2px var(--brand-2)", ...(vertical ? {} : { top: "calc(50% - 4px)" }) }}
          animate={vertical ? { top: ["0%", "70%"] } : { left: ["0%", "85%"] }}
          transition={{ duration: 0.8, repeat: Infinity, ease: "easeInOut" }}
        />
      )}
    </div>
  );
}
