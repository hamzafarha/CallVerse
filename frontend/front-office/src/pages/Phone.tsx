/**
 * Phone page (/phone): a customer calls CallVerse from their phone and talks to the advisor.
 *
 * 1. Setup: the caller types a name and picks the problem (a new customer on a real order, feature 2), or
 *    gives an existing customer id. "Call" also unlocks the phone's speaker and microphone.
 * 2. Call: hands-free by default. The microphone listens (speech to text in the phone's browser), the
 *    sentence is sent when the caller pauses, and the advisor's answer is read aloud; then it listens again.
 *    On the PC, the advisor desk sees the call in its "Phone calls" list and can watch it or take over.
 * 3. Hang up: stars (CSAT), then the Quality agent's grade.
 *
 * Phones only give the microphone to https pages: start the site with `npm run dev:phone` (see
 * vite.config.ts) and open https://<PC address>:5173/phone on the same Wi-Fi.
 */
import {
  AnimatePresence,
  ChatBubble,
  LogoMark,
  StreamingBubble,
  TalkingAvatar,
  type AvatarState,
  clock,
  clsx,
  humanize,
  motion,
  postJson,
  useApi,
  useAutoSpeak,
  useLiveSession,
  useSpeechInput,
  useVoice,
} from "@callverse/shared";
import { Hash, Keyboard, Mic, MicOff, Phone, PhoneOff, RefreshCw, SendHorizonal, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { CsatDialog } from "../components/CsatDialog";

const STORE = "callverse.phone.call"; // the call in progress, to reconnect after the screen locked

function savedCall(): { id: string; name: string } | null {
  try {
    return JSON.parse(sessionStorage.getItem(STORE) ?? "null");
  } catch {
    return null;
  }
}

export default function PhonePage() {
  const options = useApi<any>("/api/portal/new-customer-options");
  const session = useLiveSession();
  const { state } = session;
  const voice = useVoice();
  const [step, setStep] = useState<"setup" | "call">("setup");
  const [name, setName] = useState("");
  const [intent, setIntent] = useState("track_order");
  const [existing, setExisting] = useState("");
  const [useExisting, setUseExisting] = useState(false);
  const [calling, setCalling] = useState(false);
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState("");
  const [rating, setRating] = useState(false);
  const [now, setNow] = useState(Date.now());
  const wake = useRef<any>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const resume = savedCall();

  // On a phone everything the advisor says is read aloud (a typed answer from the desk too).
  useAutoSpeak(state.messages, voice, (m) => (m.speaker === "advisor" ? { role: "advisor" } : null));
  const busy = session.busy;
  const ended = state.ended || !!state.review;
  const running = state.status === "running" && !ended;
  // Speech to text: every finished sentence is sent at once.
  const speech = useSpeechInput((said) => {
    if (!session.busy && state.status === "running") send(said, "voice");
    else toast("Wait for the advisor to finish, then speak again.");
  });
  const send = (message: string, via: "text" | "voice" = "text") => {
    if (!message.trim() || !running) return;
    voice.stop();
    session.sendCustomer(message.trim(), via);
    setText("");
  };

  // The call timer ticks; the newest message stays in view.
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [state.messages.length, state.streaming?.text, speech.interim]);
  // Remember the call id (to reconnect if the phone's screen locks and the connection drops).
  useEffect(() => {
    if (state.ready?.session_id) {
      try {
        sessionStorage.setItem(STORE, JSON.stringify({ id: state.ready.session_id, name: state.ready.name }));
      } catch {
        /* private mode: no reconnect */
      }
    }
  }, [state.ready?.session_id, state.ready?.name]);
  useEffect(() => {
    if (state.ended) {
      try {
        sessionStorage.removeItem(STORE);
      } catch {
        /* nothing saved */
      }
      wake.current?.release?.();
    }
  }, [state.ended]);
  useEffect(() => {
    if (state.error) toast.error(state.error);
  }, [state.error]);
  useEffect(() => {
    if (speech.error) {
      toast.error(speech.error, { id: "speech" });
      speech.clearError();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [speech.error]);
  // Like on a phone: when the caller starts talking, the advisor's voice stops.
  useEffect(() => {
    if (speech.listening) voice.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [speech.listening]);

  // Hands-free: once the advisor has answered and finished speaking, the microphone opens by itself.
  const heardUpTo = useRef(-2);
  useEffect(() => {
    if (step !== "call" || typing || !running || busy || speech.listening || speech.unavailable) return;
    if (voice.speaking !== null) return;
    const last = state.messages.length - 1;
    const turn = last < 0 ? -1 : state.messages[last].speaker === "advisor" ? last : null;
    if (turn === null || heardUpTo.current === turn) return;
    const timer = window.setTimeout(() => {
      heardUpTo.current = turn;
      speech.start();
    }, 700);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, typing, running, busy, speech.listening, voice.speaking, state.messages.length]);

  /** Keep the screen on during the call (a locked screen would cut the connection). */
  const keepAwake = async () => {
    try {
      wake.current = await (navigator as any).wakeLock?.request("screen");
    } catch {
      /* not supported: the reconnect button covers it */
    }
  };

  const call = async () => {
    const caller = name.trim() || "Customer";
    // Inside the tap: phones only let a page speak after a tap, so the greeting unlocks the speaker.
    voice.setEnabled(true);
    voice.speak("hello", `Hello ${caller.split(" ")[0]}. You are connected to CallVerse. How can I help you?`, "advisor");
    keepAwake();
    setCalling(true);
    try {
      let contactId = existing.trim();
      if (!useExisting || !contactId) {
        const card = await postJson("/api/portal/customers", { name: caller, persona: "normal", intent, order_source: "real" });
        contactId = card.contact_id;
      }
      heardUpTo.current = -2;
      // /phone?offline: approved template answers, no LLM call (a demo when the free quota is used up).
      const offline = new URLSearchParams(window.location.search).has("offline");
      session.start({
        contact_id: contactId,
        customer: "human",
        advisor: "agent",
        mode: offline ? "template" : "auto",
        variant: "agentic",
        channel: "phone",
      });
      setStep("call");
    } catch (e: any) {
      voice.stop();
      toast.error(e.message);
    } finally {
      setCalling(false);
    }
  };

  const reconnect = (id: string) => {
    voice.setEnabled(true);
    keepAwake();
    heardUpTo.current = Number.MAX_SAFE_INTEGER; // do not reopen the microphone for old answers
    session.join(id, "customer");
    setStep("call");
  };

  const hangUp = () => {
    speech.cancel();
    voice.stop();
    if (state.messages.some((m) => m.speaker === "advisor")) setRating(true);
    else session.end();
  };

  // ------------------------------------------------------------------ setup
  if (step === "setup") {
    const problems: any[] = options.data?.problems ?? [];
    return (
      <div className="mx-auto flex min-h-[100dvh] max-w-md flex-col px-5 pb-8 pt-10">
        <div className="flex items-center gap-3">
          <LogoMark size={40} />
          <div>
            <div className="font-display text-xl font-bold text-ink">CallVerse</div>
            <div className="text-xs text-muted">Customer line · talk to our advisor</div>
          </div>
        </div>
        <h1 className="mt-10 font-display text-3xl font-semibold text-ink">Call us from your phone</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink2">
          Speak normally: our AI advisor listens, checks your order and answers out loud. An advisor on our desk can join the call.
        </p>
        {resume && (
          <button className="btn btn-ghost mt-6 w-full py-3" onClick={() => reconnect(resume.id)}>
            <RefreshCw size={16} /> Resume your call ({resume.name})
          </button>
        )}
        <div className="mt-8 space-y-4">
          {!useExisting ? (
            <>
              <label className="block">
                <span className="label">Your name</span>
                <input className="field py-3 text-base" placeholder="e.g. Amira" value={name} maxLength={40} onChange={(e) => setName(e.target.value)} />
              </label>
              <label className="block">
                <span className="label">What is it about?</span>
                <select className="field py-3 text-base" value={intent} onChange={(e) => setIntent(e.target.value)}>
                  {problems.map((p) => (
                    <option key={p.intent} value={p.intent}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
              <p className="text-xs text-muted">A real order in that situation is attached to your call (the twin replays that day).</p>
            </>
          ) : (
            <label className="block">
              <span className="label">Customer id</span>
              <input className="field py-3 font-mono text-base" placeholder="NC000001 or SC003025" value={existing} onChange={(e) => setExisting(e.target.value.toUpperCase())} />
            </label>
          )}
          <button className="text-xs font-medium text-brand" onClick={() => setUseExisting(!useExisting)}>
            {useExisting ? "I am a new customer" : "I already have a customer id"}
          </button>
        </div>
        <div className="mt-auto flex flex-col items-center pt-10">
          <motion.button
            whileTap={{ scale: 0.92 }}
            disabled={calling || (useExisting && !existing.trim()) || (!useExisting && !name.trim())}
            onClick={call}
            className="flex h-20 w-20 items-center justify-center rounded-full text-white shadow-lift disabled:opacity-40"
            style={{ background: "var(--good)" }}
            aria-label="Call"
          >
            <Phone size={32} />
          </motion.button>
          <div className="mt-3 text-sm font-medium text-ink">{calling ? "Calling…" : "Call"}</div>
          {speech.unavailable && <p className="mt-4 text-center text-xs text-bad">{speech.unavailable} You can still type.</p>}
        </div>
      </div>
    );
  }

  // ------------------------------------------------------------------- call
  const advisorSpeaking = voice.speakingRole === "advisor";
  const face: AvatarState = advisorSpeaking ? "speaking" : busy ? "thinking" : speech.listening ? "listening" : "idle";
  const routing = state.routing;
  const orderId: string | undefined = state.ready?.profile?.order_id;
  const status = ended
    ? "Call ended"
    : state.status === "connecting"
      ? "Connecting…"
      : speech.listening
        ? "Listening… pause when you are done"
        : advisorSpeaking
          ? "The advisor is speaking"
          : busy
            ? state.autopilot === false
              ? "An advisor is answering…"
              : "The advisor is checking…"
            : typing
              ? "Type your message"
              : "Tap the microphone to talk";
  const dropped = state.status === "done" && !state.ended && !!state.ready?.session_id;

  return (
    <div className="mx-auto flex h-[100dvh] max-w-md flex-col">
      {/* Who you talk to, the timer, the desk the Workforce agent chose */}
      <div className="flex flex-col items-center border-b border-line px-5 pb-4 pt-6">
        <TalkingAvatar kind="agent" state={face} word={voice.word} lipSync={voice.lipSync} size={96} label="CallVerse advisor" />
        <div className="mt-2 font-semibold text-ink">CallVerse advisor</div>
        <div className="text-xs text-muted">
          {routing ? `${routing.assigned_desk} · ${humanize(routing.predicted_intent)}` : "Customer line"}
          {state.autopilot === false && " · a human advisor took the call"}
          {state.startedAt && !ended && ` · ${clock((now - state.startedAt) / 1000)}`}
        </div>
        <div className={clsx("mt-2 text-sm font-medium", speech.listening ? "text-bad" : "text-brand")}>{status}</div>
      </div>

      {/* The conversation */}
      <div ref={scroller} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {state.messages.map((m, i) => (
          <ChatBubble key={i} message={m} mine={m.speaker === "customer"} name={state.ready?.name} showMeta={false} speaking={voice.speaking === String(i)} />
        ))}
        <AnimatePresence>
          {state.streaming?.kind === "reply" && <StreamingBubble key="s" text={state.streaming.text} />}
        </AnimatePresence>
        {speech.listening && speech.interim && (
          <div className="ml-auto max-w-[80%] rounded-2xl rounded-br-md bg-raised px-4 py-2.5 text-[14.5px] italic text-ink2">{speech.interim}…</div>
        )}
        {state.review && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="card p-4 text-center">
            <Sparkles className="mx-auto text-brand" size={18} />
            <div className="mt-1 font-semibold text-ink">Thank you for calling</div>
            <div className="text-sm text-ink2">
              Our quality agent rated this call <b className="text-ink">{Number(state.review.scorecard?.overall ?? 0).toFixed(1)} / 5</b>
            </div>
          </motion.div>
        )}
      </div>

      {/* Quick replies: an order number is hard to say out loud */}
      {running && (
        <div className="flex gap-2 overflow-x-auto px-4 pb-2">
          {orderId && (
            <button className="chip shrink-0" disabled={busy} onClick={() => send(`My order number is ${orderId}`)}>
              <Hash size={12} /> Send my order number
            </button>
          )}
          <button className="chip shrink-0" disabled={busy} onClick={() => send("Can I speak to a supervisor?")}>
            Supervisor, please
          </button>
        </div>
      )}
      {typing && running && (
        <div className="flex gap-2 px-4 pb-2">
          <input className="field" placeholder="Type your message…" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send(text)} />
          <button className="btn btn-primary px-3" disabled={busy || !text.trim()} onClick={() => send(text)} aria-label="Send">
            <SendHorizonal size={16} />
          </button>
        </div>
      )}

      {/* Keyboard, microphone, hang up */}
      <div className="flex items-center justify-around border-t border-line px-6 pb-8 pt-4">
        {ended || dropped ? (
          <>
            {dropped && (
              <button className="btn btn-ghost" onClick={() => reconnect(state.ready!.session_id!)}>
                <RefreshCw size={16} /> Reconnect
              </button>
            )}
            <button
              className="btn btn-primary"
              onClick={() => {
                session.reset();
                setStep("setup");
              }}
            >
              <Phone size={16} /> New call
            </button>
          </>
        ) : (
          <>
            <button className={clsx("btn btn-icon h-12 w-12 rounded-full", typing ? "btn-primary" : "btn-ghost")} onClick={() => setTyping(!typing)} aria-label="Keyboard">
              <Keyboard size={20} />
            </button>
            <motion.button
              whileTap={{ scale: 0.92 }}
              onClick={speech.toggle}
              disabled={!!speech.unavailable || !running}
              className={clsx("flex h-20 w-20 items-center justify-center rounded-full text-white shadow-lift disabled:opacity-40", speech.listening && "animate-pulse-ring")}
              style={{ background: speech.listening ? "var(--critical)" : "var(--brand)", ["--ring-color" as any]: "var(--critical)" }}
              aria-label={speech.listening ? "Stop listening" : "Talk"}
            >
              {speech.unavailable ? <MicOff size={30} /> : <Mic size={30} />}
            </motion.button>
            <button className="flex h-12 w-12 items-center justify-center rounded-full text-white" style={{ background: "var(--critical)" }} onClick={hangUp} aria-label="Hang up">
              <PhoneOff size={20} />
            </button>
          </>
        )}
      </div>

      <CsatDialog
        open={rating}
        onClose={() => setRating(false)}
        onSubmit={(csat) => {
          setRating(false);
          session.end(csat);
        }}
      />
    </div>
  );
}
