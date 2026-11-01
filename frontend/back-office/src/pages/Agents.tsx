import {
  ActivityRow,
  AgentPipeline,
  AnimatePresence,
  Card,
  ChatBubble,
  EmptyState,
  LiveTrace,
  PageHeader,
  Pill,
  QualityScore,
  Segmented,
  Status,
  StreamingBubble,
  clock,
  humanize,
  motion,
  pct,
  stageLabel,
  useApi,
  useLiveSession,
} from "@callverse/shared";
import { Bot, Cpu, Play, RotateCcw, Square, Timer } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export default function AgentsPage() {
  const status = useApi<any>("/api/agents/status");
  const contacts = useApi<any[]>("/api/agents/contacts?n=30");
  const [contactId, setContactId] = useState("");
  const [engine, setEngine] = useState<"auto" | "template">("auto");
  const [variant, setVariant] = useState<"rag_policy" | "rag">("rag_policy");
  const session = useLiveSession();
  const { state } = session;
  const scroller = useRef<HTMLDivElement>(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [state.messages.length, state.streaming?.text]);

  const running = state.status === "running" || state.status === "connecting";
  const start = () =>
    session.start({
      contact_id: contactId || null,
      customer: "agent",
      advisor: "agent",
      mode: engine,
      variant,
      seed: Math.floor(Math.random() * 1000),
    });
  const llm = status.data?.llm_available;
  const profile = state.ready?.profile;
  const stage = state.stages[state.stages.length - 1];
  const elapsed = state.startedAt ? ((state.review ? state.stages[state.stages.length - 1]?.at ?? now : now) - state.startedAt) / 1000 : 0;

  return (
    <div className="space-y-6">
      <PageHeader
        tag="DSO2 · the four agents together"
        color="var(--layer-agents)"
        title="Agent theater"
        subtitle="A real customer contact runs through the twin with no human involved: the Client agent plays the customer, the Workforce agent routes it, the Advisor answers with the knowledge base, the order tools and the rules engine, and the Quality agent grades the result against the policy-correct answer."
      >
        {status.data && (
          <Pill color={llm ? "var(--good-text)" : "var(--warning)"}>
            <Cpu size={12} /> {llm ? "Local Hugging Face LLMs ready" : "Offline backups only"}
          </Pill>
        )}
      </PageHeader>

      <Card>
        <div className="grid gap-4 lg:grid-cols-[2fr_auto_auto_auto] lg:items-end">
          <div>
            <label className="label">Customer contact (from history)</label>
            <select className="field" value={contactId} onChange={(e) => setContactId(e.target.value)}>
              <option value="">Random contact</option>
              {(contacts.data ?? []).map((c: any) => (
                <option key={c.contact_id} value={c.contact_id}>
                  {c.contact_id} · {c.intent} · “{String(c.message_text).slice(0, 60)}”
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Agents</label>
            <Segmented
              id="theater-engine"
              value={engine}
              onChange={setEngine}
              options={[
                { value: "auto", label: <><Cpu size={13} /> Local LLMs</>, disabled: status.data && !llm },
                { value: "template", label: "Offline backups" },
              ]}
            />
          </div>
          <div>
            <label className="label">Advisor variant</label>
            <Segmented
              id="theater-variant"
              value={variant}
              onChange={setVariant}
              options={[
                { value: "rag_policy", label: "Hybrid (prod.)" },
                { value: "rag", label: "Pure RAG" },
              ]}
            />
          </div>
          <div className="flex gap-2">
            {running ? (
              <button className="btn btn-ghost" onClick={session.reset}>
                <Square size={15} /> Stop
              </button>
            ) : (
              <button className="btn btn-primary" onClick={start}>
                {state.status === "done" ? <RotateCcw size={16} /> : <Play size={16} />} {state.status === "done" ? "Run again" : "Start conversation"}
              </button>
            )}
          </div>
        </div>
        {status.data?.llm && (
          <div className="mt-4 flex flex-wrap gap-2 text-xs">
            {Object.entries(status.data.llm.roles).map(([role, m]: any) => (
              <Pill key={role}>
                {role}: {String(m.pinned).split("/").pop()} · {m.family}
              </Pill>
            ))}
            <Pill>retriever: {status.data.retriever}</Pill>
          </div>
        )}
      </Card>

      <Card
        title="LangGraph flow"
        subtitle="client_open → workforce_route → advisor ⇄ client_reply → quality → kpi. The advisor ⇄ client loop repeats until the customer leaves."
        action={
          state.startedAt ? (
            <span className="chip font-mono">
              <Timer size={12} /> {clock(elapsed)}
            </span>
          ) : null
        }
      >
        <AgentPipeline active={state.activeAgent} visited={state.visited} stages={state.stages} done={!!state.review} />
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <Card
          title="Conversation"
          subtitle={profile ? `${profile.contact_id} · true intent ${humanize(profile.intent)} · ${profile.persona} customer` : "Start a conversation to watch the agents"}
          bodyClassName="max-h-[640px] overflow-y-auto pr-1"
        >
          <div ref={scroller} className="space-y-5">
            {!state.messages.length && !running && <EmptyState title="Nothing running" text="Pick a contact and start: every step appears as the agent works." icon={<Bot size={20} />} />}
            {state.messages.map((m, i) => (
              <ChatBubble key={i} message={m} mine={m.speaker === "advisor"} name={`Customer ${profile?.contact_id ?? ""}`} />
            ))}
            <AnimatePresence>
              {state.streaming?.kind === "reply" && <StreamingBubble key="s" mine text={state.streaming.text} label={stageLabel(stage)} />}
              {session.busy && !state.streaming && <ActivityRow key="a" text={stageLabel(stage) || "Starting the agents"} who={state.activeAgent === "client" ? "customer" : "advisor"} />}
            </AnimatePresence>
          </div>
        </Card>
        <div className="space-y-6">
          <Card title="What each agent did" subtitle="Live trace of the run">
            <LiveTrace state={state} />
          </Card>
          <AnimatePresence>
            {state.review && (
              <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
                <Card title="Quality agent scorecard">
                  <QualityScore review={state.review} />
                  <div className="mt-4 flex flex-wrap gap-3 border-t border-line pt-4">
                    <Status ok={state.review.kpis?.fcr} label="first-contact resolution" />
                    <Status ok={state.review.kpis?.correct} label="policy-correct action" />
                    <Status ok={state.review.kpis?.compliant} label="compliant" />
                    <Status ok={state.review.kpis?.intent_correct} label="intent predicted" />
                  </div>
                  <div className="mt-3 text-xs text-ink2">
                    Customer CSAT <b className="text-ink">{state.review.kpis?.csat ?? "–"}/5</b> · tools OK {pct(state.review.kpis?.tool_success_rate, 0)} · {state.review.kpis?.turns} messages
                  </div>
                </Card>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
