import {
  ActivityRow,
  LiveTrace,
  AgentPipeline,
  AnimatePresence,
  Avatar,
  CallPanel,
  ChatBubble,
  type AvatarState,
  EmptyState,
  GROUP_COLOR,
  GROUP_LABEL,
  ORDER_STATUS,
  PERSONA_COLOR,
  QualityScore,
  Segmented,
  StreamingBubble,
  ToolBox,
  VoiceControls,
  clock,
  clsx,
  dateLabel,
  humanize,
  motion,
  num,
  stageLabel,
  useApi,
  useAutoSpeak,
  useLiveSession,
  useVoice,
} from "@callverse/shared";
import { Bot, CheckCheck, Clock, Headset, Inbox, Pencil, RefreshCw, SendHorizonal, Sparkles, User, Wand2, Wrench } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { OrderTimeline } from "../components/OrderTimeline";

type Tab = "tools" | "customer" | "copilot" | "quality";
type Variant = "rag_policy" | "rag" | "agentic";

export default function DeskPage() {
  const [seed, setSeed] = useState(0);
  const queue = useApi<any[]>(`/api/desk/queue?n=10&seed=${seed}`);
  const [loadedAt, setLoadedAt] = useState(Date.now());
  const [now, setNow] = useState(Date.now());
  const [selected, setSelected] = useState<any | null>(null);
  const [handled, setHandled] = useState<{ id: string; overall: number; seconds: number }[]>([]);
  const [autopilot, setAutopilot] = useState(false);
  const [engine, setEngine] = useState<"auto" | "template">("auto");
  const [variant, setVariant] = useState<Variant>("agentic");
  const [chatVariant, setChatVariant] = useState<Variant>("agentic"); // the mode of the chat in progress
  const [tab, setTab] = useState<Tab>("tools");
  const [text, setText] = useState("");
  const session = useLiveSession();
  const { state } = session;
  const scroller = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const details = useApi<any>(selected ? `/api/portal/customers/${selected.contact_id}` : null);
  // Voice mode: the agents speak (the Client agent, and the Advisor agent on autopilot),
  // each with its own voice; what you type yourself is never read back.
  const voice = useVoice();
  useAutoSpeak(state.messages, voice, (m) =>
    m.meta?.mode === "human" ? null : m.speaker === "advisor" ? { role: "advisor" } : { role: "customer", persona: selected?.persona },
  );

  useEffect(() => setLoadedAt(Date.now()), [queue.data]);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [state.messages.length, state.streaming?.text, state.suggestion]);
  // The reply box starts on one line and grows with the text (up to max-h-32)
  useEffect(() => {
    const box = composer.current;
    if (!box) return;
    box.style.height = "auto";
    box.style.height = `${box.scrollHeight + 2}px`;
  }, [text]);
  useEffect(() => {
    if (state.review && selected) {
      const seconds = state.startedAt ? (Date.now() - state.startedAt) / 1000 : 0;
      setHandled((h) => (h.some((x) => x.id === selected.contact_id) ? h : [...h, { id: selected.contact_id, overall: state.review!.scorecard.overall, seconds }]));
      setTab("quality");
      toast.success(`Chat wrapped up · quality ${Number(state.review.scorecard.overall).toFixed(1)}/5`);
    }
  }, [state.review, selected, state.startedAt]);
  useEffect(() => {
    if (state.error) toast.error(state.error);
  }, [state.error]);

  const waiting = useMemo(
    () => (queue.data ?? []).filter((q) => !handled.some((h) => h.id === q.contact_id) && q.contact_id !== selected?.contact_id),
    [queue.data, handled, selected],
  );
  const elapsed = (q: any) => q.waiting_seconds + (now - loadedAt) / 1000;
  const longest = waiting.length ? Math.max(...waiting.map(elapsed)) : 0;
  const accept = (item: any) => {
    voice.stop();
    setSelected(item);
    setTab("tools");
    setText("");
    setChatVariant(variant);
    session.start({
      contact_id: item.contact_id,
      customer: "agent",
      advisor: autopilot ? "agent" : "human",
      mode: engine,
      variant,
      waited_seconds: Math.round(elapsed(item)), // the Client agent's chat timer starts from here
    });
  };
  const sendAdvisor = (message: string) => {
    if (!message.trim()) return;
    voice.stop(); // like on a call: answering interrupts the customer
    session.sendAdvisor(message.trim());
    setText("");
  };
  const toggleAutopilot = (on: boolean) => {
    setAutopilot(on);
    if (state.status === "running") session.autopilot(on);
  };
  const ended = state.status === "done";
  const stage = state.stages[state.stages.length - 1];
  // Call band faces: the advisor side is the Advisor agent on autopilot, otherwise you
  const advisorWorking = session.busy && state.activeAgent === "advisor";
  const advisorFace: AvatarState =
    voice.speakingRole === "advisor" ? "speaking" : advisorWorking ? "thinking" : !autopilot && text.trim() ? "typing" : "listening";
  const customerFace: AvatarState =
    voice.speakingRole === "customer" ? "speaking" : session.busy && state.activeAgent === "client" ? "typing" : "listening";
  const avgQuality = handled.length ? handled.reduce((s, h) => s + h.overall, 0) / handled.length : null;
  const avgHandle = handled.length ? handled.reduce((s, h) => s + h.seconds, 0) / handled.length : null;

  return (
    <div className="flex h-[calc(100vh-64px)] flex-col">
      {/* stats strip */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-line bg-surface/70 px-4 py-2.5 text-xs backdrop-blur sm:px-6">
        <span className="inline-flex items-center gap-2 font-semibold text-ink">
          <Headset size={15} className="text-brand" /> Advisor desk
        </span>
        <Metric label="Waiting" value={String(waiting.length)} />
        <Metric label="Longest wait" value={clock(longest)} alert={longest > 180} />
        <Metric label="Handled" value={String(handled.length)} />
        <Metric label="Avg quality" value={avgQuality ? `${avgQuality.toFixed(1)}/5` : "–"} />
        <Metric label="Avg handle time" value={avgHandle ? clock(avgHandle) : "–"} />
        <div className="ml-auto flex items-center gap-2">
          <Segmented
            id="desk-variant"
            size="sm"
            value={variant}
            onChange={setVariant}
            options={[
              { value: "rag_policy", label: "Hybrid" },
              { value: "rag", label: "Pure RAG" },
              { value: "agentic", label: "Agentic" },
            ]}
          />
          <Segmented id="desk-engine" size="sm" value={engine} onChange={setEngine} options={[{ value: "auto", label: "Local LLM" }, { value: "template", label: "Offline" }]} />
          <button className="btn btn-ghost py-1 text-xs" onClick={() => setSeed((s) => s + 1)}>
            <RefreshCw size={13} /> New queue
          </button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[300px_1fr_380px]">
        {/* ------------------------------------------------------------ queue */}
        <aside className="hidden min-h-0 flex-col border-r border-line lg:flex">
          <div className="flex items-center justify-between px-4 py-3">
            <div className="text-sm font-semibold text-ink">Queue</div>
            <span className="chip py-0.5 text-[11px]">{waiting.length} waiting</span>
          </div>
          <div className="flex-1 space-y-2 overflow-y-auto px-3 pb-4">
            <AnimatePresence initial={false}>
              {waiting.map((item) => {
                const seconds = elapsed(item);
                return (
                  <motion.button
                    layout
                    key={item.contact_id}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 40, height: 0, marginTop: 0 }}
                    onClick={() => accept(item)}
                    disabled={state.status === "running" && !ended}
                    className="card card-hover group relative w-full overflow-hidden p-3 text-left disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <span className="absolute inset-y-0 left-0 w-1" style={{ background: GROUP_COLOR[item.intent_group] }} />
                    <div className="flex items-center gap-2 pl-1">
                      <Avatar name={item.name} size={28} />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[13px] font-semibold text-ink">{item.name}</div>
                        <div className="truncate text-[11px] text-muted">{GROUP_LABEL[item.intent_group]}</div>
                      </div>
                      <span className={clsx("inline-flex items-center gap-1 font-mono text-[11px] tabular", seconds > 180 ? "font-bold text-bad" : "text-muted")}>
                        <Clock size={11} /> {clock(seconds)}
                      </span>
                    </div>
                    <p className="mt-2 line-clamp-2 pl-1 text-xs text-ink2">{item.message_text}</p>
                    <div className="mt-2 flex items-center gap-1.5 pl-1 text-[10px]">
                      <span className="rounded-full px-1.5 py-0.5 font-semibold capitalize" style={{ color: PERSONA_COLOR[item.persona], background: `color-mix(in srgb, ${PERSONA_COLOR[item.persona]} 12%, transparent)` }}>
                        {item.persona}
                      </span>
                      {item.is_repeat_contact && <span className="chip py-0 text-[10px]">repeat</span>}
                      <span className="ml-auto font-semibold text-brand opacity-0 transition-opacity group-hover:opacity-100">Accept →</span>
                    </div>
                  </motion.button>
                );
              })}
            </AnimatePresence>
            {!waiting.length && queue.data && <EmptyState title="Queue empty" text="Load a new queue to keep practising." />}
          </div>
        </aside>

        {/* ---------------------------------------------------- conversation */}
        <section className="flex min-h-0 min-w-0 flex-col">
          {!selected ? (
            <div className="flex flex-1 items-center justify-center p-8">
              <div className="max-w-md text-center">
                <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-3xl gradient-brand text-white shadow-glow">
                  <Inbox size={28} />
                </motion.div>
                <h2 className="text-2xl font-semibold text-ink">Pick a customer from the queue</h2>
                <p className="mt-2 text-sm text-ink2">
                  The Client agent plays the customer. You answer, with the Advisor agent as your copilot: it drafts every
                  reply from the policies and the order. Switch on <b>autopilot</b> to let it answer alone.
                </p>
                {queue.data?.[0] && (
                  <button className="btn btn-primary mt-6" onClick={() => accept(waiting[0] ?? queue.data![0])}>
                    Take the longest-waiting customer
                  </button>
                )}
              </div>
            </div>
          ) : (
            <>
              {/* One line: the name block shrinks (truncated) before the controls wrap */}
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line px-4 py-2.5 sm:px-6">
                <Avatar name={selected.name} size={36} />
                <div className="min-w-[150px] flex-1">
                  <div className="truncate font-semibold text-ink">{selected.name}</div>
                  <div className="truncate text-xs text-muted" title="simulated by the Client agent">
                    {humanize(selected.intent)} · <span className="capitalize">{selected.persona}</span> customer · Client agent
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <VoiceControls voice={voice} />
                  <Segmented
                    id="pilot"
                    size="sm"
                    value={autopilot ? "agent" : "human"}
                    onChange={(v) => toggleAutopilot(v === "agent")}
                    options={[
                      { value: "human", label: <><User size={12} /> You answer</> },
                      { value: "agent", label: <><Bot size={12} /> Autopilot</> },
                    ]}
                  />
                  <button className="btn btn-ghost py-1.5 text-xs" disabled={ended || session.busy || !state.messages.some((m) => m.speaker === "advisor")} onClick={() => session.end()}>
                    <CheckCheck size={14} /> Wrap up
                  </button>
                </div>
              </div>
              <AnimatePresence initial={false}>
                {voice.enabled && (
                  <CallPanel
                    key="call"
                    compact
                    voice={voice}
                    startedAt={state.startedAt}
                    left={
                      autopilot
                        ? { kind: "agent", name: "Advisor agent", subtitle: "autopilot", state: advisorFace }
                        : {
                            kind: "person",
                            headset: true,
                            name: "You",
                            subtitle: "advisor · AI copilot",
                            state: advisorFace,
                            note: advisorWorking ? "copilot drafting…" : undefined,
                          }
                    }
                    right={{
                      kind: "person",
                      name: selected.name,
                      subtitle: `${selected.persona} customer · Client agent`,
                      persona: selected.persona,
                      state: customerFace,
                    }}
                  />
                )}
              </AnimatePresence>
              <div className="border-b border-line bg-raised/40 px-4 py-2 sm:px-6">
                <AgentPipeline compact active={state.activeAgent} visited={state.visited} stages={state.stages} done={!!state.review} />
              </div>
              <div ref={scroller} className="scroll-fade min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4 sm:px-6">
                {state.messages.map((m, i) => {
                  const role = m.speaker === "advisor" ? "advisor" : "customer";
                  return (
                    <ChatBubble
                      key={i}
                      message={m}
                      mine={m.speaker === "advisor"}
                      name={selected.name}
                      speaking={voice.speaking === String(i)}
                      onListen={m.meta?.mode !== "human" && voice.supported ? () => voice.replay(String(i), m.text, role, selected.persona) : undefined}
                    />
                  );
                })}
                <AnimatePresence>
                  {state.streaming?.kind === "reply" && <StreamingBubble key="s" mine text={state.streaming.text} label={stageLabel(stage)} />}
                  {session.busy && !state.streaming && <ActivityRow key="a" text={stageLabel(stage)} who={state.activeAgent === "client" ? "customer" : "advisor"} />}
                </AnimatePresence>
              </div>
              {!ended && !autopilot && (
                <div className="border-t border-line bg-surface px-3 py-2.5 sm:px-4">
                  <AnimatePresence>
                    {(state.suggestion || state.streaming?.kind === "draft") && (
                      <motion.div
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: 10 }}
                        className="ring-gradient mb-2.5 rounded-2xl bg-raised px-3 py-2"
                      >
                        {/* Buttons on the title line and a capped text height: the conversation keeps the room */}
                        <div className="mb-1 flex min-h-[28px] items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-brand">
                          <Wand2 size={13} /> Copilot draft
                          {state.suggestion?.meta?.tools?.length ? <span className="font-normal normal-case tracking-normal text-muted">· {state.suggestion.meta.tools.length} tool calls</span> : null}
                          {state.suggestion && (
                            <div className="ml-auto flex gap-1.5 normal-case tracking-normal">
                              <button className="btn btn-primary px-2.5 py-1 text-xs" onClick={() => sendAdvisor(state.suggestion!.text)}>
                                <SendHorizonal size={12} /> Send draft
                              </button>
                              <button className="btn btn-ghost px-2.5 py-1 text-xs" onClick={() => setText(state.suggestion!.text)}>
                                <Pencil size={12} /> Edit first
                              </button>
                            </div>
                          )}
                        </div>
                        <p className={clsx("max-h-[4.5rem] overflow-y-auto pr-1 text-sm leading-snug text-ink", !state.suggestion && "caret")}>
                          {state.suggestion?.text ?? state.streaming?.text}
                        </p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                  <div className="flex items-end gap-2">
                    <textarea
                      ref={composer}
                      rows={1}
                      value={text}
                      onChange={(e) => setText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          if (!session.busy) sendAdvisor(text);
                        }
                      }}
                      placeholder="Type your reply, or use the copilot draft…"
                      className="field max-h-32 min-h-[44px] resize-none"
                    />
                    <button className="btn btn-primary h-11 px-4" disabled={session.busy || !text.trim()} onClick={() => sendAdvisor(text)}>
                      <SendHorizonal size={17} />
                    </button>
                  </div>
                </div>
              )}
              {ended && (
                <div className="border-t border-line bg-surface p-4 text-center text-sm text-ink2">
                  Conversation closed.{" "}
                  {waiting[0] && (
                    <button className="btn btn-primary ml-2 py-1.5 text-xs" onClick={() => accept(waiting[0])}>
                      Next customer
                    </button>
                  )}
                </div>
              )}
            </>
          )}
        </section>

        {/* ---------------------------------------------------- context panel */}
        <aside className="hidden min-h-0 flex-col border-l border-line lg:flex">
          <div className="px-4 py-3">
            <Segmented
              id="desk-tab"
              size="sm"
              value={tab}
              onChange={setTab}
              options={[
                { value: "tools", label: <><Wrench size={12} /> Tools</> },
                { value: "customer", label: "Customer" },
                { value: "copilot", label: <><Sparkles size={12} /> Copilot</> },
                { value: "quality", label: "Quality", disabled: !state.review },
              ]}
            />
          </div>
          <div className="flex-1 overflow-y-auto px-4 pb-6">
            {!selected && <EmptyState title="No customer selected" text="Accept a chat to see the customer's order and history." />}
            {selected && tab === "tools" && (
              <ToolBox stages={state.stages} variant={chatVariant} offline={state.ready ? !state.ready.llm : engine === "template"} customerTools />
            )}
            {selected && tab === "customer" && <Customer360 data={details.data} />}
            {selected && tab === "copilot" && (
              <div className="space-y-4">
                {state.advisor && (
                  <div className="rounded-2xl border border-line p-4">
                    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">Policy state</div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <Field label="Intent" value={humanize(state.advisor.intent)} />
                      <Field label="Order verified" value={state.advisor.order_id ? "yes" : "not yet"} />
                      <Field label="Rules-engine action" value={state.advisor.outcome ? humanize(state.advisor.outcome) : "–"} />
                      <Field label="Hand over to" value={state.advisor.handed_to ? humanize(state.advisor.handed_to) : "nobody"} />
                    </div>
                  </div>
                )}
                {state.suggestion?.meta?.retrieval?.length ? (
                  <div className="rounded-2xl border border-line p-4">
                    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">Policy sources of the draft</div>
                    {state.suggestion.meta.retrieval.map((r: any) => (
                      <div key={r.chunk_id} className="flex items-center justify-between gap-2 py-1 text-xs">
                        <span className="truncate text-ink2">{r.section}</span>
                        <span className="tabular text-muted">{Number(r.score).toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
                <LiveTrace state={state} />
              </div>
            )}
            {selected && tab === "quality" && state.review && (
              <div className="space-y-4">
                <QualityScore review={state.review} />
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <Field label="FCR" value={state.review.kpis?.fcr ? "yes" : "no"} />
                  <Field label="Customer CSAT" value={state.review.kpis?.csat ? `${state.review.kpis.csat}/5` : "–"} />
                  <Field label="Compliant" value={state.review.kpis?.compliant ? "yes" : "no"} />
                  <Field label="Turns" value={num(state.review.kpis?.turns, 0)} />
                </div>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

function Metric({ label, value, alert = false }: { label: string; value: string; alert?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-muted">
      {label}
      <b className={clsx("tabular", alert ? "text-bad" : "text-ink")}>{value}</b>
    </span>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-raised p-2.5">
      <div className="text-muted">{label}</div>
      <div className="mt-0.5 font-medium capitalize text-ink">{value}</div>
    </div>
  );
}

function Customer360({ data }: { data: any }) {
  if (!data) return <div className="skeleton h-80" />;
  const order = data.order;
  const status = ORDER_STATUS[order.status_at_contact] ?? { label: humanize(order.status_at_contact), color: "var(--series-1)" };
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
      <div className="flex items-center gap-3">
        <Avatar name={data.name} size={44} />
        <div>
          <div className="font-semibold text-ink">{data.name}</div>
          <div className="text-xs text-muted">
            {data.city}, {data.state} · {data.tone}
          </div>
        </div>
      </div>
      <div className="rounded-2xl border border-line p-4">
        <div className="mb-3 flex items-center justify-between text-xs">
          <span className="font-mono text-muted">#{order.order_id.slice(0, 12)}…</span>
          <span className="rounded-full px-2 py-0.5 font-semibold" style={{ color: status.color, background: `color-mix(in srgb, ${status.color} 12%, transparent)` }}>
            {status.label}
          </span>
        </div>
        <OrderTimeline steps={data.timeline} compact />
        <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
          <Field label="Category" value={humanize(order.category)} />
          <Field label="Value" value={`R$ ${num(order.value, 2)}`} />
          <Field label="Estimated" value={dateLabel(order.estimated_delivery)} />
          <Field label="Days past estimate" value={order.days_past_estimate > 0 ? String(order.days_past_estimate) : "on time"} />
        </div>
      </div>
      <div className="rounded-2xl border border-line p-4">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">Previous contacts</div>
        {data.previous_contacts.length ? (
          data.previous_contacts.map((c: any) => (
            <div key={c.contact_id} className="border-b border-line py-2 text-xs last:border-0">
              <div className="flex justify-between text-muted">
                <span>{humanize(c.intent)}</span>
                <span>{dateLabel(c.contact_timestamp)}</span>
              </div>
            </div>
          ))
        ) : (
          <div className="text-xs text-muted">None: first contact.</div>
        )}
      </div>
    </motion.div>
  );
}
