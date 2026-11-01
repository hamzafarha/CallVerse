import {
  APP_URLS,
  Card,
  ErrorBox,
  PageSkeleton,
  Pill,
  Reveal,
  Ring,
  Spotlight,
  Stat,
  Status,
  motion,
  num,
  pct,
  useApi,
} from "@callverse/shared";
import { Activity, ArrowRight, Bot, Cpu, Database, MessageSquare, Package, Smile, Store } from "lucide-react";
import { Link } from "react-router-dom";
import { ArchitectureMap } from "../components/ArchitectureMap";

const BO_COLOR: Record<string, string> = {
  BO1: "var(--series-1)",
  BO2: "var(--series-7)",
  BO3: "var(--series-3)",
  BO4: "var(--series-2)",
};

export default function OverviewPage() {
  const { data, error } = useApi<any>("/api/overview");
  const system = useApi<any>("/api/system");
  if (error) return <ErrorBox error={error} />;
  if (!data) return <PageSkeleton />;
  const d = data.data;
  const cards = data.scorecard.length
    ? data.scorecard
    : Object.entries(data.objectives).map(([bo, o]: any) => ({ bo, dso: o.dso, objective: o.title, result: null, passed: null, main_idea: "", baseline: "" }));
  const passed = cards.filter((c: any) => c.passed).length;

  return (
    <div className="space-y-8">
      {/* hero */}
      <motion.section
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="card ring-gradient relative overflow-hidden p-8 md:p-10"
      >
        <div className="pointer-events-none absolute -right-20 -top-28 h-80 w-80 rounded-full opacity-25 blur-3xl gradient-brand" />
        <div className="relative grid items-center gap-8 lg:grid-cols-[1.4fr_1fr]">
          <div>
            <div className="chip mb-4 text-brand">
              <span className="live-dot" /> Multi-agent digital twin · e-commerce customer service
            </div>
            <h1 className="font-display text-4xl font-semibold leading-tight tracking-tight text-ink md:text-5xl">
              Test every decision on a <span className="gradient-text">virtual contact centre</span> first.
            </h1>
            <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-ink2">
              Forecast the demand, plan the shifts, route every customer and grade every AI conversation, then compare it
              all to the baselines with confidence intervals, before anything reaches a real customer.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link to="/twin" className="btn btn-primary">
                <Activity size={16} /> Watch the live floor
              </Link>
              <Link to="/agents" className="btn btn-ghost">
                <Bot size={16} /> Agent theater
              </Link>
              <a href={APP_URLS.front} target="_blank" rel="noreferrer" className="btn btn-ghost">
                <Store size={16} /> Front office
              </a>
            </div>
          </div>
          <div className="flex items-center justify-center gap-6">
            <Ring value={passed / Math.max(cards.length, 1)} size={150} stroke={12} color="var(--brand)">
              <div className="text-center">
                <div className="font-display text-4xl font-bold text-ink">
                  {passed}
                  <span className="text-xl text-muted">/{cards.length}</span>
                </div>
                <div className="text-[11px] uppercase tracking-wider text-muted">main ideas kept</div>
              </div>
            </Ring>
            <div className="space-y-2 text-xs text-ink2">
              {cards.map((c: any) => (
                <div key={c.bo} className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full" style={{ background: c.passed ? "var(--good)" : "var(--warning)" }} />
                  <b className="text-ink">{c.dso}</b> {c.passed ? "beats baseline" : "backup kept"}
                </div>
              ))}
            </div>
          </div>
        </div>
      </motion.section>

      {/* numbers */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Real orders (Olist)" numeric={d.orders} icon={<Package size={16} />} accent="var(--layer-data)" hint="2016-2018 · Brazilian marketplace" />
        <Stat label="Synthetic contacts" numeric={d.contacts} icon={<MessageSquare size={16} />} accent="var(--series-1)" hint={`${d.first_day} → ${d.last_day}`} />
        <Stat label="Chat messages" numeric={d.chat_messages} icon={<Database size={16} />} accent="var(--series-3)" hint={`${num(d.tickets, 0)} tickets in SQLite`} />
        <Stat
          label="Historical FCR · CSAT"
          value={`${pct(d.fcr_rate_history, 0)} · ${num(d.csat_history, 2)}`}
          icon={<Smile size={16} />}
          accent="var(--series-4)"
          hint="baseline of the logs"
        />
      </div>

      {/* scorecard */}
      <section>
        <Reveal>
          <div className="mb-4 flex items-end justify-between">
            <div>
              <h2 className="text-2xl font-semibold text-ink">Business objectives → data-science objectives</h2>
              <p className="mt-1 text-sm text-muted">Verdicts apply the switch rules of the DSO document (`callverse evaluate`).</p>
            </div>
            <Link to="/evaluation" className="btn btn-ghost hidden sm:inline-flex">
              Full scorecard <ArrowRight size={14} />
            </Link>
          </div>
        </Reveal>
        <div className="grid gap-4 md:grid-cols-2">
          {cards.map((card: any, i: number) => (
            <Reveal key={card.bo} delay={i * 0.08}>
              <Spotlight className="card card-hover h-full p-6">
                <div className="flex items-start gap-5">
                  <Ring value={card.passed ? 1 : card.passed === false ? 0.5 : 0} size={62} stroke={6} color={card.passed ? "var(--good)" : "var(--warning)"}>
                    <span className="font-display text-sm font-bold" style={{ color: BO_COLOR[card.bo] }}>
                      {card.bo}
                    </span>
                  </Ring>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-md px-2 py-0.5 text-[11px] font-bold text-white" style={{ background: BO_COLOR[card.bo] }}>
                        {card.dso}
                      </span>
                      <Status ok={card.passed} label={card.passed === null ? "not evaluated" : card.passed ? "main idea beats baseline" : "backup / hybrid kept"} />
                    </div>
                    <div className="mt-2 text-lg font-semibold text-ink">{card.objective}</div>
                    {card.main_idea && (
                      <div className="mt-1 text-xs text-ink2">
                        <b>{card.main_idea}</b> vs {card.baseline}
                      </div>
                    )}
                    {card.result && <div className="mt-3 rounded-xl bg-raised p-3 text-sm text-ink">{card.result}</div>}
                    {card.rule && <div className="mt-2 text-[11px] text-muted">Rule: {card.rule}</div>}
                  </div>
                </div>
              </Spotlight>
            </Reveal>
          ))}
        </div>
      </section>

      <Card title="Architecture" subtitle="Five layers, each a folder of src/callverse and a section of this control room. Click a layer to open it.">
        <ArchitectureMap />
      </Card>

      <Card
        title="Agent runtime"
        subtitle="Open-weight Hugging Face models run locally with transformers; every agent keeps an offline backup."
        action={
          <Link to="/mlops" className="btn btn-ghost py-1.5 text-xs">
            Models & MLOps <ArrowRight size={13} />
          </Link>
        }
      >
        {system.data ? (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Status ok={system.data.llm_available} label={system.data.llm_available ? "local LLMs ready" : system.data.llm_reason ?? "offline backups in use"} />
            {system.data.llm.gpu && (
              <Pill>
                <Cpu size={12} /> {system.data.llm.gpu.name}
              </Pill>
            )}
            {Object.entries(system.data.llm.roles).map(([role, m]: any) => (
              <Pill key={role}>
                {role}: {String(m.pinned).split("/").pop()}
              </Pill>
            ))}
            <Pill>retriever: {system.data.retriever}</Pill>
          </div>
        ) : (
          <div className="skeleton h-8" />
        )}
      </Card>
    </div>
  );
}
