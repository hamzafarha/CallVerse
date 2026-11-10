/**
 * One advisor's history, opened by clicking a desk on the centre page: every finished chat that the Workforce
 * agent sent to this desk, newest first, with the Quality agent's scorecard of each one
 * (GET /api/centre/advisors/{id}). Click a chat to read the whole conversation and the judge's reasons.
 */
import { ErrorBox, GROUP_LABEL, Loading, QualityScore, TOOL_LABEL, clsx, humanize, num, useApi } from "@callverse/shared";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, Building2, ChevronDown, Globe, Mic, Phone, User, X, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Portrait, advisorName, lookFor } from "./people";

// Where the chat came from: the centre page's AI customers or its microphone, the customer portal, or a phone.
const CHANNEL: Record<string, { label: string; icon: LucideIcon }> = {
  centre: { label: "AI customer (centre)", icon: Building2 },
  visitor: { label: "Visitor at the centre (voice)", icon: Mic },
  web: { label: "Web chat", icon: Globe },
  phone: { label: "Phone call", icon: Phone },
};

/** "Mon 10 Nov, 14:05" from a time in seconds. */
function when(seconds: number): string {
  return new Date(seconds * 1000).toLocaleString("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

const scoreColor = (q: number | null | undefined) =>
  q == null ? "var(--text-muted)" : q >= 4 ? "var(--good)" : q >= 3 ? "var(--warning)" : "var(--critical)";

/** The side panel (it slides in from the right; Esc or a click outside closes it). */
export function AdvisorHistory({ advisorId, desk, onClose }: { advisorId: string | null; desk: number | null; onClose: () => void }) {
  useEffect(() => {
    if (!advisorId) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [advisorId, onClose]);
  return (
    <AnimatePresence>
      {advisorId && (
        <>
          <motion.div key="shade" className="fixed inset-0 z-[3000] bg-black/40" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          <motion.aside
            key="panel"
            role="dialog"
            aria-modal="true"
            aria-label={`${advisorName(advisorId)}: chats and Quality scores`}
            className="fixed inset-y-0 right-0 z-[3001] flex w-full max-w-[620px] flex-col border-l border-line bg-surface shadow-lift"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", bounce: 0.1, duration: 0.45 }}
          >
            <HistoryBody advisorId={advisorId} desk={desk} onClose={onClose} />
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function HistoryBody({ advisorId, desk, onClose }: { advisorId: string; desk: number | null; onClose: () => void }) {
  const { data, error, loading } = useApi<any>(`/api/centre/advisors/${encodeURIComponent(advisorId)}`);
  const [open, setOpen] = useState<string | null>(null);
  const name = advisorName(advisorId);
  const summary = data?.summary;
  const figures = [
    { label: "Chats", value: summary ? String(summary.chats) : "0" },
    { label: "Quality score", value: summary?.quality != null ? `${num(summary.quality, 1)}/5` : "–" },
    { label: "Solved first time", value: summary?.fcr != null ? `${Math.round(summary.fcr * 100)}%` : "–" },
    { label: "Customer rating", value: summary?.csat != null ? `${num(summary.csat, 1)}/5` : "–" },
  ];
  return (
    <>
      <header className="flex items-start gap-4 border-b border-line p-5">
        <Portrait role="advisor" look={lookFor(advisorId)} size={64} />
        <div className="min-w-0 flex-1">
          <div className="font-display text-xl font-semibold text-ink">{name}</div>
          <div className="mt-0.5 text-sm text-ink2">
            {desk != null && desk >= 0 ? `Desk ${desk + 1} · ` : ""}
            {advisorId} · Advisor agent
            {summary?.specialty ? ` · speciality: ${GROUP_LABEL[summary.specialty] ?? humanize(summary.specialty)}` : ""}
          </div>
        </div>
        <button className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close the history">
          <X size={18} />
        </button>
      </header>
      <div className="grid grid-cols-4 gap-2 border-b border-line p-4">
        {figures.map((figure) => (
          <div key={figure.label} className="rounded-xl bg-raised px-3 py-2 text-center">
            <div className="font-display text-lg font-semibold tabular text-ink">{figure.value}</div>
            <div className="text-[11px] text-muted">{figure.label}</div>
          </div>
        ))}
      </div>
      <div className="flex-1 space-y-2 overflow-y-auto p-4">
        {loading && !data && <Loading text="Reading the saved chats" />}
        {error && <ErrorBox error={error} />}
        {data && data.chats.length === 0 && (
          <p className="py-10 text-center text-sm text-muted">No finished chat at this desk yet. Send a customer in, and its chat appears here when it ends.</p>
        )}
        {data?.chats.map((chat: any) => (
          <ChatRow key={chat.id} chat={chat} advisor={name} open={open === chat.id} onToggle={() => setOpen(open === chat.id ? null : chat.id)} />
        ))}
      </div>
      <footer className="border-t border-line px-5 py-3 text-xs text-muted">
        Every chat the Workforce agent sent to this desk, saved when it ended. Scores: the Quality agent (5 criteria, each out of 5).
      </footer>
    </>
  );
}

/** One finished chat: score, customer, problem, channel, who answered, when, rating; open it for the details. */
function ChatRow({ chat, advisor, open, onToggle }: { chat: any; advisor: string; open: boolean; onToggle: () => void }) {
  const channel = CHANNEL[chat.channel] ?? CHANNEL.web;
  const ChannelIcon = channel.icon;
  const human = chat.advisor_side === "human";
  return (
    <div className="rounded-2xl border border-line bg-raised">
      <button className="flex w-full items-center gap-3 p-3 text-left" onClick={onToggle} aria-expanded={open}>
        <div className="flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-xl text-white" style={{ background: scoreColor(chat.quality) }}>
          <span className="font-display text-lg font-bold leading-none">{chat.quality == null ? "–" : num(chat.quality, 1)}</span>
          <span className="text-[9px] uppercase">/ 5</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-ink">
            {chat.customer} <span className="font-normal text-muted">· {humanize(chat.intent)}</span>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-ink2">
            <span className="inline-flex items-center gap-1">
              <ChannelIcon size={12} aria-hidden /> {channel.label}
            </span>
            <span className="inline-flex items-center gap-1">
              {human ? <User size={12} aria-hidden /> : <Bot size={12} aria-hidden />}
              {human ? "answered by a person" : "answered by the AI"}
            </span>
            <span>{when(chat.ended_at)}</span>
            {chat.csat != null && (
              <span title={`customer rating ${chat.csat}/5`} style={{ color: "var(--warning)" }}>
                {"★".repeat(chat.csat)}
                {"☆".repeat(Math.max(0, 5 - chat.csat))}
              </span>
            )}
          </div>
        </div>
        <ChevronDown size={16} className={clsx("shrink-0 text-muted transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="space-y-4 border-t border-line p-4">
              <QualityScore
                compact
                review={{
                  scorecard: {
                    overall: chat.quality,
                    scores: chat.scores,
                    correct: chat.correct,
                    resolved: chat.resolved,
                    judge: chat.judge,
                    model: chat.judge_model,
                    rationale: chat.rationale,
                  },
                  reference: chat.reference,
                }}
              />
              <div className="flex flex-wrap gap-2 text-xs text-ink2">
                <span className="chip">{chat.fcr ? "Solved at the first contact" : "Not solved at the first contact"}</span>
                {chat.compliant != null && <span className="chip">{chat.compliant ? "Compliant with the policy" : "Compliance issue"}</span>}
                <span className="chip">{chat.turns} messages</span>
                {chat.tokens > 0 && <span className="chip">{num(chat.tokens, 0)} AI tokens</span>}
                {chat.predicted_intent && chat.predicted_intent !== chat.intent && (
                  <span className="chip">routed as “{humanize(chat.predicted_intent)}”</span>
                )}
              </div>
              <Transcript messages={chat.messages} customer={chat.customer} advisor={human ? `${advisor} (a person)` : advisor} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** The whole conversation: the customer on the left, the advisor on the right, with the tools it used. */
function Transcript({ messages, customer, advisor }: { messages: any[]; customer: string; advisor: string }) {
  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold uppercase tracking-wider text-muted">Conversation</div>
      {messages.map((message, i) => {
        const mine = message.speaker === "advisor";
        return (
          <div key={i} className={clsx("max-w-[88%] rounded-2xl px-3 py-2 text-sm", mine ? "ml-auto bg-[var(--brand-soft)]" : "bg-sunken")}>
            <div className="mb-0.5 text-[11px] font-semibold text-muted">{mine ? advisor : customer}</div>
            <div className="whitespace-pre-wrap leading-snug text-ink">{message.text}</div>
            {message.tools?.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {message.tools.map((tool: string, j: number) => (
                  <span key={j} className="rounded-full border border-line bg-surface px-2 py-0.5 text-[10.5px] text-ink2">
                    {TOOL_LABEL[tool] ?? tool}
                  </span>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
