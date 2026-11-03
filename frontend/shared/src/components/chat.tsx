/**
 * Chat pieces shared by the customer chat, the advisor desk and the back office: message bubbles, the chips
 * under a message (tools used, who wrote it), the streaming bubble, the "is typing" row, and labels that turn
 * tool and step names into plain words.
 */
import { motion } from "framer-motion";
import {
  AlertTriangle,
  AudioLines,
  Bot,
  CheckCircle2,
  FileSearch,
  Image as ImageIcon,
  ReceiptText,
  ShieldCheck,
  Sparkles,
  Timer,
  Volume2,
  Wrench,
  XCircle,
} from "lucide-react";
import type { ReactNode } from "react";
import type { ChatMessage, StageEvent } from "../lib/session";
import { Typewriter, TypingDots } from "./motion";
import { Avatar, clsx } from "./ui";

// Display names of the tools (Python name -> label under a message). The first ten are the Advisor agent's
// tools; the last three belong to the Client agent.
export const TOOL_LABEL: Record<string, string> = {
  lookup_order: "Order lookup",
  get_ticket_history: "Ticket history",
  get_customer_history: "Customer history",
  check_refund_eligibility: "Refund eligibility",
  recommend_resolution: "Rules engine",
  validate_bank_code: "Bank check",
  open_ticket: "Ticket opened",
  escalate_to_human: "Escalated to a human",
  search_knowledge_base: "Knowledge base",
  check_draft_reply: "Fact check",
  view_my_order_page: "My order page", // the Client agent's tools
  check_my_waiting_time: "My waiting time",
  send_evidence: "Send evidence",
};

/** Who decided to call a tool: the LLM itself, a fixed pipeline step, or a safety net. */
export const CALLER_LABEL: Record<string, string> = {
  llm: "chosen by the AI",
  code: "pipeline step",
  safety_net: "safety net",
};

/** Short, human description of what an agent is doing right now. */
export function stageLabel(stage: StageEvent | undefined): string {
  if (!stage) return "";
  if (stage.agent === "workforce") return "Workforce agent is routing the conversation…";
  // The Client agent: typing, or using one of its three tools.
  if (stage.agent === "client") {
    if (stage.step !== "tool") return "Customer is typing…";
    if (stage.name === "send_evidence") return "Customer is attaching a file…";
    return stage.name === "check_my_waiting_time" ? "Customer is looking at the clock…" : "Customer is reading their order page…";
  }
  if (stage.agent === "quality") return "Quality agent is reviewing the conversation…";
  if (stage.step === "retrieval") return "Searching the help centre…";
  if (stage.step === "tool") return `${TOOL_LABEL[stage.name] ?? stage.name} ${stage.ok ? "✓" : "✗"}`;
  if (stage.step === "generation") return stage.reason === "fact_check" ? "Fixing the draft after the fact check…" : "Writing the answer…";
  return stage.kind === "draft" ? "Copilot is drafting…" : "Advisor is thinking…";
}

/**
 * Round brand-colored icon that stands for the AI advisor.
 */
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

/**
 * Small label under a message, one per tool call: a tick or a cross (did the tool succeed?), the tool's name,
 * and who decided to call it (robot = the LLM chose it, shield = a safety net). Hover shows the tool's
 * summary.
 */
export function ToolChip({ name, ok, caller, summary }: { name: string; ok?: boolean; caller?: string; summary?: string }) {
  const title = [caller ? CALLER_LABEL[caller] ?? caller : null, summary].filter(Boolean).join(" · ");
  return (
    <span
      title={title || undefined}
      className="inline-flex items-center gap-1 rounded-md bg-black/5 px-1.5 py-0.5 font-mono text-[10px] dark:bg-white/10"
    >
      {ok === false ? <XCircle size={10} /> : <CheckCircle2 size={10} />} {TOOL_LABEL[name] ?? name}
      {caller === "llm" && <Bot size={10} className="text-brand" aria-label="chosen by the AI" />}
      {caller === "safety_net" && <ShieldCheck size={10} aria-label="safety net" />}
    </span>
  );
}

/** Short model name: "google/gemma-4-31b-it:free" -> "gemma-4-31b-it", "…SmolLM3-3B-bnb-4bit" -> "SmolLM3-3B". */
export function modelName(model: unknown): string {
  return String(model ?? "").split("/").pop()!.replace("-bnb-4bit", "").replace(/:free$/, "");
}

/**
 * Who or what wrote the message, in plain words (e.g. "AI · gemma-4-26b-a4b-it", "approved template", "real
 * customer message").
 */
function modeLabel(meta: Record<string, any> | undefined): string | null {
  if (!meta?.mode) return null;
  if (meta.mode === "llm") return `AI · ${modelName(meta.model)}`;
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
  speaking = false,
  onListen,
}: {
  message: ChatMessage;
  mine: boolean;
  name?: string;
  animate?: boolean;
  showMeta?: boolean;
  speaking?: boolean; // voice mode is reading this message
  onListen?: () => void; // read this message aloud
}) {
  // Everything shown under the bubble comes from message.meta, sent by the server with each message.
  const advisor = message.speaker === "advisor";
  const tools: any[] = message.meta?.tools ?? [];
  const sources: string[] = message.meta?.sources ?? [];
  const label = modeLabel(message.meta);
  // Client agent: true when what the advisor said contradicts the customer's order page
  const mismatch: boolean | undefined = message.meta?.mismatch;
  // Client agent: its chat timer showed it had waited longer than its patience
  const outOfPatience = tools.some((t) => t.name === "check_my_waiting_time" && t.result?.over_my_patience);
  // Client agent: files attached with send_evidence (simulated photos, statement screenshot)
  const attachments: any[] = message.meta?.attachments ?? [];
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", bounce: 0.3, duration: 0.5 }}
      className={clsx("flex items-end gap-2.5", mine ? "flex-row-reverse" : "flex-row")}
    >
      {/* Avatar, then the bubble; flex-row-reverse puts my own messages on the right. */}
      {advisor ? <AdvisorAvatar /> : <Avatar name={name ?? "Customer"} size={32} />}
      <div className={clsx("flex max-w-[80%] flex-col", mine ? "items-end" : "items-start")}>
        <div
          className={clsx(
            "whitespace-pre-wrap break-words rounded-2xl px-4 py-2.5 text-[14.5px] leading-relaxed shadow-soft",
            mine ? "rounded-br-md text-white" : "rounded-bl-md border border-line bg-surface text-ink",
          )}
          style={{
            ...(mine ? { background: "linear-gradient(135deg, var(--brand), color-mix(in srgb, var(--brand) 60%, var(--brand-2)))" } : {}),
            ...(speaking ? { boxShadow: "0 0 0 2px var(--brand)" } : {}),
          }}
        >
          {animate ? <Typewriter text={message.text} /> : message.text}
        </div>
        {/* Files sent by the customer (Client agent tool send_evidence). */}
        {attachments.length > 0 && <Attachments files={attachments} />}
        {/* The meta line: listen button, who wrote it, tool chips, Client agent warnings, number of
           sources. */}
        {showMeta && (label || tools.length > 0 || sources.length > 0 || onListen || speaking || mismatch !== undefined || outOfPatience) && (
          <div className={clsx("mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted", mine && "justify-end")}>
            {onListen && (
              <button
                type="button"
                onClick={onListen}
                title="Listen to this message"
                className={clsx("inline-flex items-center gap-1 rounded-md px-1 py-0.5 transition-colors hover:text-brand", speaking && "text-brand")}
              >
                {speaking ? <AudioLines size={12} className="animate-pulse" /> : <Volume2 size={12} />}
                {speaking ? "speaking…" : "Listen"}
              </button>
            )}
            {label && <span>{label}</span>}
            {/* One chip per tool call. For the fact check (check_draft_reply), "ok" means the draft passed. */}
            {tools.map((t, i) => (
              <ToolChip
                key={i}
                name={t.name}
                ok={t.name === "check_draft_reply" ? t.result?.passed !== false : t.ok}
                caller={t.caller}
                summary={t.summary}
              />
            ))}
            {/* The customer's order page says something else than the advisor (Client agent tool 1). */}
            {mismatch === true && (
              <span
                title="The customer compared the advisor's answer with their order page"
                className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-medium text-warn"
                style={{ background: "color-mix(in srgb, var(--warning) 14%, transparent)" }}
              >
                <AlertTriangle size={10} /> doesn't match my order page
              </span>
            )}
            {mismatch === false && tools.length > 0 && <span>matches my order page</span>}
            {/* The customer's chat timer went past its patience (Client agent tool 2). */}
            {outOfPatience && (
              <span
                title="The customer's chat timer showed a wait longer than its patience"
                className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-medium text-warn"
                style={{ background: "color-mix(in srgb, var(--warning) 14%, transparent)" }}
              >
                <Timer size={10} /> waited too long{message.meta?.end ? " · left the chat" : ""}
              </span>
            )}
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

/** Files the customer attached: simulated photos and statement screenshots, described from the real order. */
function Attachments({ files }: { files: any[] }) {
  return (
    <div className="mt-1.5 flex flex-col gap-1.5">
      {files.map((file, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 * i }}
          className="flex max-w-sm items-start gap-2.5 rounded-xl border border-line bg-surface px-2.5 py-2 text-xs shadow-soft"
          title="Simulated attachment: described from the customer's real order"
        >
          <div
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-brand"
            style={{ background: "color-mix(in srgb, var(--brand) 12%, transparent)" }}
          >
            {file.kind === "payment_statement" ? <ReceiptText size={18} /> : <ImageIcon size={18} />}
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-baseline gap-x-1.5 font-medium text-ink">
              {file.label}
              <span className="font-mono text-[10px] font-normal text-muted">{file.file}</span>
            </div>
            <div className="text-ink2">{file.description}</div>
          </div>
        </motion.div>
      ))}
    </div>
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
          {/* No text yet: three dots. Then the text grows with a blinking caret. */}
          {text ? <span className="caret">{text}</span> : <TypingDots color="var(--brand)" />}
        </div>
        {label && <div className="mt-1.5 text-[11px] text-muted">{label}</div>}
      </div>
    </motion.div>
  );
}

/** "… is typing" row with the agent's current step. */
export function ActivityRow({ text, who = "advisor" }: { text: string; who?: "advisor" | "customer" | "system" }) {
  // Icon by speaker: robot for the advisor, sparkles for the customer, wrench for the system.
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
