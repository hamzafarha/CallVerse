import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, ChartTooltip, ErrorBox, Legend, Loading, PageHeader, Status } from "../components/ui";
import { useApi } from "../lib/api";
import { PLAN_LABEL, ROUTER_LABEL, eur, kpiValue, num, signed } from "../lib/format";

export default function EvaluationPage() {
  const { data, error, loading } = useApi<any>("/api/evaluation");
  if (error) return <ErrorBox error={error} />;
  if (loading || !data) return <Loading />;
  const empty = !data.dso3.summary.length;
  return (
    <div className="space-y-6">
      <PageHeader
        tag="Evaluation"
        color="var(--layer-eval)"
        title="Does each idea beat its baseline?"
        subtitle="Every number below comes from `callverse evaluate`: scenario weeks replayed over 10 seeds with common random numbers, paired differences with 95% confidence intervals, and component metrics for each part on its own."
      />
      {empty && <div className="card p-4 text-sm text-ink2">No evaluation tables yet. Run <code>callverse evaluate</code> (about 10 minutes).</div>}

      <Card title="BO → DSO scorecard" subtitle="Switch rules from the DSO document; thresholds are starting targets">
        <div className="overflow-x-auto">
          <table className="data">
            <thead><tr><th className="w-1/5">Objective</th><th className="w-1/5">Main idea vs baseline</th><th>Result and rule</th><th className="w-1/5">Verdict</th></tr></thead>
            <tbody>
              {data.scorecard.map((c: any) => (
                <tr key={c.bo} className="align-top">
                  <td className="text-ink"><b>{c.bo}/{c.dso}</b> {c.objective}</td>
                  <td className="text-xs">{c.main_idea}<div className="text-muted">vs {c.baseline}</div></td>
                  <td className="text-xs text-ink">{c.result ?? "–"}<div className="mt-1 text-muted">Rule: {c.rule}</div></td>
                  <td><Status ok={c.passed} label={c.passed ? "main idea kept" : "backup / hybrid kept"} />{!c.passed && c.fallback && <div className="mt-1 text-[11px] text-muted">{c.fallback}</div>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid gap-6">
        <Card title="BO4 — money saved by testing first" subtitle="Labour + lost-customer cost, unprepared minus prepared plan (EUR per week, 95% CI)">
          <div className="h-60">
            <ResponsiveContainer>
              <BarChart data={data.bo4.savings}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="scenario" tickLine={false} axisLine={{ stroke: "var(--baseline)" }} />
                <YAxis width={50} tickLine={false} axisLine={false} />
                <Tooltip content={<ChartTooltip format={(v: number) => eur(v)} />} cursor={{ fill: "var(--hairline)" }} />
                <Bar dataKey="money_saved_by_testing_eur" name="Saved" fill="var(--series-1)" radius={[4, 4, 0, 0]} barSize={44} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="data mt-3">
            <thead><tr><th>Scenario</th><th className="text-right">Net saving / week</th><th className="text-right">95% CI</th><th className="text-right">Extra labour</th><th className="text-right">Lost customers avoided</th><th className="text-right">Break-even cost of a lost customer</th></tr></thead>
            <tbody>
              {data.bo4.savings.map((r: any) => (
                <tr key={r.scenario}>
                  <td className="text-ink">{r.scenario}</td><td className="text-right font-medium">{eur(r.money_saved_by_testing_eur)}</td>
                  <td className="text-right text-xs text-muted">[{eur(r.ci_low)}, {eur(r.ci_high)}]</td><td className="text-right">{eur(r.extra_labour_eur)}</td>
                  <td className="text-right">{num(r.abandonments_avoided, 0)}</td><td className="text-right">{eur(r.break_even_abandonment_cost_eur)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-muted">Preparing pays off whenever a customer who hangs up is worth more than the break-even value (assumption in configs: €8).</p>
          <DiffTable rows={data.bo4.vs_unprepared} by="option" kpis={["understaffed_hours", "service_level", "abandon_rate", "total_cost_eur"]} />
        </Card>
        <Card title="DSO1 — routing in peak scenarios" subtitle="Change vs FIFO (paired, 95% CI); same unprepared CP-SAT plan">
          <DiffTable rows={data.dso1.vs_fifo} by="router" kpis={["asa_seconds", "abandon_rate", "service_level"]} labels={ROUTER_LABEL} />
        </Card>
      </div>

      <Card title="DSO3 — shift planners vs the fixed schedule" subtitle="Same customers; prepared plans; FIFO routing">
        <DiffTable rows={data.dso3.vs_fixed} by="plan" kpis={["labour_cost_eur", "cost_per_contact_eur", "service_level", "asa_seconds", "overtime_hours", "understaffed_hours"]} labels={PLAN_LABEL} />
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="DSO2 — conversations per advisor variant">
          <table className="data">
            <thead><tr><th>Variant</th><th className="text-right">n</th><th className="text-right">Verified policy action</th><th className="text-right">Judge says correct</th><th className="text-right">FCR</th><th className="text-right">CSAT</th><th className="text-right">Compliant</th><th className="text-right">Tools OK</th></tr></thead>
            <tbody>
              {data.dso2.summary.map((r: any) => (
                <tr key={r.variant}>
                  <td className="text-ink">{r.variant}</td><td className="text-right">{r.conversations}</td>
                  <td className="text-right font-medium">{r.verified_action_rate === null || r.verified_action_rate === undefined ? "not verifiable" : kpiValue("service_level", r.verified_action_rate)}</td>
                  <td className="text-right text-muted">{kpiValue("service_level", r.judge_correct_rate)}</td>
                  <td className="text-right">{kpiValue("service_level", r.fcr_rate)}</td>
                  <td className="text-right">{num(r.csat_mean, 2)}</td>
                  <td className="text-right">{kpiValue("service_level", r.compliance_rate)}</td>
                  <td className="text-right">{kpiValue("service_level", r.tool_success_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3 className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wide text-muted">Retrieval (Bitext questions, 17 intents)</h3>
          <table className="data">
            <thead><tr><th>Retriever</th><th className="text-right">Recall@1</th><th className="text-right">Recall@4</th><th className="text-right">MRR</th></tr></thead>
            <tbody>
              {data.dso2.retrieval.map((r: any) => (
                <tr key={r.retriever}><td className="text-ink">{r.retriever}</td><td className="text-right">{num(r.context_recall_at_1 * 100, 1)}%</td><td className="text-right">{num(r.context_recall_at_4 * 100, 1)}%</td><td className="text-right">{num(r.mrr, 3)}</td></tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Component metrics" subtitle="Is each part good on its own?">
          <div className="max-h-[420px] overflow-auto">
            <table className="data">
              <thead><tr><th>Component</th><th>Metric</th><th className="text-right">Value</th><th className="text-right">Ref.</th></tr></thead>
              <tbody>
                {data.component_metrics.map((r: any, i: number) => (
                  <tr key={i}><td className="text-ink">{r.component}</td><td className="text-xs">{r.metric}</td><td className="text-right">{num(r.value, 3)}</td><td className="text-right text-muted">{r.baseline ?? "–"}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Twin fidelity — time of day" subtitle="Share of contacts per hour, simulated vs historical"
          action={<Legend items={[{ label: "Historical", color: "var(--series-1)" }, { label: "Simulated", color: "var(--series-2)", dashed: true }]} />}>
          <div className="h-56">
            <ResponsiveContainer>
              <LineChart data={data.fidelity.hourly}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="hour" tickLine={false} axisLine={{ stroke: "var(--baseline)" }} />
                <YAxis width={36} tickLine={false} axisLine={false} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                <Tooltip content={<ChartTooltip format={(v: number) => `${(v * 100).toFixed(2)}%`} />} />
                <Line dataKey="historical_share" name="Historical" stroke="var(--series-1)" strokeWidth={2} dot={false} />
                <Line dataKey="simulated_share" name="Simulated" stroke="var(--series-2)" strokeWidth={2} strokeDasharray="4 3" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Twin fidelity checks">
          <table className="data">
            <thead><tr><th>Check</th><th className="text-right">Value</th><th>Detail</th><th /></tr></thead>
            <tbody>
              {data.fidelity.checks.map((r: any) => (
                <tr key={r.check}><td className="text-ink">{r.check}</td><td className="text-right">{num(r.value, 3)}</td><td className="text-xs">{r.detail}</td><td><Status ok={r.passed} /></td></tr>
              ))}
              {data.fidelity.erlang.map((r: any) => (
                <tr key={r.metric}><td className="text-ink">Erlang C: {r.metric}</td><td className="text-right">{num(r.simulated, 3)}</td><td className="text-xs">theory {num(r.expected, 3)} ({num(r.relative_error_percent, 1)}% error)</td><td><Status ok={r.passed} /></td></tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}

function DiffTable({ rows, by, kpis, labels = {} }: { rows: any[]; by: string; kpis: string[]; labels?: Record<string, string> }) {
  const filtered = rows.filter((r) => kpis.includes(r.kpi));
  if (!filtered.length) return <div className="text-sm text-muted">Not computed yet.</div>;
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="data">
        <thead><tr><th>Scenario</th><th>Option</th><th>KPI</th><th className="text-right">Option</th><th className="text-right">Baseline</th><th className="text-right">Change</th><th>Significant</th></tr></thead>
        <tbody>
          {filtered.map((r, i) => (
            <tr key={i}>
              <td className="text-xs">{r.scenario}</td><td className="text-xs text-ink">{labels[r[by]] ?? r[by]}</td><td className="text-xs">{r.label}</td>
              <td className="text-right">{kpiValue(r.kpi, r.option_mean)}</td><td className="text-right text-muted">{kpiValue(r.kpi, r.baseline_mean)}</td>
              <td className="text-right font-medium">{signed(r.relative_percent, 1)}</td>
              <td><Status ok={r.significant} label={r.significant ? "yes (95%)" : "no"} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
