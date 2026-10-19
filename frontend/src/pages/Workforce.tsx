import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ErrorBar, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { StaffingHeatmap } from "../components/Heatmap";
import { Card, ChartTooltip, ErrorBox, Loading, PageHeader, Pill, Stat, Status } from "../components/ui";
import { useApi } from "../lib/api";
import { DAYS, PLAN_LABEL, ROUTER_COLOR, ROUTER_LABEL, eur, kpiValue, num, signed } from "../lib/format";

export default function WorkforcePage() {
  const [tab, setTab] = useState<"schedule" | "routing">("schedule");
  return (
    <div className="space-y-6">
      <PageHeader
        tag="Workforce agent · DSO1 + DSO3"
        color="var(--layer-agents)"
        title="Who works when, and who takes which customer"
        subtitle="One manager agent, two jobs: plan shifts and overtime for the week from the forecast (OR-Tools CP-SAT), and route each waiting customer to an advisor in real time (MaskablePPO trained in the twin)."
      >
        <button className={`btn ${tab === "schedule" ? "btn-primary" : "btn-ghost"}`} onClick={() => setTab("schedule")}>Shift planning</button>
        <button className={`btn ${tab === "routing" ? "btn-primary" : "btn-ghost"}`} onClick={() => setTab("routing")}>Real-time routing</button>
      </PageHeader>
      {tab === "schedule" ? <Schedule /> : <Routing />}
    </div>
  );
}

function Schedule() {
  const [scenario, setScenario] = useState("baseline");
  const [planner, setPlanner] = useState("cpsat");
  const [prepared, setPrepared] = useState(true);
  const config = useApi<any>("/api/twin/config");
  const { data, error, loading } = useApi<any>(`/api/workforce/schedule?scenario=${scenario}&planner=${planner}&prepared=${prepared}`);
  const roster = data?.roster ?? [];
  const agents = Array.from(new Set(roster.map((r: any) => r.agent_id))) as number[];
  return (
    <>
      <Card title="Plan a week">
        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <label className="label">Scenario week</label>
            <select className="field" value={scenario} onChange={(e) => setScenario(e.target.value)}>
              {Object.entries(config.data?.scenarios ?? { baseline: { label: "Normal week" } }).map(([n, s]: any) => <option key={n} value={n}>{s.label}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Planner</label>
            <select className="field" value={planner} onChange={(e) => setPlanner(e.target.value)}>
              {Object.entries(PLAN_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Demand used</label>
            <select className="field" value={prepared ? "1" : "0"} onChange={(e) => setPrepared(e.target.value === "1")}>
              <option value="1">Scenario-adjusted forecast</option>
              <option value="0">Normal forecast</option>
            </select>
          </div>
        </div>
      </Card>
      {error && <ErrorBox error={error} />}
      {loading && <Loading text="Solving" />}
      {data && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
            <Stat label="Planned cost" value={eur(data.costs.planned_cost_eur)} hint="regular + 1.5× overtime" />
            <Stat label="Regular hours" value={num(data.costs.planned_regular_hours, 0)} />
            <Stat label="Overtime hours" value={num(data.costs.planned_overtime_hours, 0)} />
            <Stat label="Understaffed hours" value={num(data.costs.planned_understaffed_hours, 0)} hint="vs Erlang C requirement" tone={data.costs.planned_understaffed_hours ? "bad" : "good"} />
            <Stat label="Headcount" value={num(data.costs.headcount, 0)} hint={data.status !== "ok" ? `CP-SAT ${data.status} in ${num(data.solve_seconds, 1)} s` : undefined} />
          </div>
          {data.compliance && (
            <Card title="Labour rules" subtitle="Hard constraints of the CP-SAT roster">
              <div className="flex flex-wrap gap-4">
                <Status ok={data.compliance.max_days} label="≤ 5 days / week" />
                <Status ok={data.compliance.max_hours} label="≤ 40 h / week" />
                <Status ok={data.compliance.one_shift_per_day} label="1 shift per day" />
                <Status ok={data.compliance.min_rest} label="≥ 11 h rest" />
              </div>
            </Card>
          )}
          <div className="grid gap-6 xl:grid-cols-2">
            <Card title="Required agents (Erlang C on the forecast)" subtitle="80% of chats answered within 20 s, occupancy ≤ 90%">
              <StaffingHeatmap rows={data.plan} value={(r) => r.required} />
            </Card>
            <Card title="Scheduled agents (regular + overtime)" subtitle="Red outline: below the requirement">
              <StaffingHeatmap rows={data.plan} value={(r) => r.regular + r.overtime} highlight={(r) => r.regular + r.overtime < r.required} />
            </Card>
          </div>
          {roster.length > 0 && (
            <Card title="Roster" subtitle={`${agents.length} agents, shifts of 4, 6 or 8 hours`}>
              <div className="max-h-96 overflow-auto">
                <table className="data">
                  <thead><tr><th>Agent</th>{DAYS.map((d) => <th key={d}>{d}</th>)}<th className="text-right">Hours</th></tr></thead>
                  <tbody>
                    {agents.map((a) => {
                      const shifts = roster.filter((r: any) => r.agent_id === a);
                      return (
                        <tr key={a}>
                          <td className="font-mono text-xs">A{String(a).padStart(2, "0")}</td>
                          {DAYS.map((_, day) => {
                            const s = shifts.find((r: any) => r.day === day);
                            return <td key={day} className="text-xs">{s ? `${s.start_hour}–${s.end_hour}` : <span className="text-muted">off</span>}</td>;
                          })}
                          <td className="text-right">{shifts.reduce((t: number, r: any) => t + r.hours, 0)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </>
  );
}

function Routing() {
  const { data, error, loading } = useApi<any>("/api/workforce/routing");
  if (error) return <ErrorBox error={error} />;
  if (loading || !data) return <Loading />;
  const comparison = data.comparison ?? [];
  const routers = Array.from(new Set(comparison.map((r: any) => r.router))) as string[];
  const bars = (kpi: string) => routers.map((router) => {
    const row = comparison.find((r: any) => r.router === router && r.kpi === kpi) ?? {};
    return { router: ROUTER_LABEL[router] ?? router, key: router, mean: row.mean,
      err: row.router === "fifo" ? 0 : Math.abs((row.ci_high - row.ci_low) / 2), change: row.relative_change_percent };
  });
  return (
    <>
      <Card title="How the routing agent decides" subtitle="State → action → reward, trained only in the simulated center (no LLM calls)">
        <div className="grid gap-3 text-sm md:grid-cols-3">
          <div className="rounded-xl border border-line p-3"><b className="text-ink">State</b><p className="mt-1 text-ink2">The 10 oldest waiting customers (wait, problem type, persona, live or overnight) and how fast the free advisor is on each problem; queue length, staff on duty, time of day.</p></div>
          <div className="rounded-xl border border-line p-3"><b className="text-ink">Action</b><p className="mt-1 text-ink2">Which waiting customer the free advisor takes (invalid slots masked: MaskablePPO).</p></div>
          <div className="rounded-xl border border-line p-3"><b className="text-ink">Reward</b><p className="mt-1 text-ink2">− customer-seconds of waiting − 10 min per abandonment. Minimising total wait = minimising average wait (Little's law).</p></div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          <span className="text-muted">Backup skill-score weights (random search in the twin):</span>
          {Object.entries(data.skill_weights ?? {}).map(([k, v]) => <Pill key={k}>{k}: {num(v, 2)}</Pill>)}
        </div>
      </Card>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Average wait to answer (ASA)" subtitle="Unseen stressed days (load ×1.6, 15% absent); error bars: 95% CI of the paired difference">
          <RouterBars data={bars("asa_seconds")} unit="s" />
        </Card>
        <Card title="Abandon rate" subtitle="Same days, same customers for every router">
          <RouterBars data={bars("abandon_rate")} unit="%" scale={100} />
        </Card>
      </div>
      <Card title="Router comparison vs FIFO" subtitle="Paired over test days and seeds">
        <table className="data">
          <thead><tr><th>Router</th><th>KPI</th><th className="text-right">Mean</th><th className="text-right">vs FIFO</th><th className="text-right">95% CI of difference</th></tr></thead>
          <tbody>
            {comparison.filter((r: any) => r.router !== "fifo" && ["asa_seconds", "abandon_rate", "service_level", "mean_wait_all_live_seconds"].includes(r.kpi)).map((r: any) => (
              <tr key={r.router + r.kpi}>
                <td className="text-ink">{ROUTER_LABEL[r.router]}</td><td>{r.kpi}</td>
                <td className="text-right">{kpiValue(r.kpi, r.mean)}</td>
                <td className="text-right font-medium">{signed(r.relative_change_percent, 1)}</td>
                <td className="text-right text-xs text-muted">[{num(r.ci_low, 3)}, {num(r.ci_high, 3)}]</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card title="PPO learning curve" subtitle="Episode reward (one simulated busy day per episode), rolling mean of 50 episodes">
        <div className="h-64">
          <ResponsiveContainer>
            <LineChart data={data.training_curve}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="episode" tickLine={false} axisLine={{ stroke: "var(--baseline)" }} minTickGap={50} />
              <YAxis width={40} tickLine={false} axisLine={false} />
              <Tooltip content={<ChartTooltip format={(v: number) => num(v, 1)} />} />
              <Line dataKey="reward_rolling" name="Reward (rolling)" stroke="var(--series-3)" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </>
  );
}

function RouterBars({ data, unit, scale = 1 }: { data: any[]; unit: string; scale?: number }) {
  const scaled = data.map((d) => ({ ...d, mean: d.mean * scale, err: d.err * scale }));
  return (
    <div className="h-56">
      <ResponsiveContainer>
        <BarChart data={scaled} margin={{ top: 16 }}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey="router" tickLine={false} axisLine={{ stroke: "var(--baseline)" }} />
          <YAxis width={36} tickLine={false} axisLine={false} />
          <Tooltip content={<ChartTooltip format={(v: number) => `${num(v, 2)} ${unit}`} />} cursor={{ fill: "var(--hairline)" }} />
          <Bar dataKey="mean" name="Mean" radius={[4, 4, 0, 0]} barSize={48}
            shape={(props: any) => <rect {...props} fill={ROUTER_COLOR[props.payload.key]} rx={4} />}>
            <ErrorBar dataKey="err" stroke="var(--text-secondary)" width={6} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
