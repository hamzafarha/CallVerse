import { Bot, Headset, Play, ShieldCheck, User, Wrench } from "lucide-react";
import { useRef, useState } from "react";
import { Card, ErrorBox, Loading, PageHeader, Pill, Status } from "../components/ui";
import { useApi, wsUrl } from "../lib/api";
import { num, pct } from "../lib/format";

const NODES = [
  { id: "client_open", label: "Client agent", sub: "opens the chat", icon: User },
  { id: "workforce_route", label: "Workforce agent", sub: "predicts + routes", icon: Headset },
  { id: "advisor", label: "Advisor agent", sub: "RAG + tools", icon: Bot },
  { id: "client_reply", label: "Client agent", sub: "replies / leaves", icon: User },
  { id: "quality", label: "Quality agent", sub: "LLM judge", icon: ShieldCheck },
  { id: "kpi", label: "KPI engine", sub: "BO2 indicators", icon: Wrench },
];

export default function AgentsPage() {
  const status = useApi<any>("/api/agents/status");
  const contacts = useApi<any[]>("/api/agents/contacts?n=30");
  const [contactId, setContactId] = useState<string>("");
  const [mode, setMode] = useState("template");
  const [variant, setVariant] = useState("rag_policy");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<any>(null);
  const [state, setState] = useState<any>({});
  const [active, setActive] = useState<string | null>(null);
  const [visited, setVisited] = useState<string[]>([]);
  const socket = useRef<WebSocket | null>(null);

  const start = () => {
    setRunning(true); setError(null); setState({}); setVisited([]); setProfile(null); setActive("client_open");
    const ws = new WebSocket(wsUrl("/ws/conversation"));
    socket.current = ws;
    ws.onopen = () => ws.send(JSON.stringify({ contact_id: contactId || null, mode, variant, seed: Math.floor(Math.random() * 1000) }));
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.type === "profile") setProfile(message.profile);
      if (message.type === "update") {
        setState((s: any) => ({ ...s, ...message.update }));
        setVisited((v) => [...v, message.node]);
        const next: Record<string, string> = { client_open: "workforce_route", workforce_route: "advisor", advisor: "client_reply", client_reply: "advisor", quality: "kpi", kpi: "" };
        setActive(message.node === "client_reply" && message.update.ended ? "quality" : next[message.node] || null);
      }
      if (message.type === "error") { setError(message.message); setRunning(false); setActive(null); }
      if (message.type === "done") { setRunning(false); setActive(null); }
    };
    ws.onerror = () => { setError("WebSocket error: is `callverse serve` running?"); setRunning(false); };
  };

  const messages = state.messages ?? [];
  const llm = status.data?.llm_available;
  return (
    <div className="space-y-6">
      <PageHeader
        tag="DSO2 · the four agents"
        color="var(--layer-agents)"
        title="Watch the agents work together"
        subtitle="A LangGraph state machine runs one real customer contact through the twin: the Client agent plays the customer, the Workforce agent routes it, the Advisor answers with the knowledge base and the order tools, and the Quality agent grades the conversation against the policy-correct answer."
      />
      <Card title="Run a conversation">
        <div className="grid gap-4 md:grid-cols-4">
          <div className="md:col-span-2">
            <label className="label">Customer contact (from history)</label>
            <select className="field" value={contactId} onChange={(e) => setContactId(e.target.value)}>
              <option value="">Random contact</option>
              {(contacts.data ?? []).map((c: any) => (
                <option key={c.contact_id} value={c.contact_id}>{c.contact_id} · {c.intent} · “{String(c.message_text).slice(0, 60)}”</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Agents</label>
            <select className="field" value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="template">Offline backups (instant)</option>
              <option value="llm" disabled={!llm}>Local LLMs via Ollama{llm ? "" : " (offline)"}</option>
            </select>
          </div>
          <div>
            <label className="label">Advisor variant (LLM)</label>
            <select className="field" value={variant} onChange={(e) => setVariant(e.target.value)} disabled={mode !== "llm"}>
              <option value="rag_policy">RAG + tools + rules engine</option>
              <option value="rag">Pure agentic RAG (ablation)</option>
            </select>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button className="btn btn-primary" onClick={start} disabled={running}><Play size={16} /> {running ? "Running…" : "Start conversation"}</button>
          {status.data && (
            <>
              <Status ok={llm} label={llm ? "Ollama reachable" : "Ollama offline"} />
              {Object.entries(status.data.pinned_models ?? {}).map(([r, m]) => <Pill key={r}>{r}: {String(m)}</Pill>)}
              <Pill>{status.data.retriever}</Pill>
            </>
          )}
        </div>
        {mode === "llm" && <p className="mt-2 text-xs text-muted">LLM conversations take 1-2 minutes on a laptop GPU; each step appears as soon as the agent finishes.</p>}
      </Card>

      <Card title="LangGraph flow">
        <div className="flex flex-wrap items-center gap-2">
          {NODES.map((node, index) => {
            const done = visited.includes(node.id);
            const isActive = active === node.id;
            const Icon = node.icon;
            return (
              <div key={node.id + index} className="flex items-center gap-2">
                <div className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-xs transition ${isActive ? "animate-pulse" : ""}`}
                  style={{ borderColor: isActive ? "var(--brand)" : done ? "var(--good)" : "var(--hairline)", background: isActive ? "var(--surface-2)" : undefined }}>
                  <Icon size={15} style={{ color: done || isActive ? "var(--brand)" : "var(--text-muted)" }} />
                  <div><div className="font-semibold text-ink">{node.label}</div><div className="text-muted">{node.sub}</div></div>
                </div>
                {index < NODES.length - 1 && <span className="text-muted">→</span>}
              </div>
            );
          })}
        </div>
        <p className="mt-2 text-xs text-muted">The advisor ⇄ client loop repeats until the customer leaves (max 4 customer turns).</p>
      </Card>

      {error && <ErrorBox error={error} />}
      {running && !messages.length && <Loading text="Starting the agents" />}

      {(profile || messages.length > 0) && (
        <div className="grid gap-6 lg:grid-cols-5">
          <Card title="Conversation" className="lg:col-span-3"
            subtitle={profile ? `${profile.contact_id} · ${profile.intent} · ${profile.persona} customer · order ${profile.order_id.slice(0, 8)}…` : undefined}>
            <div className="space-y-3">
              {messages.map((m: any, i: number) => (
                <div key={i} className={`flex ${m.speaker === "customer" ? "justify-start" : "justify-end"}`}>
                  <div className="max-w-[85%] rounded-2xl px-4 py-2.5 text-sm"
                    style={{ background: m.speaker === "customer" ? "var(--surface-2)" : "var(--brand)", color: m.speaker === "customer" ? "var(--text-primary)" : "white", border: m.speaker === "customer" ? "1px solid var(--hairline)" : undefined }}>
                    <div className="mb-0.5 text-[10px] uppercase tracking-wide opacity-70">{m.speaker === "customer" ? "Customer (client agent)" : `Advisor · ${m.meta?.mode}`}</div>
                    <div className="whitespace-pre-wrap">{m.text}</div>
                    {m.meta?.tools?.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {m.meta.tools.map((t: any, j: number) => (
                          <span key={j} className="rounded bg-black/15 px-1.5 py-0.5 font-mono text-[10px]">{t.ok ? "✓" : "✗"} {t.name}</span>
                        ))}
                      </div>
                    )}
                    {m.meta?.sources?.length > 0 && <div className="mt-1 text-[10px] opacity-80">sources: {m.meta.sources.join(", ")}</div>}
                  </div>
                </div>
              ))}
              {running && <Loading text={active ? `Waiting for ${active.replace("_", " ")}` : "Working"} />}
            </div>
          </Card>
          <div className="space-y-6 lg:col-span-2">
            {state.routing && (
              <Card title="Workforce agent decision">
                <dl className="grid grid-cols-2 gap-2 text-sm">
                  <dt className="text-muted">Predicted problem</dt><dd className="text-ink">{state.routing.predicted_intent} ({pct(state.routing.confidence, 0)})</dd>
                  <dt className="text-muted">Routed to</dt><dd className="text-ink">{state.routing.assigned_desk} ({state.routing.desk_specialty} specialist)</dd>
                  <dt className="text-muted">Speed on this problem</dt><dd className="text-ink">×{state.routing.desk_speed_on_problem}</dd>
                  <dt className="text-muted">Expected wait</dt><dd className="text-ink">{state.routing.is_live ? `${num(state.routing.expected_wait_seconds, 1)} s` : "closed: overnight backlog"}</dd>
                  <dt className="text-muted">Agents on duty</dt><dd className="text-ink">{state.routing.agents_on_duty} (≈{num(state.routing.arrivals_per_hour, 0)} chats/h)</dd>
                </dl>
              </Card>
            )}
            {state.scorecard && (
              <Card title={`Quality scorecard (${state.scorecard.judge})`} subtitle={state.scorecard.model ?? "rule-based checklist"}>
                {Object.entries(state.scorecard.scores).map(([k, v]: any) => (
                  <div key={k} className="mb-2">
                    <div className="flex justify-between text-xs"><span className="capitalize text-ink2">{k}</span><span className="tabular font-semibold text-ink">{v}/5</span></div>
                    <div className="mt-1 h-1.5 rounded-full bg-raised"><div className="h-1.5 rounded-full" style={{ width: `${(v / 5) * 100}%`, background: "var(--series-1)" }} /></div>
                  </div>
                ))}
                <p className="mt-2 text-xs text-ink2">{state.scorecard.rationale}</p>
                {state.reference && <p className="mt-2 text-xs text-muted">Policy reference: <b>{state.reference.outcome}</b></p>}
              </Card>
            )}
            {state.kpis && (
              <Card title="Conversation KPIs (BO2)">
                <div className="flex flex-wrap gap-3">
                  <Status ok={state.kpis.fcr} label="first-contact resolution" />
                  <Status ok={state.kpis.correct} label="policy-correct action" />
                  <Status ok={state.kpis.compliant} label="compliant" />
                  <Status ok={state.kpis.intent_correct} label="intent predicted" />
                </div>
                <div className="mt-3 text-sm text-ink2">Customer CSAT: <b className="text-ink">{state.kpis.csat ?? "–"}/5</b> · tools OK: {pct(state.kpis.tool_success_rate, 0)} · turns: {state.kpis.turns}</div>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
