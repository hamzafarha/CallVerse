import { AdvisorAvatar, Avatar, ToolChip, TypingDots, motion } from "@callverse/shared";
import { Gauge, ScanSearch, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

/** Scripted, looping preview of a chat (hero illustration). The real chat is on /chat. */
const SCRIPT: { who: "customer" | "advisor"; text: string; tools?: string[] }[] = [
  { who: "customer", text: "Hi! My order still hasn't arrived and the date has passed 😕" },
  { who: "advisor", text: "I'm sorry about the wait. Could you share your order number so I can check it?" },
  { who: "customer", text: "Sure: 9f2a…c41e" },
  {
    who: "advisor",
    text: "Thanks! Your parcel is 9 days late with no tracking movement, so I've opened a carrier investigation. You'll hear back within 5 business days.",
    tools: ["lookup_order", "recommend_resolution", "open_ticket"],
  },
];

export function HeroChatDemo() {
  const [round, setRound] = useState(0);
  const [step, setStep] = useState(0);
  const [typed, setTyped] = useState(0);

  useEffect(() => {
    if (step >= SCRIPT.length) {
      const reset = window.setTimeout(() => {
        setRound((r) => r + 1);
        setStep(0);
        setTyped(0);
      }, 4500);
      return () => window.clearTimeout(reset);
    }
    const current = SCRIPT[step];
    if (current.who === "advisor" && typed < current.text.length) {
      const t = window.setTimeout(() => setTyped((n) => n + 2), typed === 0 ? 1000 : 22);
      return () => window.clearTimeout(t);
    }
    const next = window.setTimeout(() => {
      setStep((s) => s + 1);
      setTyped(0);
    }, current.who === "customer" ? 900 : 1600);
    return () => window.clearTimeout(next);
  }, [step, typed]);

  const shown = SCRIPT.slice(0, Math.min(step + 1, SCRIPT.length));
  return (
    <div className="relative mx-auto w-full max-w-md">
      <motion.div
        initial={{ opacity: 0, x: 30, rotate: 2 }}
        animate={{ opacity: 1, x: 0, rotate: 0 }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        className="card ring-gradient overflow-hidden p-0 shadow-lift"
      >
        <div className="flex items-center gap-3 border-b border-line px-4 py-3">
          <AdvisorAvatar size={34} />
          <div>
            <div className="text-sm font-semibold text-ink">CallVerse assistant</div>
            <div className="flex items-center gap-1.5 text-[11px] text-muted">
              <span className="live-dot" /> online · AI + policy rules
            </div>
          </div>
        </div>
        <div className="flex h-[380px] flex-col justify-end gap-3 overflow-hidden bg-raised p-4 pb-12">
          {shown.map((message, i) => {
            const writing = message.who === "advisor" && i === step;
            const text = writing ? message.text.slice(0, typed) : message.text;
            const mine = message.who === "customer";
            const complete = text.length === message.text.length;
            return (
              <motion.div
                key={`${round}-${i}`}
                initial={{ opacity: 0, y: 14, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ type: "spring", bounce: 0.3, duration: 0.5 }}
                className={`flex shrink-0 items-end gap-2 ${mine ? "flex-row-reverse" : ""}`}
              >
                {mine ? <Avatar name="Ana S" size={26} /> : <AdvisorAvatar size={26} />}
                <div className={`flex max-w-[82%] flex-col ${mine ? "items-end" : "items-start"}`}>
                  <div
                    className={`rounded-2xl px-3.5 py-2 text-[13px] leading-relaxed ${mine ? "rounded-br-md text-white" : "rounded-bl-md border border-line bg-surface text-ink"}`}
                    style={mine ? { background: "linear-gradient(135deg, var(--brand), var(--brand-2))" } : undefined}
                  >
                    {text ? <span className={writing && !complete ? "caret" : undefined}>{text}</span> : <TypingDots color="var(--brand)" />}
                  </div>
                  {message.tools && complete && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-1 flex flex-wrap gap-1 text-muted">
                      {message.tools.map((t) => (
                        <ToolChip key={t} name={t} />
                      ))}
                    </motion.div>
                  )}
                </div>
              </motion.div>
            );
          })}
        </div>
      </motion.div>
      <Floating className="-bottom-7 -left-8 hidden sm:flex" delay={0.6} icon={ScanSearch} title="Knowledge base" text="“Order late” · cosine 0.80" />
      <Floating className="-right-10 -top-6 hidden md:flex" delay={1} icon={Gauge} title="Workforce agent" text="WISMO desk · 12 s wait" />
      <Floating className="-bottom-7 -right-6 hidden md:flex" delay={1.4} icon={ShieldCheck} title="Quality review" text="4.8 / 5 · policy-correct" />
    </div>
  );
}

function Floating({ className, delay, icon: Icon, title, text }: { className: string; delay: number; icon: any; title: string; text: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay, type: "spring", bounce: 0.4 }}
      className={`glass absolute z-10 items-center gap-2.5 rounded-2xl px-3 py-2 shadow-lift ${className}`}
    >
      <div className="flex h-8 w-8 animate-float items-center justify-center rounded-xl bg-[var(--brand-soft)] text-brand">
        <Icon size={16} />
      </div>
      <div>
        <div className="text-[11px] font-semibold text-ink">{title}</div>
        <div className="text-[11px] text-muted">{text}</div>
      </div>
    </motion.div>
  );
}
