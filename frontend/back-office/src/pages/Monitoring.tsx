/**
 * AI monitoring (back office, /monitoring): how the AI components behave, from data CallVerse already records
 * (GET /api/monitoring, callverse/evaluation/monitoring.py):
 *
 * the LLMs (calls, errors, cache, providers), latency, cost and tokens (with an "if we paid" estimate), the
 * RAG (offline benchmark and live citations), tool calling (who chose each tool: the AI, a pipeline step or a
 * safety net), the answers' quality and how far the judge can be trusted, the Workforce agent's routing,
 * grounding (does the advisor invent things?), the engines side by side, the judge against the customer, and
 * the numbers per resolved chat. The headline tiles turn orange or red past the thresholds of
 * configs/monitoring.yaml.
 */
import { Card, ChartTooltip, ErrorBox, GROUP_LABEL, Legend, PageHeader, Segmented, TOOL_LABEL, humanize, num, pct, useApi } from "@callverse/shared";
import {
  AlertTriangle,
  BookOpen,
  Briefcase,
  CheckCircle2,
  Coins,
  Cpu,
  Gauge,
  MinusCircle,
  Route,
  Scale,
  ShieldCheck,
  Timer,
  Wrench,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { type ReactNode, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";

type Period = "24h" | "7d" | "all";
type Source = "all" | "live" | "eval";

// --------------------------------------------------------------------------- formats
const ms = (v: number | null | undefined) => (v == null ? "–" : v >= 1000 ? `${num(v / 1000, 1)} s` : `${Math.round(v)} ms`);
const share = (v: number | null | undefined, digits = 0) => pct(v, digits);
const tokens = (v: number | null | undefined) => (v == null ? "–" : v >= 1e6 ? `${num(v / 1e6, 2)}M` : v >= 1e3 ? `${num(v / 1e3, 1)}k` : num(v, 0));
const usd = (v: number | null | undefined) => (v == null ? "–" : v < 0.01 ? `$${v.toFixed(5)}` : `$${v.toFixed(2)}`);
const model = (m: string) => String(m).split("/").pop()?.replace(":free", "") ?? m;

// Colours follow the entity, in the design system's fixed order (validated colour-blind-safe palette).
const PROVIDER_COLOR: Record<string, string> = { openrouter: "var(--series-1)", local: "var(--series-2)", unknown: "var(--baseline)" };
const AGENT_COLOR: Record<string, string> = { advisor: "var(--series-1)", client: "var(--series-2)", quality: "var(--series-3)" };
const CALLER_COLOR: Record<string, string> = { AI: "var(--series-1)", pipeline: "var(--series-2)", "safety net": "var(--series-3)", "not recorded": "var(--baseline)" };
const AGENT_LABEL: Record<string, string> = { advisor: "Advisor agent", client: "Client agent", quality: "Quality agent (judge)" };
const MODE_LABEL: Record<string, string> = { llm: "LLM", template_fallback: "Backup template (LLM failed)", template: "Template (offline mode)", human: "A person" };

// Status colours are reserved for the alerts, and always come with an icon and a word.
const LEVEL: Record<string, { color: string; icon: LucideIcon; word: string }> = {
  ok: { color: "var(--good)", icon: CheckCircle2, word: "OK" },
  warn: { color: "var(--warning)", icon: AlertTriangle, word: "Watch" },
  alert: { color: "var(--critical)", icon: XCircle, word: "Alert" },
  none: { color: "var(--text-muted)", icon: MinusCircle, word: "No data" },
};

const AXIS = { tickLine: false, axisLine: false, tick: { fontSize: 11, fill: "var(--text-muted)" } } as const;

export default function MonitoringPage() {
  const [period, setPeriod] = useState<Period>("all");
  const [source, setSource] = useState<Source>("all");
  const { data, error, loading } = useApi<any>(`/api/monitoring?period=${period}&source=${source}`);

  return (
    <div className="space-y-6">
      <PageHeader
        tag="Serving & MLOps · evaluation and monitoring"
        color="var(--layer-serve)"
        title="AI monitoring"
        subtitle="How the AI components behave: the LLMs, latency, cost, the RAG, tool calling, quality and routing. Everything is computed from what CallVerse already records: the trace of every LLM call, the saved chats and the evaluation's result tables."
      >
        <div className="flex flex-wrap gap-2">
          <Segmented
            id="mon-period"
            size="sm"
            value={period}
            onChange={setPeriod}
            options={[
              { value: "24h", label: "24 hours" },
              { value: "7d", label: "7 days" },
              { value: "all", label: "Everything" },
            ]}
          />
          <Segmented
            id="mon-source"
            size="sm"
            value={source}
            onChange={setSource}
            options={[
              { value: "all", label: "All chats" },
              { value: "live", label: "Live (apps)" },
              { value: "eval", label: "Evaluation runs" },
            ]}
          />
        </div>
      </PageHeader>
      {error && <ErrorBox error={error} />}
      {loading && !data && <p className="text-sm text-muted">Reading the traces and the saved chats…</p>}
      {data && <Report data={data} />}
    </div>
  );
}

function Report({ data }: { data: any }) {
  const alerts: Record<string, any> = Object.fromEntries((data.alerts ?? []).map((a: any) => [a.metric, a]));
  const h = data.headline;
  return (
    <>
      {/* Headline tiles: the watched metrics carry their alert colour (thresholds: configs/monitoring.yaml). */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile label="LLM calls" value={num(h.llm_calls, 0)} hint={`${num(h.chats, 0)} saved chats in this view`} />
        <Tile label="LLM latency, slow case (p95)" value={ms(alerts.llm_p95_latency_seconds?.value * 1000)} hint={`median ${ms(h.p50_ms)}`} alert={alerts.llm_p95_latency_seconds} />
        <Tile label="LLM errors" value={share(alerts.llm_error_rate?.value, 1)} hint="calls that failed (e.g. rate limited)" alert={alerts.llm_error_rate} />
        <Tile label="Fallback rate" value={share(h.fallback_rate, 1)} hint="advisor answers where the LLM failed and a template answered" alert={alerts.fallback_rate} />
        <Tile label="Tool success" value={share(h.tool_success_rate, 1)} hint="tool calls that worked" alert={alerts.tool_success_rate} />
        <Tile label="Quality score" value={h.quality == null ? "–" : `${num(h.quality, 2)} / 5`} hint="the Quality agent's overall score" alert={alerts.quality_overall} />
        <Tile label="Routing accuracy" value={share(h.routing_accuracy, 1)} hint="the Workforce agent found the right problem" alert={alerts.routing_accuracy} />
        <Tile
          label="Tokens and cost"
          value={tokens(h.tokens)}
          hint={`real cost €${num(h.real_cost_eur, 2)} (free tier, local GPU) · if we paid ≈ ${usd(h.estimate_usd)}`}
        />
      </div>
      <LlmSection llm={data.llm} />
      <div className="grid gap-6 xl:grid-cols-2">
        <LatencySection llm={data.llm} advisor={data.advisor} quality={data.quality} />
        <CostSection cost={data.cost} price={data.reference_price} />
      </div>
      <RagSection rag={data.rag} />
      <ToolsSection tools={data.tools} grounding={data.grounding} />
      <QualitySection quality={data.quality} />
      <div className="grid gap-6 xl:grid-cols-2">
        <RoutingSection routing={data.routing} />
        <JudgeSection pairs={data.judge_vs_customer} />
      </div>
      <EnginesSection engines={data.engines} variants={data.variants} components={data.rag.components} />
      <BusinessSection business={data.business} />
    </>
  );
}

// ----------------------------------------------------------------------------- pieces
/** One headline number; a watched one shows its alert level with a colour, an icon and a word. */
function Tile({ label, value, hint, alert }: { label: string; value: ReactNode; hint?: ReactNode; alert?: any }) {
  const level = alert ? LEVEL[alert.level] ?? LEVEL.none : null;
  const Icon = level?.icon;
  return (
    <div className="card p-4" style={level ? { borderLeft: `4px solid ${level.color}` } : undefined}>
      <div className="flex items-center justify-between gap-2 text-xs font-medium text-muted">
        <span>{label}</span>
        {level && Icon && (
          <span
            className="inline-flex items-center gap-1 text-[11px] font-semibold text-ink2"
            title={`Watch past ${alert.warn}, alert past ${alert.alert} (${alert.better} is better)`}
          >
            <Icon size={13} color={level.color} aria-hidden /> {level.word}
          </span>
        )}
      </div>
      <div className="mt-1 font-display text-2xl font-semibold tabular text-ink">{value}</div>
      {hint && <div className="mt-0.5 text-xs leading-snug text-muted">{hint}</div>}
    </div>
  );
}

/** A compact table (every chart has its numbers in a table too). */
function Table({ head, rows }: { head: ReactNode[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs text-muted">
            {head.map((cell, i) => (
              <th key={i} className={i === 0 ? "py-2 pr-3 font-medium" : "px-3 py-2 text-right font-medium"}>
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r} className="border-b border-line/60 last:border-0">
              {row.map((cell, i) => (
                <td key={i} className={i === 0 ? "py-2 pr-3 text-ink" : "px-3 py-2 text-right tabular text-ink2"}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Note({ children }: { children: ReactNode }) {
  return <p className="mt-3 text-xs leading-relaxed text-muted">{children}</p>;
}

function Mini({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-xl bg-raised px-3 py-2">
      <div className="font-display text-lg font-semibold tabular text-ink">{value}</div>
      <div className="text-[11px] leading-tight text-muted">{label}</div>
    </div>
  );
}

// --------------------------------------------------------------------------- sections
function LlmSection({ llm }: { llm: any }) {
  const providers: string[] = llm.providers ?? [];
  return (
    <Card title="LLMs: are the models working?" subtitle="Every LLM call of the server (artifacts/traces/llm_calls.jsonl), whatever chat it belongs to." icon={<Cpu size={16} />}>
      <div className="h-56">
        <ResponsiveContainer>
          <BarChart data={llm.per_day} margin={{ top: 8, right: 8 }}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="day" {...AXIS} minTickGap={24} />
            <YAxis width={36} {...AXIS} allowDecimals={false} />
            <Tooltip content={<ChartTooltip format={(v: number) => `${num(v, 0)} calls`} />} cursor={{ fill: "var(--hairline)" }} />
            {providers.map((p, i) => (
              <Bar
                key={p}
                dataKey={p}
                name={p === "openrouter" ? "OpenRouter (hosted)" : p === "local" ? "Local GPU" : humanize(p)}
                stackId="calls"
                fill={PROVIDER_COLOR[p] ?? "var(--series-4)"}
                stroke="var(--surface-1)"
                strokeWidth={2}
                radius={i === providers.length - 1 ? [4, 4, 0, 0] : 0}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mb-4 mt-2">
        <Legend items={providers.map((p) => ({ label: p === "openrouter" ? "OpenRouter (hosted)" : p === "local" ? "Local GPU" : humanize(p), color: PROVIDER_COLOR[p] ?? "var(--series-4)" }))} />
      </div>
      <Table
        head={["Agent · model", "Provider", "Calls", "Errors", "Cache hits", "p50", "p95", "Tokens/s"]}
        rows={llm.by_model.map((r: any) => [
          <span key="m">
            <b className="font-medium">{AGENT_LABEL[r.agent] ?? r.agent}</b> · <span className="text-ink2">{model(r.model)}</span>
          </span>,
          r.provider,
          num(r.calls, 0),
          share(r.error_rate, 1),
          share(r.cache_rate),
          ms(r.p50_ms),
          ms(r.p95_ms),
          num(r.tokens_per_second, 1),
        ])}
      />
      {llm.errors?.length > 0 && (
        <div className="mt-4">
          <div className="mb-1 text-xs font-semibold text-ink2">Last errors</div>
          <ul className="space-y-1 text-xs text-ink2">
            {llm.errors.map((e: any, i: number) => (
              <li key={i} className="rounded-lg bg-raised px-2.5 py-1.5">
                <span className="tabular text-muted">{String(e.ts).replace("T", " ")}</span> · {AGENT_LABEL[e.agent] ?? e.agent} · {e.error}
              </li>
            ))}
          </ul>
        </div>
      )}
      <Note>
        p50 = the median (half the calls are faster); p95 = the slow case (95% of the calls are faster). Latency counts only real answers:
        a cached call costs no time, an error has no answer. Cache hits: the same question asked again is answered from the cache.
      </Note>
    </Card>
  );
}

function LatencySection({ llm, advisor, quality }: { llm: any; advisor: any; quality: any }) {
  return (
    <Card title="Latency: how fast is it?" subtitle="One LLM call, one advisor answer (retrieval + tools + LLM), and the judge's review." icon={<Timer size={16} />}>
      <Table
        head={["Step", "Calls", "Median (p50)", "Slow case (p95)"]}
        rows={[
          ...llm.by_agent.map((r: any) => [`LLM call · ${AGENT_LABEL[r.agent] ?? r.agent}`, num(r.calls, 0), ms(r.p50_ms), ms(r.p95_ms)]),
          ["Advisor answer · written by the LLM", num(advisor.modes?.llm ?? 0, 0), ms(advisor.reply_llm_p50_ms), ms(advisor.reply_llm_p95_ms)],
          ["Advisor answer · template (no LLM)", num((advisor.modes?.template ?? 0) + (advisor.modes?.template_fallback ?? 0), 0), ms(advisor.reply_template_p50_ms), "–"],
          ["Quality agent's review", num(quality.chats, 0), ms(quality.judge_p50_ms), "–"],
        ]}
      />
      <div className="mt-4">
        <div className="mb-1 text-xs font-semibold text-ink2">Who wrote the advisor's answers</div>
        <Table
          head={["Writer", "Answers"]}
          rows={Object.entries(advisor.modes ?? {})
            .sort((a: any, b: any) => b[1] - a[1])
            .map(([mode, n]: any) => [MODE_LABEL[mode] ?? humanize(mode), num(n, 0)])}
        />
      </div>
      <Note>The fallback rate in the tiles = backup templates ÷ (LLM answers + backup templates): how often the safety chain was needed.</Note>
    </Card>
  );
}

function CostSection({ cost, price }: { cost: any; price: any }) {
  const agents = cost.by_agent.map((r: any) => r.agent);
  return (
    <Card title="Cost and tokens" subtitle="Tokens per day and per agent; what it costs, and what it would cost on a paid model." icon={<Coins size={16} />}>
      <div className="grid grid-cols-3 gap-2">
        <Mini label="tokens (prompt + generated)" value={tokens(cost.prompt_tokens + cost.completion_tokens)} />
        <Mini label="real cost (free tier, local GPU)" value={`€${num(cost.real_eur, 2)}`} />
        <Mini label="if we paid (estimate)" value={usd(cost.estimate_usd)} />
      </div>
      <div className="mt-4 h-44">
        <ResponsiveContainer>
          <BarChart data={cost.per_day} margin={{ top: 8, right: 8 }}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="day" {...AXIS} minTickGap={24} />
            <YAxis width={44} {...AXIS} tickFormatter={(v) => tokens(v)} />
            <Tooltip content={<ChartTooltip format={(v: number) => `${tokens(v)} tokens`} />} cursor={{ fill: "var(--hairline)" }} />
            {agents.map((a: string, i: number) => (
              <Bar key={a} dataKey={a} name={AGENT_LABEL[a] ?? a} stackId="t" fill={AGENT_COLOR[a] ?? "var(--series-4)"} stroke="var(--surface-1)" strokeWidth={2} radius={i === agents.length - 1 ? [4, 4, 0, 0] : 0} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mb-3 mt-2">
        <Legend items={agents.map((a: string) => ({ label: AGENT_LABEL[a] ?? a, color: AGENT_COLOR[a] ?? "var(--series-4)" }))} />
      </div>
      <Table
        head={["Agent", "Prompt tokens", "Generated tokens", "If we paid"]}
        rows={cost.by_agent.map((r: any) => [AGENT_LABEL[r.agent] ?? r.agent, tokens(r.prompt_tokens), tokens(r.completion_tokens), usd(r.estimate_usd)])}
      />
      <Note>
        "If we paid" is an estimate only: the tokens × {price?.name} (${price?.input_per_million_usd} per million prompt tokens, $
        {price?.output_per_million_usd} per million generated tokens). Change the yardstick in configs/monitoring.yaml.
      </Note>
    </Card>
  );
}

function RagSection({ rag }: { rag: any }) {
  const quality = (rag.components ?? []).filter((c: any) => c.component === "RAG advisor" && !String(c.metric).startsWith("Context recall"));
  return (
    <Card title="RAG: does the advisor find the right policy?" subtitle="Offline: the retrieval benchmark and the answers' faithfulness. Live: how many answers cite a policy section." icon={<BookOpen size={16} />}>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <Table
            head={["Retriever (offline benchmark)", "Questions", "Recall@1", "Recall@4", "MRR"]}
            rows={(rag.offline ?? []).map((r: any) => [r.retriever, num(r.questions, 0), share(r.context_recall_at_1, 1), share(r.context_recall_at_4, 1), num(r.mrr, 3)])}
          />
          <Table
            head={["Answer quality (offline)", "Value"]}
            rows={quality.map((c: any) => [c.metric, c.unit === "share" ? share(c.value, 1) : num(c.value, 3)])}
          />
        </div>
        <div>
          <div className="grid grid-cols-2 gap-2">
            <Mini label="advisor answers (live view)" value={num(rag.live?.answers, 0)} />
            <Mini label="cite at least one policy section" value={share(rag.live?.cited_share, 0)} />
          </div>
          <div className="mt-3 text-xs font-semibold text-ink2">Most cited sources</div>
          <Table head={["Source", "Answers"]} rows={(rag.live?.top_sections ?? []).map((s: any) => [humanize(s.section), num(s.answers, 0)])} />
        </div>
      </div>
      <Note>
        Recall@k = how often the right policy section is among the first k results; MRR = how high the right section ranks on average (1 =
        always first). Faithfulness = the share of the answer's claims supported by the retrieved policy; relevance and similarity are cosine
        similarities (0 to 1).
      </Note>
    </Card>
  );
}

function ToolsSection({ tools, grounding }: { tools: any; grounding: any }) {
  const callers: [string, number][] = Object.entries(tools.callers ?? {}) as [string, number][];
  const total = callers.reduce((sum, [, n]) => sum + n, 0);
  const order = ["AI", "pipeline", "safety net", "not recorded"];
  callers.sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]));
  return (
    <Card title="Tool calling: do the agents use their tools well?" subtitle="Every tool call of the saved chats: success, time, who chose it, and the MCP server." icon={<Wrench size={16} />}>
      <div className="text-xs font-semibold text-ink2">Who chose the advisor's tools</div>
      {/* One segmented bar: each part labelled with its share (identity is never colour alone). */}
      <div className="mt-2 flex h-7 w-full overflow-hidden rounded-lg" role="img" aria-label={callers.map(([c, n]) => `${c}: ${n}`).join(", ")}>
        {callers.map(([caller, n]) => (
          <div key={caller} className="flex items-center justify-center text-[11px] font-semibold text-white" style={{ width: `${(100 * n) / Math.max(1, total)}%`, background: CALLER_COLOR[caller], borderRight: "2px solid var(--surface-1)" }} title={`${caller}: ${n}`}>
            {n / Math.max(1, total) > 0.08 ? `${Math.round((100 * n) / total)}%` : ""}
          </div>
        ))}
      </div>
      <div className="mt-2">
        <Legend items={callers.map(([c, n]) => ({ label: `${c === "AI" ? "the AI chose it" : c === "pipeline" ? "a fixed pipeline step" : c === "safety net" ? "a safety net" : "not recorded (older chats)"} · ${n}`, color: CALLER_COLOR[c] }))} />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Mini label="tool calls" value={num(tools.calls, 0)} />
        <Mini label="tool calls per chat" value={num(tools.per_chat, 2)} />
        <Mini label="through the MCP server" value={tools.via?.mcp != null ? `${tools.via.mcp} of ${(tools.via.mcp ?? 0) + (tools.via.direct ?? 0)}` : "–"} />
        <Mini label="fact checks run" value={num(grounding.fact_checks, 0)} />
      </div>
      <div className="mt-4">
        <Table
          head={["Tool", "Calls", "Success", "Average time", "Chosen by the AI", "Through MCP"]}
          rows={(tools.rows ?? []).map((r: any) => [
            <span key="t">
              {TOOL_LABEL[r.tool] ?? humanize(r.tool)} <span className="text-xs text-muted">· {r.agent === "customer" ? "Client agent" : "Advisor agent"}</span>
            </span>,
            num(r.calls, 0),
            share(r.success_rate, 1),
            ms(r.mean_ms),
            num(r.callers?.AI ?? 0, 0),
            r.mcp_share == null ? "–" : share(r.mcp_share),
          ])}
        />
      </div>
      <Note>
        The honest finding: a small model rarely chooses a tool by itself, so most calls are fixed pipeline steps, with safety nets when the
        LLM forgets. "Not recorded" = chats saved before the caller was logged.
      </Note>
    </Card>
  );
}

function QualitySection({ quality }: { quality: any }) {
  const criteria = Object.entries(quality.criteria ?? {}) as [string, number][];
  return (
    <Card title="Quality: are the answers good?" subtitle="The Quality agent's scorecard of every saved chat, and how far that judge can be trusted." icon={<ShieldCheck size={16} />}>
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div>
          <div className="text-xs font-semibold text-ink2">Overall score per day (out of 5)</div>
          <div className="mt-2 h-44">
            <ResponsiveContainer>
              <LineChart data={quality.per_day} margin={{ top: 8, right: 12 }}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="day" {...AXIS} minTickGap={24} />
                <YAxis width={28} {...AXIS} domain={[1, 5]} ticks={[1, 2, 3, 4, 5]} />
                <Tooltip content={<ChartTooltip format={(v: number) => `${num(v, 2)} / 5`} />} />
                <Line dataKey="overall" name="Overall score" stroke="var(--series-1)" strokeWidth={2} dot={{ r: 4, strokeWidth: 2, stroke: "var(--surface-1)" }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Mini label="resolved" value={share(quality.resolved)} />
            <Mini label="solved at first contact (FCR)" value={share(quality.fcr)} />
            <Mini label="customer rating (CSAT)" value={quality.csat == null ? "–" : `${num(quality.csat, 2)} / 5`} />
            <Mini label="compliant with the policy" value={share(quality.compliant)} />
            <Mini label="policy-correct, checked by code" value={share(quality.correct_by_code)} />
            <Mini label="policy-correct, says the judge" value={share(quality.correct_by_judge)} />
            <Mini label="code and judge agree" value={share(quality.code_judge_agreement)} />
            <Mini label="judges used" value={Object.entries(quality.judges ?? {}).map(([j, n]) => `${j === "llm" ? "LLM" : "rules"} ${n}`).join(" · ") || "–"} />
          </div>
        </div>
        <div>
          <div className="text-xs font-semibold text-ink2">The five criteria (average, out of 5)</div>
          <div className="mt-2 space-y-2">
            {criteria.map(([c, v]) => (
              <div key={c} className="grid grid-cols-[96px_1fr_36px] items-center gap-2 text-xs text-ink2">
                <span>{c}</span>
                <span className="h-2 overflow-hidden rounded-full bg-sunken">
                  <span className="block h-full rounded-full" style={{ width: `${((v ?? 0) / 5) * 100}%`, background: "var(--series-1)" }} />
                </span>
                <span className="text-right tabular text-ink">{num(v, 2)}</span>
              </div>
            ))}
          </div>
          <div className="mt-4 text-xs font-semibold text-ink2">Can we trust the judge? (offline, against human labels)</div>
          <Table
            head={["Judge · criterion", "n", "Kappa"]}
            rows={(quality.calibration ?? []).slice(0, 10).map((r: any) => [`${r.judge} · ${r.criterion}`, num(r.n, 0), num(r.quadratic_kappa, 2)])}
          />
          <Note>Quadratic kappa: 1 = perfect agreement with the human labels, 0 = no better than chance. Below 0.4, the judge is not trusted yet.</Note>
        </div>
      </div>
    </Card>
  );
}

function RoutingSection({ routing }: { routing: any }) {
  const max = Math.max(1, ...routing.matrix.flat());
  const step = (v: number) => (v === 0 ? -1 : Math.min(4, Math.floor((v / max) * 4.999)));
  const SEQ = ["--seq-100", "--seq-250", "--seq-400", "--seq-550", "--seq-700"];
  return (
    <Card title="Routing: does the Workforce agent find the right problem?" subtitle="Its guess against the customer's real problem, in every saved chat." icon={<Route size={16} />}>
      <div className="grid grid-cols-2 gap-2">
        <Mini label="right problem" value={share(routing.accuracy, 1)} />
        <Mini label="chats routed" value={num(routing.chats, 0)} />
      </div>
      <div className="mt-4 text-xs font-semibold text-ink2">Problem families mixed up (rows: the real problem · columns: the guess)</div>
      <div className="mt-2 overflow-x-auto">
        <table className="text-xs" role="grid">
          <thead>
            <tr>
              <th />
              {routing.groups.map((g: string) => (
                <th key={g} className="px-1 pb-1 font-medium text-muted">
                  {GROUP_LABEL[g] ?? g}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {routing.matrix.map((row: number[], i: number) => (
              <tr key={i}>
                <th className="pr-2 text-right font-medium text-muted">{GROUP_LABEL[routing.groups[i]] ?? routing.groups[i]}</th>
                {row.map((v, j) => {
                  const s = step(v);
                  return (
                    <td key={j} className="p-0.5">
                      <div
                        className="flex h-10 w-20 items-center justify-center rounded-md font-semibold tabular"
                        style={{ background: s < 0 ? "var(--surface-2)" : `var(${SEQ[s]})`, color: s < 0 ? "var(--text-muted)" : `var(--seq-ink-${s})` }}
                        title={`${GROUP_LABEL[routing.groups[i]]} guessed as ${GROUP_LABEL[routing.groups[j]]}: ${v} chats`}
                      >
                        {v}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {routing.mistakes?.length > 0 && (
        <>
          <div className="mt-4 text-xs font-semibold text-ink2">Most frequent mistakes</div>
          <Table head={["Real problem → guess", "Chats"]} rows={routing.mistakes.map((m: any) => [`${humanize(m.true)} → ${humanize(m.predicted)}`, num(m.chats, 0)])} />
        </>
      )}
      <div className="mt-4 text-xs font-semibold text-ink2">Is it right more often when it is more sure? (accuracy by confidence)</div>
      <div className="mt-2 h-36">
        <ResponsiveContainer>
          <BarChart data={routing.confidence.map((b: any) => ({ ...b, bin: `${Math.round(b.from * 100)}–${Math.round(b.to * 100)}%`, acc: b.accuracy == null ? null : b.accuracy * 100 }))} margin={{ top: 16, right: 8 }}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="bin" {...AXIS} />
            <YAxis width={44} {...AXIS} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
            <Tooltip content={<ChartTooltip format={(v: number) => `${num(v, 1)}% right`} />} cursor={{ fill: "var(--hairline)" }} />
            <Bar dataKey="acc" name="Accuracy" fill="var(--series-1)" radius={[4, 4, 0, 0]} label={{ position: "top", fontSize: 11, fill: "var(--text-secondary)", formatter: (v: number) => (v == null ? "" : `${Math.round(v)}%`) }} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <Note>Chats per confidence band: {routing.confidence.map((b: any) => `${Math.round(b.from * 100)}–${Math.round(b.to * 100)}%: ${b.chats}`).join(" · ")}.</Note>
    </Card>
  );
}

function JudgeSection({ pairs }: { pairs: any }) {
  // Many chats share the same (score, rating): one bubble per pair of values, its size = the number of chats.
  const counts = new Map<string, { judge: number; csat: number; chats: number }>();
  for (const [score, csat] of pairs.points ?? []) {
    const judge = Math.round(score * 2) / 2;
    const key = `${judge}-${csat}`;
    const cell = counts.get(key) ?? { judge, csat, chats: 0 };
    cell.chats += 1;
    counts.set(key, cell);
  }
  const cells = [...counts.values()];
  return (
    <Card title="The judge against the customer" subtitle="Two independent views of quality: the Quality agent's score and the customer's own rating. Do they agree?" icon={<Scale size={16} />}>
      <div className="grid grid-cols-3 gap-2">
        <Mini label="chats with both" value={num(pairs.chats, 0)} />
        <Mini label="Pearson correlation" value={num(pairs.pearson, 2)} />
        <Mini label="Spearman (ranks)" value={num(pairs.spearman, 2)} />
      </div>
      <div className="mt-4 h-64">
        <ResponsiveContainer>
          <ScatterChart margin={{ top: 8, right: 16, bottom: 8 }}>
            <CartesianGrid />
            <XAxis type="number" dataKey="judge" name="Judge's score" domain={[1, 5]} ticks={[1, 2, 3, 4, 5]} {...AXIS} label={{ value: "judge's score", position: "insideBottom", offset: -4, fontSize: 11, fill: "var(--text-muted)" }} />
            <YAxis type="number" dataKey="csat" name="Customer's rating" domain={[1, 5]} ticks={[1, 2, 3, 4, 5]} width={36} {...AXIS} label={{ value: "customer", angle: -90, position: "insideLeft", fontSize: 11, fill: "var(--text-muted)" }} />
            <ZAxis type="number" dataKey="chats" range={[60, 700]} />
            <Tooltip
              cursor={{ strokeDasharray: "3 3" }}
              content={({ active, payload }: any) =>
                active && payload?.length ? (
                  <div className="glass rounded-xl px-3 py-2 text-xs shadow-lift">
                    Judge {payload[0].payload.judge} · customer {payload[0].payload.csat}/5 · <b>{payload[0].payload.chats} chats</b>
                  </div>
                ) : null
              }
            />
            <Scatter data={cells} fill="var(--series-1)" fillOpacity={0.7} stroke="var(--surface-1)" strokeWidth={2} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <Note>
        A correlation near 1 means they agree; near 0, they do not. Bigger bubbles = more chats. A weak agreement is a finding in itself: the
        judge and the customers do not value the same things.
      </Note>
    </Card>
  );
}

function EnginesSection({ engines, variants, components }: { engines: any[]; variants: any[]; components: any[] }) {
  const faithful = (variant: string) => components.find((c: any) => c.metric === `Faithfulness (${variant})`)?.value;
  return (
    <Card title="Engines and variants side by side" subtitle="The same metrics for each engine (live and evaluation chats) and for each advisor variant (the offline evaluation)." icon={<Gauge size={16} />}>
      <Table
        head={["Engine (who wrote the answers)", "Chats", "Quality", "Policy-correct", "FCR", "CSAT", "Answer time (p50)", "Tokens per chat"]}
        rows={engines.map((e) => [e.engine, num(e.chats, 0), num(e.quality, 2), share(e.correct_by_code), share(e.fcr), num(e.csat, 2), ms(e.reply_p50_ms), tokens(e.tokens_per_chat)])}
      />
      {variants.length > 0 && (
        <div className="mt-5">
          <div className="mb-1 text-xs font-semibold text-ink2">Advisor variants (offline evaluation, same contacts for each)</div>
          <Table
            head={["Variant", "Chats", "Quality", "Correct answer", "FCR", "CSAT", "Faithfulness", "Routing accuracy"]}
            rows={variants.map((v) => [<code key="v">{v.variant}</code>, num(v.conversations, 0), num(v.quality_overall, 2), share(v.correct_answer_rate), share(v.fcr_rate), num(v.csat_mean, 2), share(faithful(v.variant), 1), share(v.intent_accuracy)])}
          />
        </div>
      )}
      <Note>rag = retrieval + LLM; rag_policy = the rules engine decides and the LLM writes; template = no LLM (the offline backup).</Note>
    </Card>
  );
}

function BusinessSection({ business }: { business: any }) {
  return (
    <Card title="Per resolved chat" subtitle="The AI's numbers turned into what a manager reads." icon={<Briefcase size={16} />}>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        <Mini label={`resolved chats (${share(business.resolved_share)})`} value={num(business.resolved_chats, 0)} />
        <Mini label="advisor tokens per resolved chat" value={tokens(business.tokens_per_resolved)} />
        <Mini label="cost per resolved chat, if we paid" value={usd(business.estimate_usd_per_resolved)} />
        <Mini label="advisor answers per resolved chat" value={num(business.replies_per_resolved, 1)} />
        <Mini label="AI processing time per resolved chat" value={business.ai_seconds_per_resolved == null ? "–" : `${num(business.ai_seconds_per_resolved, 1)} s`} />
      </div>
    </Card>
  );
}
