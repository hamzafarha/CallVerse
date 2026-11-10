/**
 * "Talk as a customer": a visitor of the defence speaks into the centre page's microphone and becomes a real
 * customer on the floor.
 *
 * It opens a real chat on /ws/session (the same as the customer portal), labelled "visitor": the visitor plays
 * a real customer from the history (a real Olist order); the Workforce agent routes the chat, the Advisor
 * agent answers, the Quality agent grades it at the end. The microphone turns speech into text (speech to
 * text, shared lib/speech.ts: click, speak, pause, it is sent). The advisor's answers are spoken on the floor by
 * the centre's voices (voices.ts), so the visitor watches and hears their own story there.
 */
import { ListeningHint, MicButton, humanize, useLiveSession, useSpeechInput } from "@callverse/shared";
import { motion } from "framer-motion";
import { Mic, PhoneOff, Send, Star, X } from "lucide-react";
import { useState } from "react";

export function VisitorPanel({ mode, onClose }: { mode: "auto" | "template"; onClose: () => void }) {
  const session = useLiveSession();
  const { state } = session;
  const [text, setText] = useState("");
  const [rating, setRating] = useState(0);
  const running = state.status === "running" && !state.ended;
  const speech = useSpeechInput((said) => {
    if (running) session.sendCustomer(said, "voice");
  });
  const profile = state.ready?.profile;
  const mine = state.messages.filter((m) => m.speaker === "customer");
  const answering = state.activeAgent !== null;
  // The same quick replies as the customer portal: the real first message, the order number (nobody can read
  // a 32-character id aloud), a supervisor request and a goodbye.
  const quick = profile
    ? [mine.length === 0 ? profile.opening_message : null, `My order number is ${profile.order_id}`, "Can I speak to a supervisor?", "Thanks, that's all."].filter(
        (q): q is string => !!q,
      )
    : [];

  const start = () =>
    session.start({ customer: "human", advisor: "agent", mode, variant: "rag_policy", seed: Math.floor(Math.random() * 1000), channel: "visitor" });
  const sendTyped = (value: string) => {
    if (!value.trim() || !running) return;
    session.sendCustomer(value.trim(), "text");
    setText("");
  };
  const close = () => {
    speech.cancel();
    session.reset(); // closes the chat: the customer leaves the floor
    onClose();
  };

  return (
    <motion.aside
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 16 }}
      className="fixed bottom-32 right-5 z-[2500] w-[380px] max-w-[calc(100vw-40px)] rounded-3xl border border-line bg-surface p-4 shadow-lift"
      role="dialog"
      aria-label="Talk as a customer"
    >
      <div className="mb-3 flex items-center gap-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-xl text-white" style={{ background: "#3b82f6" }}>
          <Mic size={16} />
        </span>
        <div className="flex-1 font-display text-base font-semibold text-ink">Talk as a customer</div>
        <button className="btn btn-ghost btn-icon" onClick={close} aria-label="Close and leave the centre">
          <X size={16} />
        </button>
      </div>

      {state.status === "idle" && (
        <div className="space-y-3 text-sm text-ink2">
          <p>
            You become a real customer from the history (a real Olist order). Speak into the microphone: the agents answer, and you
            see and hear your story on the floor.
          </p>
          <button className="btn btn-primary w-full" onClick={start}>
            <Mic size={15} /> Start my chat
          </button>
        </div>
      )}

      {state.status === "connecting" && <p className="text-sm text-muted">Opening your chat…</p>}

      {state.error && <p className="mb-2 rounded-xl bg-[color-mix(in_srgb,var(--critical)_12%,transparent)] px-3 py-2 text-xs text-ink">{state.error}</p>}

      {profile && (
        <div className="space-y-3">
          <div className="rounded-2xl bg-raised p-3 text-sm">
            <div className="font-semibold text-ink">You are {state.ready?.name}</div>
            <div className="text-ink2">
              Problem: <b className="text-ink">{humanize(profile.intent)}</b> · order <span className="font-mono">#{String(profile.order_id).slice(0, 8)}…</span>
            </div>
            {mine.length === 0 && profile.opening_message && (
              <div className="mt-1 text-xs text-muted">The real customer wrote: “{profile.opening_message}”</div>
            )}
          </div>

          {running && (
            <>
              <div className="flex items-center gap-3">
                <MicButton speech={speech} disabled={answering} className="h-14 w-14" />
                <div className="min-w-0 flex-1 text-sm">
                  {speech.listening ? (
                    <span className="text-ink">{speech.interim || "Listening…"}</span>
                  ) : answering ? (
                    <span className="text-muted">The agents are working: watch and listen on the floor…</span>
                  ) : (
                    <span className="text-ink2">Click the microphone, speak, then pause.</span>
                  )}
                </div>
              </div>
              <ListeningHint speech={speech} />
              {speech.error && <p className="text-xs" style={{ color: "var(--critical)" }}>{speech.error}</p>}
              <div className="flex flex-wrap gap-1.5">
                {quick.map((q) => (
                  <button key={q} className="chip text-left text-xs" onClick={() => sendTyped(q)} disabled={answering} title="Send this sentence">
                    {q.length > 48 ? `${q.slice(0, 46)}…` : q}
                  </button>
                ))}
              </div>
              <form
                className="flex gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  sendTyped(text);
                }}
              >
                <input className="field h-10 flex-1" value={text} onChange={(e) => setText(e.target.value)} placeholder="…or type here" aria-label="Type a message" />
                <button className="btn btn-soft btn-icon h-10 w-10" type="submit" disabled={!text.trim() || answering} aria-label="Send">
                  <Send size={15} />
                </button>
              </form>
              {mine.length > 0 && (
                <div className="space-y-2 border-t border-line pt-3">
                  <div className="text-xs text-ink2">When you are done, rate the chat and end it:</div>
                  <div className="flex items-center gap-1">
                    {[1, 2, 3, 4, 5].map((n) => (
                      <button key={n} onClick={() => setRating(n)} aria-label={`${n} star${n === 1 ? "" : "s"}`} className="p-0.5">
                        <Star size={22} fill={n <= rating ? "var(--warning)" : "none"} color="var(--warning)" />
                      </button>
                    ))}
                    <button className="btn btn-ghost ml-auto text-sm" onClick={() => session.end(rating || undefined)} disabled={answering}>
                      <PhoneOff size={15} /> End the chat
                    </button>
                  </div>
                </div>
              )}
            </>
          )}

          {state.ended && (
            <div className="space-y-2 text-sm text-ink2">
              <p>Thank you! The quality lead reviews your chat on the floor; it is then saved in the advisor's history.</p>
              <button className="btn btn-soft w-full" onClick={start}>
                <Mic size={15} /> Start another chat
              </button>
            </div>
          )}
        </div>
      )}
    </motion.aside>
  );
}
