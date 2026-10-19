import { Play, Scale } from "lucide-react";
import { useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { StaffingHeatmap } from "../components/Heatmap";
import { Card, ChartTooltip, ErrorBox, Legend, Loading, PageHeader, Pill, Stat } from "../components/ui";
import { postJson, useApi } from "../lib/api";
import { DAYS, GROUPS, GROUP_LABEL, PLAN_LABEL, ROUTER_LABEL, kpiValue, num } from "../lib/format";

const TILE_KPIS = [
  "service_level", "abandon_rate", "asa_seconds", "understaffed_hours",
  "labour_cost_eur", "overtime_hours", "cost_per_contact_eur", "total_cost_eur",
];
const LOWER_IS_BETTER = new Set(["abandon_rate", "asa_seconds", "understaffed_hours", "labour_cost_eur",
  "overtime_hours", "cost_per_contact_eur", "total_cost_eur"]);

export default function TwinPage() {
  const config = useApi<any>("/api/twin/config");
  const [form, setForm] = useState<any>({ scenario: "promo_spike", plan: "cpsat", router: "fifo", seeds: 5, prepared: true });
  const [custom, setCustom] = useState<Record<string, number> | null>(null);
  const [absence, setAbsence] = useState<number | null>(null);
  const [result, setResult] = useState<any>(null);
  const [compare, setCompare] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const scenario = config.data?.scenarios?.[form.scenario];
  const multipliers = custom ?? scenario?.multipliers ?? {};

  const run = async () => {
    setBusy("run"); setError(null);
    try {
      setResult(await postJson("/api/twin/run", { ...form, multipliers: custom ?? undefined, absence_rate: absence ?? undefined }));
    } catch (e: any) { setError(e.message); } finally { setBusy(null); }
  };
  const runCompare = async () => {
    setBusy("compare"); setError(null);
    try {
      setCompare(await postJson("/api/twin/compare", {
        scenario: form.scenario, seeds: form.seeds,
        options: [
          { plan: "cpsat", router: "fifo", prepared: false },
          { plan: "cpsat", router: "fifo", prepared: true },
          { plan: "fixed", router: "fifo", prepared: true },
          { plan: "cpsat", router: config.data?.ppo_available ? "ppo" : "skill_score", prepared: false },
        ].map((o) => ({ ...o, scenario: form.scenario, multipliers: custom ?? undefined, absence_rate: absence ?? undefined })),
      }));
    } catch (e: any) { setError(e.message); } finally { setBusy(null); }
  };

  const kpis: Record<string, any> = useMemo(
    () => Object.fromEntries((result?.kpis ?? []).map((k: any) => [k.kpi, k])), [result]);
  const queue = (result?.queue ?? []).map((r: any) => ({
    ...r, label: `${DAYS[Math.floor(r.hour_index / 24) % 7]} ${r.hour_index % 24}h`,
  }));

  if (config.error) return <ErrorBox error={config.error} />;
  if (!config.data) return <Loading />;
  const c = config.data;
  return (
    <div className="space-y-6">
      <PageHeader
        tag="DSO4 · part 2 — the digital twin"
        color="var(--layer-sim)"
        title="Test a decision before applying it"
        subtitle="Pick a peak scenario, a staffing planner and a routing policy. The twin replays a real week of contacts with Poisson arrivals, customer personas, skilled agents and abandonment, over several seeds. Unprepared = plan from the normal forecast; prepared = plan adjusted after testing the scenario."
      />

      <Card title="What-if configuration">
        <div className="grid gap-4 md:grid-cols-5">
          <div>
            <label className="label">Scenario</label>
            <select className="field" value={form.scenario} onChange={(e) => { setForm({ ...form, scenario: e.target.value }); setCustom(null); setAbsence(null); }}>
              {Object.entries(c.scenarios).map(([name, s]: any) => <option key={name} value={name}>{s.label}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Shift planner (DSO3)</label>
            <select className="field" value={form.plan} onChange={(e) => setForm({ ...form, plan: e.target.value })}>
              {c.plans.map((p: string) => <option key={p} value={p}>{PLAN_LABEL[p] ?? p}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Routing (DSO1)</label>
            <select className="field" value={form.router} onChange={(e) => setForm({ ...form, router: e.target.value })}>
              {c.routers.filter((r: string) => r !== "ppo" || c.ppo_available).map((r: string) => <option key={r} value={r}>{ROUTER_LABEL[r]}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Plan built from</label>
            <select className="field" value={form.prepared ? "1" : "0"} onChange={(e) => setForm({ ...form, prepared: e.target.value === "1" })}>
              <option value="1">Scenario forecast (prepared)</option>
              <option value="0">Normal forecast (unprepared)</option>
            </select>
          </div>
          <div>
            <label className="label">Seeds (replications)</label>
            <input className="field" type="number" min={1} max={30} value={form.seeds} onChange={(e) => setForm({ ...form, seeds: Number(e.target.value) })} />
          </div>
        </div>
        <p className="mt-3 text-sm text-ink2">{scenario?.description} <span className="text-muted">Week of {scenario?.week_start}.</span></p>
        <div className="mt-4 grid gap-4 md:grid-cols-5">
          {GROUPS.map((g) => (
            <div key={g}>
              <label className="label">{GROUP_LABEL[g]} ×{num(multipliers[g] ?? 1, 2)}</label>
              <input type="range" min={0.5} max={3} step={0.1} className="w-full accent-[var(--brand)]" value={multipliers[g] ?? 1}
                onChange={(e) => setCustom({ ...multipliers, [g]: Number(e.target.value) })} />
            </div>
          ))}
          <div>
            <label className="label">Absent agents {Math.round(100 * (absence ?? scenario?.absence_rate ?? 0))}%</label>
            <input type="range" min={0} max={0.5} step={0.05} className="w-full accent-[var(--brand)]" value={absence ?? scenario?.absence_rate ?? 0}
              onChange={(e) => setAbsence(Number(e.target.value))} />
          </div>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          <button className="btn btn-primary" onClick={run} disabled={!!busy}><Play size={16} /> {busy === "run" ? "Simulating…" : "Run the twin"}</button>
          <button className="btn btn-ghost" onClick={runCompare} disabled={!!busy}><Scale size={16} /> {busy === "compare" ? "Comparing…" : "Compare unprepared vs prepared vs fixed"}</button>
          {(custom || absence !== null) && <button className="btn btn-ghost" onClick={() => { setCustom(null); setAbsence(null); }}>Reset scenario</button>}
        </div>
      </Card>

      {error && <ErrorBox error={error} />}
      {busy === "run" && <Loading text="Planning shifts with CP-SAT and simulating the week" />}

      {result && (
        <>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <Pill>{result.request.seeds} seeds</Pill>
            <Pill>simulated in {num(result.elapsed_seconds, 1)} s</Pill>
            <span>Mean over seeds, [95% confidence interval].</span>
          </div>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            {TILE_KPIS.filter((k) => kpis[k]).map((k) => (
              <Stat key={k} label={kpis[k].label} value={kpiValue(k, kpis[k].mean)}
                hint={`[${kpiValue(k, kpis[k].ci_low)}, ${kpiValue(k, kpis[k].ci_high)}] · ${LOWER_IS_BETTER.has(k) ? "lower is better" : "higher is better"}`} />
            ))}
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Customers waiting (live chats), hourly mean" subtitle="Seed 0 of the run">
              <div className="h-60">
                <ResponsiveContainer>
                  <AreaChart data={queue}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="label" minTickGap={60} tickLine={false} axisLine={{ stroke: "var(--baseline)" }} />
                    <YAxis width={32} tickLine={false} axisLine={false} />
                    <Tooltip content={<ChartTooltip format={(v: number) => num(v, 1)} />} />
                    <Area dataKey="live_waiting" name="Waiting" stroke="var(--series-2)" strokeWidth={2} fill="var(--series-2)" fillOpacity={0.15} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card title="Agents on duty vs busy" action={<Legend items={[{ label: "On duty", color: "var(--series-1)" }, { label: "Busy", color: "var(--series-3)" }]} />}>
              <div className="h-60">
                <ResponsiveContainer>
                  <LineChart data={queue}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="label" minTickGap={60} tickLine={false} axisLine={{ stroke: "var(--baseline)" }} />
                    <YAxis width={32} tickLine={false} axisLine={false} />
                    <Tooltip content={<ChartTooltip format={(v: number) => num(v, 1)} />} />
                    <Line dataKey="on_duty" name="On duty" stroke="var(--series-1)" strokeWidth={2} dot={false} type="stepAfter" />
                    <Line dataKey="busy" name="Busy" stroke="var(--series-3)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>
          <Card title={`Staffing plan: ${PLAN_LABEL[result.request.plan] ?? result.request.plan}`}
            subtitle="Agents scheduled per hour (regular + overtime). A red outline marks hours below the Erlang C requirement.">
            <StaffingHeatmap rows={result.plan} value={(r) => r.regular + r.overtime} open={c.opening_hours} highlight={(r) => r.regular + r.overtime < r.required} />
          </Card>
        </>
      )}

      {compare && (
        <Card title="Same customers, four decisions" subtitle="Mean [95% CI] over seeds with common random numbers">
          <CompareTable summary={compare.summary} />
        </Card>
      )}
    </div>
  );
}

function CompareTable({ summary }: { summary: any[] }) {
  const options = Array.from(new Set(summary.map((r) => r.option)));
  const kpis = ["service_level", "abandon_rate", "asa_seconds", "understaffed_hours", "labour_cost_eur", "total_cost_eur", "overtime_hours"];
  const cell = (option: string, kpi: string) => summary.find((r) => r.option === option && r.kpi === kpi);
  return (
    <div className="overflow-x-auto">
      <table className="data">
        <thead><tr><th>KPI</th>{options.map((o) => <th key={o} className="text-right">{o}</th>)}</tr></thead>
        <tbody>
          {kpis.map((k) => (
            <tr key={k}>
              <td className="text-ink">{cell(options[0], k)?.label ?? k}</td>
              {options.map((o) => {
                const r = cell(o, k);
                return <td key={o} className="text-right">{r ? <>{kpiValue(k, r.mean)} <span className="text-xs text-muted">[{kpiValue(k, r.ci_low)}, {kpiValue(k, r.ci_high)}]</span></> : "–"}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
