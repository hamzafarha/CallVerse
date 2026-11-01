import { motion } from "framer-motion";
import { Bot, CheckCircle2, FileSearch, Sparkles, Wrench, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import type { ChatMessage, StageEvent } from "../lib/session";
import { Typewriter, TypingDots } from "./motion";
import { Avatar, clsx } from "./ui";

export const TOOL_LABEL: Record<string, string> = {
  lookup_order: "Order lookup",
  get_ticket_history: "Ticket history",
  check_refund_eligibility: "Refund eligibility",
  recommend_resolution: "Rules engine",
  open_ticket: "Ticket opened",
  search_knowledge_base: "Knowledge base",
};

/** Short, human description of what an agent is doing right now. */
export function stageLabel(stage: StageEvent | undefined): string {
  if (!stage) return "";
  if (stage.agent === "workforce") return "Workforce agent is routing the conversation…";
  if (stage.agent === "client") return "Customer is typing…";
  if (stage.agent === "quality") return "Quality agent is reviewing the conversation…";
  if (stage.step === "retrieval") return "Searching the help centre…";
  if (stage.step === "tool") return `${TOOL_LABEL[stage.name] ?? stage.name} ${stage.ok ? "✓" : "✗"}`;
  if (stage.step === "generation") return "Writing the answer…";
  return stage.kind === "draft" ? "Copilot is drafting…" : "Advisor is thinking…";
}

export function AdvisorAvatar({ size = 32 }: { size?: number }) {
  return (
    <div
      className="flex shrink-0 items-center justify-center rounded-full text-white shadow-glow"
      style={{ width: size, height: size, background: "linear-gradient(135deg, var(--brand), var(--brand-2))" }}
    >
      <Sparkles size={size * 0.5} />
    </div>
  );
}

export function ToolChip({ name, ok }: { name: string; ok?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-black/5 px-1.5 py-0.5 font-mono text-[10px] dark:bg-white/10">
      {ok === false ? <XCircle size={10} /> : <CheckCircle2 size={10} />} {TOOL_LABEL[name] ?? name}
    </span>
  );
}

function modeLabel(meta: Record<string, any> | undefined): string | null {
  if (!meta?.mode) return null;
  if (meta.mode === "llm") return `AI · ${String(meta.model ?? "").split("/").pop()?.replace("-bnb-4bit", "")}`;
  if (meta.mode === "human") return meta.copilot_draft ? (meta.copilot_edited ? "human · edited AI draft" : "human · AI draft") : "human";
  if (meta.mode === "template" || meta.mode === "template_fallback") return "approved template";
  if (meta.mode === "history") return "real customer message";
  if (meta.mode === "rule") return "simulated";
  return meta.mode;
}

/** One chat message. `mine` puts it on the right with the brand gradient. */
export function ChatBubble({
  message,
  mine,
  name,
  animate = false,
  showMeta = true,
}: {
  message: ChatMessage;
  mine: boolean;
  name?: string;
  animate?: boolean;
  showMeta?: boolean;
}) {
  const advisor = message.speaker === "advisor";
  const tools: any[] = message.meta?.tools ?? [];
  const sources: string[] = message.meta?.sources ?? [];
  const label = modeLabel(message.meta);
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", bounce: 0.3, duration: 0.5 }}
      className={clsx("flex items-end gap-2.5", mine ? "flex-row-reverse" : "flex-row")}
    >
      {advisor ? <AdvisorAvatar /> : <Avatar name={name ?? "Customer"} size={32} />}
      <div className={clsx("flex max-w-[80%] flex-col", mine ? "items-end" : "items-start")}>
        <div
          className={clsx(
            "whitespace-pre-wrap break-words rounded-2xl px-4 py-2.5 text-[14.5px] leading-relaxed shadow-soft",
            mine ? "rounded-br-md text-white" : "rounded-bl-md border border-line bg-surface text-ink",
          )}
          style={mine ? { background: "linear-gradient(135deg, var(--brand), color-mix(in srgb, var(--brand) 60%, var(--brand-2)))" } : undefined}
        >
          {animate ? <Typewriter text={message.text} /> : message.text}
        </div>
        {showMeta && (label || tools.length > 0 || sources.length > 0) && (
          <div className={clsx("mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted", mine && "justify-end")}>
            {label && <span>{label}</span>}
            {tools.map((t, i) => (
              <ToolChip key={i} name={t.name} ok={t.ok} />
            ))}
            {sources.length > 0 && (
              <span className="inline-flex items-center gap-1">
                <FileSearch size={11} /> {sources.length} source{sources.length > 1 ? "s" : ""}
              </span>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
}

/** The advisor's reply while it is being generated (token stream). */
export function StreamingBubble({ text, mine = false, label }: { text: string; mine?: boolean; label?: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={clsx("flex items-end gap-2.5", mine ? "flex-row-reverse" : "flex-row")}
    >
      <AdvisorAvatar />
      <div className="flex max-w-[80%] flex-col">
        <div className="ring-gradient whitespace-pre-wrap rounded-2xl rounded-bl-md bg-surface px-4 py-2.5 text-[14.5px] leading-relaxed text-ink shadow-soft">
          {text ? <span className="caret">{text}</span> : <TypingDots color="var(--brand)" />}
        </div>
        {label && <div className="mt-1.5 text-[11px] text-muted">{label}</div>}
      </div>
    </motion.div>
  );
}

/** "… is typing" row with the agent's current step. */
export function ActivityRow({ text, who = "advisor" }: { text: string; who?: "advisor" | "customer" | "system" }) {
  const Icon = who === "advisor" ? Bot : who === "customer" ? Sparkles : Wrench;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className="flex items-center gap-2 pl-11 text-xs text-muted"
    >
      <Icon size={13} className="text-brand" />
      <span>{text}</span>
      <TypingDots color="var(--text-muted)" />
    </motion.div>
  );
}
