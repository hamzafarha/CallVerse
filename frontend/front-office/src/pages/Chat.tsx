import {
  ActivityRow,
  LiveTrace,
  AdvisorAvatar,
  AgentPipeline,
  AnimatePresence,
  CallPanel,
  ChatBubble,
  QualityScore,
  type AvatarState,
  Segmented,
  StreamingBubble,
  ToolBox,
  VoiceControls,
  modelName,
  motion,
  stageLabel,
  useApi,
  useAutoSpeak,
  useLiveSession,
  useVoice,
} from "@callverse/shared";
import { Cpu, Eye, EyeOff, RefreshCw, SendHorizonal, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { CsatDialog } from "../components/CsatDialog";
import { useCustomer } from "../customer";

type Engine = "auto" | "template";

export default function ChatPage() {
  const { contactId } = useParams();
  const { customer } = useCustomer();
  const id = contactId ?? customer?.contact_id;
  if (!id) return <Navigate to="/account" replace />;
  return <Chat contactId={id} />;
}

function Chat({ contactId }: { contactId: string }) {
  const profile = useApi<any>(`/api/portal/customers/${contactId}`);
  const session = useLiveSession();
  const { state } = session;
  const [engine, setEngine] = useState<Engine>("auto");
  const [variant, setVariant] = useState<"rag_policy" | "rag" | "agentic">("agentic");
  const [text, setText] = useState("");
  const [showTrace, setShowTrace] = useState(true);
  const [rating, setRating] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  // Voice mode: you are the customer, so only the Advisor agent's replies are read aloud
  const voice = useVoice();
  useAutoSpeak(state.messages, voice, (m) => (m.speaker === "advisor" && m.meta?.mode !== "human" ? { role: "advisor" } : null));

  useEffect(() => {
    session.start({ contact_id: contactId, customer: "human", advisor: "agent", mode: engine, variant });
    return () => session.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contactId, engine, variant]);

  useEffect(() => {
    if (state.ready) {
      toast.success(
        state.ready.llm
          ? `AI advisor online · ${modelName(state.ready.model)}${state.ready.provider === "openrouter" ? " via OpenRouter" : ""}`
          : "Advisor online · offline backups (approved templates)",
        { id: "ready" },
      );
    }
  }, [state.ready]);
  useEffect(() => {
    if (state.error) toast.error(state.error);
  }, [state.error]);
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [state.messages.length, state.streaming?.text, state.activeAgent, state.review]);

  const data = profile.data;
  const first = data?.name?.split(" ")[0] ?? "there";
  const ended = state.status === "done";
  const busy = session.busy;
  // Call band faces: the Advisor agent thinks while it works; you are "typing" while you write
  const advisorFace: AvatarState = voice.speakingRole === "advisor" ? "speaking" : busy ? "thinking" : "listening";
  const customerFace: AvatarState = text.trim() ? "typing" : voice.speakingRole === "advisor" ? "listening" : "idle";
  const canSend = !busy && !ended && state.status === "running" && text.trim().length > 0;
  const send = (message: string) => {
    if (!message.trim() || busy || ended) return;
    voice.stop(); // like on a call: talking over the advisor interrupts it
    session.sendCustomer(message.trim());
    setText("");
  };
  const currentStage = state.stages[state.stages.length - 1];
  const suggestions = data
    ? [
        state.messages.length === 0 ? data.opening_message : null,
        `My order number is ${data.order.order_id}`,
        "Can I speak to a supervisor?",
        "Thanks, that's all.",
      ].filter(Boolean)
    : [];

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <div className="card flex h-[calc(100vh-180px)] min-h-[560px] min-w-0 flex-col overflow-hidden p-0">
        {/* header */}
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3.5">
          <AdvisorAvatar size={40} />
          <div className="mr-auto">
            <div className="font-semibold text-ink">CallVerse assistant</div>
            <div className="flex items-center gap-1.5 text-xs text-muted">
              {state.status === "running" || ended ? <span className="live-dot" /> : <span className="h-2 w-2 rounded-full bg-[var(--warning)]" />}
              {state.ready
                ? state.ready.llm
                  ? `AI · ${modelName(state.ready.model)} ${state.ready.provider === "openrouter" ? "via OpenRouter" : "on GPU"}`
                  : "offline backups · approved templates"
                : "connecting…"}
            </div>
          </div>
          <VoiceControls voice={voice} roles={["advisor"]} />
          <Segmented
            id="engine"
            size="sm"
            value={engine}
            onChange={setEngine}
            options={[
              { value: "auto", label: <><Cpu size={12} /> Local LLM</> },
              { value: "template", label: "Offline" },
            ]}
          />
          <button className="btn btn-ghost btn-icon hidden lg:inline-flex" title="Behind the scenes" onClick={() => setShowTrace(!showTrace)}>
            {showTrace ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
        </div>
        <AnimatePresence initial={false}>
          {voice.enabled && (
            <CallPanel
              key="call"
              voice={voice}
              startedAt={state.startedAt}
              left={{ kind: "agent", name: "CallVerse assistant", subtitle: "Advisor agent", state: advisorFace }}
              right={{ kind: "person", name: data?.name ?? "You", subtitle: "you · the customer", state: customerFace }}
            />
          )}
        </AnimatePresence>

        {/* messages */}
        <div ref={scroller} className="scroll-fade flex-1 space-y-5 overflow-y-auto bg-raised/40 px-4 py-6 sm:px-6">
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mx-auto max-w-md text-center text-xs text-muted">
            Chat about order <span className="font-mono">#{data?.order?.order_id?.slice(0, 10)}…</span> · the twin replays the
            day you contacted us. Every chat is reviewed by our quality agent.
          </motion.div>
          <ChatBubble
            mine={false}
            showMeta={false}
            message={{ speaker: "advisor", text: `Hi ${first}! I'm the CallVerse assistant. How can I help you today?` }}
          />
          {state.messages.map((m, i) => (
            <ChatBubble
              key={i}
              message={m}
              mine={m.speaker === "customer"}
              name={data?.name}
              animate={m.speaker === "advisor" && m.meta?.mode !== "llm" && i === state.messages.length - 1}
              speaking={voice.speaking === String(i)}
              onListen={m.speaker === "advisor" && voice.supported ? () => voice.replay(String(i), m.text, "advisor") : undefined}
            />
          ))}
          <AnimatePresence>
            {state.streaming && state.streaming.kind === "reply" && (
              <StreamingBubble key="stream" text={state.streaming.text} label={stageLabel(currentStage)} />
            )}
          </AnimatePresence>
          <AnimatePresence>
            {busy && !state.streaming && <ActivityRow key="activity" text={stageLabel(currentStage) || "Connecting…"} who={state.activeAgent === "quality" ? "system" : "advisor"} />}
          </AnimatePresence>
          {state.review && (
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="card mx-auto max-w-md p-5">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
                <Sparkles size={16} className="text-brand" /> Chat closed · quality review
              </div>
              <QualityScore review={state.review} compact />
              <button className="btn btn-primary mt-4 w-full" onClick={() => session.start({ contact_id: contactId, customer: "human", advisor: "agent", mode: engine, variant })}>
                <RefreshCw size={15} /> Start a new chat
              </button>
            </motion.div>
          )}
        </div>

        {/* composer */}
        {!ended && (
          <div className="border-t border-line bg-surface p-3 sm:p-4">
            <div className="mb-2.5 flex gap-2 overflow-x-auto pb-1">
              {suggestions.map((s) => (
                <button key={s} disabled={busy} onClick={() => send(String(s))} className="chip shrink-0 transition-colors hover:border-brand hover:text-brand disabled:opacity-50">
                  {String(s).length > 60 ? `${String(s).slice(0, 58)}…` : s}
                </button>
              ))}
            </div>
            <div className="flex items-end gap-2">
              <textarea
                rows={1}
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    if (canSend) send(text);
                  }
                }}
                placeholder={busy ? "The advisor is answering…" : "Write your message…"}
                className="field max-h-32 min-h-[46px] resize-none py-3"
              />
              <motion.button whileTap={{ scale: 0.92 }} className="btn btn-primary h-[46px] px-4" disabled={!canSend} onClick={() => send(text)} aria-label="Send">
                <SendHorizonal size={17} />
              </motion.button>
              <button className="btn btn-ghost h-[46px]" disabled={busy || !state.messages.length} onClick={() => setRating(true)}>
                <X size={15} /> End chat
              </button>
            </div>
          </div>
        )}
      </div>

      {/* behind the scenes */}
      <AnimatePresence>
        {showTrace && (
          <motion.aside initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }} className="space-y-4">
            <div className="card p-5">
              <div className="mb-1 flex items-center justify-between">
                <div className="text-sm font-semibold text-ink">Behind the scenes</div>
                <Segmented
                  id="variant"
                  size="sm"
                  value={variant}
                  onChange={setVariant}
                  options={[
                    { value: "rag_policy", label: "Hybrid" },
                    { value: "rag", label: "Pure RAG" },
                    { value: "agentic", label: "Agentic" },
                  ]}
                />
              </div>
              <p className="mb-4 text-xs text-muted">
                {variant === "rag_policy"
                  ? "Rules engine decides, LLM writes (production)."
                  : variant === "agentic"
                    ? "The LLM picks its tools; the rules engine still decides; every draft is fact-checked."
                    : "The LLM decides alone with tools (ablation)."}
              </p>
              <div className="mb-5">
                <AgentPipeline active={state.activeAgent} visited={state.visited} stages={state.stages} done={!!state.review} humanCustomer vertical />
              </div>
              <div className="mb-5">
                <ToolBox stages={state.stages} variant={variant} offline={state.ready ? !state.ready.llm : engine === "template"} />
              </div>
              <LiveTrace state={state} />
            </div>
            {state.review && (
              <div className="card p-5">
                <div className="mb-3 text-sm font-semibold text-ink">Conversation KPIs</div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  {[
                    ["First-contact resolution", state.review.kpis?.fcr],
                    ["Policy-correct action", state.review.kpis?.correct],
                    ["Compliant", state.review.kpis?.compliant],
                    ["Intent predicted", state.review.kpis?.intent_correct],
                  ].map(([label, ok]) => (
                    <div key={String(label)} className="rounded-xl bg-raised p-2.5">
                      <div className="text-muted">{label}</div>
                      <div className={ok ? "font-semibold text-good" : ok === false ? "font-semibold text-bad" : "text-muted"}>{ok === null || ok === undefined ? "n/a" : ok ? "yes" : "no"}</div>
                    </div>
                  ))}
                </div>
                <button className="btn btn-ghost mt-3 w-full text-xs" onClick={() => navigate("/")}>
                  Back to the help centre
                </button>
              </div>
            )}
          </motion.aside>
        )}
      </AnimatePresence>

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
