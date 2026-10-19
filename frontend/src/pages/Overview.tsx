import { ArrowRight, Bot, Database, FlaskConical, Server, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import { Card, ErrorBox, Loading, PageHeader, Pill, Stat, Status } from "../components/ui";
import { useApi } from "../lib/api";
import { num, pct } from "../lib/format";

const LAYERS = [
  {
    icon: Database, color: "var(--layer-data)", title: "Data layer", to: "/data",
    text: "Olist orders + Bitext intents → synthetic contacts, tickets and chats (SQLite), bge-m3 knowledge base, Pandera contracts.",
  },
  {
    icon: TrendingUp, color: "var(--layer-sim)", title: "Forecast & simulation", to: "/forecast",
    text: "LightGBM contact forecast per intent (vs naive, SARIMA, Prophet) feeding a SimPy call-center twin.",
  },
  {
    icon: Bot, color: "var(--layer-agents)", title: "Digital twin agents", to: "/agents",
    text: "Client, Advisor (RAG + tools), Quality (LLM judge) and Workforce (PPO routing + CP-SAT shifts), orchestrated by LangGraph.",
  },
  {
    icon: FlaskConical, color: "var(--layer-eval)", title: "Evaluation", to: "/evaluation",
    text: "Scenario testing with seeds and 95% CIs, KPI engine per BO, component metrics per DSO.",
  },
  {
    icon: Server, color: "var(--layer-serve)", title: "Serving & MLOps", to: "/mlops",
    text: "FastAPI + WebSocket, this React control room, MLflow tracking, LLM tracing, Docker Compose, CI.",
  },
];

export default function OverviewPage() {
  const { data, error, loading } = useApi<any>("/api/overview");
  const status = useApi<any>("/api/agents/status");
  if (error) return <ErrorBox error={error} />;
  if (loading || !data) return <Loading />;
  const d = data.data;
  return (
    <div className="space-y-6">
      <PageHeader
        title="CallVerse control room"
        subtitle="A multi-agent digital twin of an e-commerce customer service center: forecast the demand, test staffing and routing decisions on a virtual center, and grade every AI conversation before anything reaches real customers."
      >
        <Link to="/twin" className="btn btn-primary">
          Run a what-if <ArrowRight size={16} />
        </Link>
      </PageHeader>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Real orders (Olist)" value={num(d.orders, 0)} hint="2016-2018, Brazil marketplace" />
        <Stat label="Synthetic contacts" value={num(d.contacts, 0)} hint={`${d.first_day} → ${d.last_day}`} />
        <Stat label="Chat messages" value={num(d.chat_messages, 0)} hint={`${num(d.tickets, 0)} tickets in SQLite`} />
        <Stat label="Historical FCR / CSAT" value={`${pct(d.fcr_rate_history, 0)} · ${num(d.csat_history, 2)}`} hint="baseline of the logs" />
      </div>

      <Card title="Business objectives → data science objectives" subtitle="Verdicts apply the switch rules of the DSO document (computed by `callverse evaluate`).">
        <div className="grid gap-4 md:grid-cols-2">
          {(data.scorecard.length ? data.scorecard : Object.entries(data.objectives).map(([bo, o]: any) => ({
            bo, dso: o.dso, objective: o.title, result: null, passed: null, main_idea: "", baseline: "",
          }))).map((card: any) => (
            <div key={card.bo} className="rounded-xl border border-line p-4">
              <div className="mb-2 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="rounded-md border border-line bg-raised px-2 py-0.5 text-xs font-bold text-ink">{card.bo}</span>
                  <ArrowRight size={14} className="text-muted" />
                  <span className="rounded-md px-2 py-0.5 text-xs font-bold text-white" style={{ background: "var(--brand)" }}>{card.dso}</span>
                </div>
                <Status ok={card.passed} label={card.passed === null ? "not evaluated" : card.passed ? "beats baseline" : "see fallback"} />
              </div>
              <div className="font-medium text-ink">{card.objective}</div>
              {card.main_idea && (
                <div className="mt-1 text-xs text-ink2">
                  Main idea: <b>{card.main_idea}</b> · baseline: {card.baseline}
                </div>
              )}
              {card.result && <div className="mt-2 text-sm text-ink">{card.result}</div>}
              {card.rule && <div className="mt-1 text-xs text-muted">Rule: {card.rule}</div>}
            </div>
          ))}
        </div>
      </Card>

      <Card title="Architecture" subtitle="Five layers, each a folder of src/callverse and a page of this app.">
        <div className="grid gap-3 md:grid-cols-5">
          {LAYERS.map(({ icon: Icon, color, title, text, to }) => (
            <Link key={title} to={to} className="group rounded-xl border border-line p-4 transition hover:shadow-md">
              <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-lg" style={{ background: color }}>
                <Icon size={18} className="text-white" />
              </div>
              <div className="text-sm font-semibold text-ink group-hover:underline">{title}</div>
              <p className="mt-1 text-xs leading-relaxed text-ink2">{text}</p>
            </Link>
          ))}
        </div>
      </Card>

      <Card title="Agent runtime" subtitle="Local LLMs served by Ollama; every agent has an offline backup.">
        {status.data ? (
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <Status ok={status.data.llm_available} label={status.data.llm_available ? "Ollama reachable" : "Ollama offline: backups in use"} />
            <Pill>profile: {status.data.llm_mode}</Pill>
            {Object.entries(status.data.pinned_models ?? {}).map(([role, model]) => (
              <Pill key={role}>
                {role}: {String(model)}
              </Pill>
            ))}
            <Pill>retriever: {status.data.retriever}</Pill>
          </div>
        ) : (
          <Loading text="Checking agents" />
        )}
      </Card>
    </div>
  );
}
