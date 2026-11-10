/**
 * Digital twin page (DSO4, part 2). Three tabs: the Live floor (one simulated day replayed contact by contact),
 * Side by side (the same day and customers under two staffing decisions, on one clock) and the Scenario lab
 * (what-if runs over several seeds, with 95% confidence intervals, and a comparison of four decisions on the
 * same customers). A Simple / Detailed switch: the simple view (components/SimpleTwin.tsx) shows what happens to
 * the customers in pictures and plain words, for a jury; the detailed view keeps the technical screens.
 */
import { Activity, Columns2, Eye, FlaskConical, Play, Scale, Wrench } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { StaffingHeatmap } from "../components/Heatmap";
import {
  type Floor,
  FloorControls,
  FloorLegend,
  LiveFloor,
  busiestHalfHour,
  hhmm,
  useFloorClock,
  waitingSeries,
} from "../components/LiveFloor";
import {
  PLAN_PLAIN,
  ROUTER_PLAIN,
  SimpleCompareResult,
  SimpleRunResult,
  SimpleSideBySide,
  SimpleSingleFloor,
  dayLabel,
  planSourcePlain,
} from "../components/SimpleTwin";
import { Card, ChartTooltip, ErrorBox, Legend, Loading, PageHeader, Pill, Segmented, Skeleton, Stat } from "@callverse/shared";
import { postJson, useApi } from "@callverse/shared";
import { DAYS, GROUPS, GROUP_LABEL, PLAN_LABEL, ROUTER_LABEL, kpiValue, num } from "@callverse/shared";

// KPIs shown as tiles after a run, and the ones where lower is better (for the hint line).
const TILE_KPIS = [
  "service_level", "abandon_rate", "asa_seconds", "understaffed_hours",
  "labour_cost_eur", "overtime_hours", "cost_per_contact_eur", "total_cost_eur",
];
const LOWER_IS_BETTER = new Set(["abandon_rate", "asa_seconds", "understaffed_hours", "labour_cost_eur",
  "overtime_hours", "cost_per_contact_eur", "total_cost_eur"]);

/**
 * The page: a header with the tab switch, then the chosen tab.
 */
const VIEW_KEY = "callverse.twin.view"; // the chosen view, remembered in this browser

export default function TwinPage() {
  const [tab, setTab] = useState<"floor" | "compare" | "lab">("floor");
  // Simple view by default (for a jury); the choice is remembered, and the page works without it.
  const [view, setView] = useState<"simple" | "detailed">(() => {
    try {
      return localStorage.getItem(VIEW_KEY) === "detailed" ? "detailed" : "simple";
    } catch {
      return "simple";
    }
  });
  const changeView = (next: "simple" | "detailed") => {
    setView(next);
    try {
      localStorage.setItem(VIEW_KEY, next);
    } catch {
      /* private window: not remembered */
    }
  };
  const simple = view === "simple";
  return (
    <div className="space-y-6">
      <PageHeader
        tag="DSO4 · part 2 — the digital twin"
        color="var(--layer-sim)"
        title="Test a decision before applying it"
        subtitle={
          simple
            ? "A virtual copy of the contact centre, fed with real customer days. Try a staffing decision here first, and see what happens to the customers before doing it for real."
            : "The twin replays a real week of contacts with Poisson arrivals, customer personas, skilled agents and abandonment. Watch one day contact by contact, or run what-if experiments over several seeds."
        }
      >
        <Segmented
          id="twin-view"
          value={view}
          onChange={changeView}
          options={[
            { value: "simple", label: <><Eye size={14} /> Simple view</> },
            { value: "detailed", label: <><Wrench size={14} /> Detailed view</> },
          ]}
        />
        <Segmented
          id="twin-tab"
          value={tab}
          onChange={setTab}
          options={[
            { value: "floor", label: <><Activity size={14} /> Live floor</> },
            { value: "compare", label: <><Columns2 size={14} /> Side by side</> },
            { value: "lab", label: <><FlaskConical size={14} /> Scenario lab</> },
          ]}
        />
      </PageHeader>
      {tab === "floor" ? <FloorPanel simple={simple} /> : tab === "compare" ? <FloorCompare simple={simple} /> : <ScenarioLab simple={simple} />}
    </div>
  );
}

/**
 * The two "Plan built from" choices. For a real historical week (reference_week set), the unprepared manager
 * copies the staffing of a normal week; otherwise it uses the normal forecast without the scenario's changes.
 */
function planSources(scenario: any): { unprepared: string; prepared: string } {
  return scenario?.reference_week
    ? { unprepared: `Copy of a normal week, ${scenario.reference_week} (unprepared)`, prepared: "Forecast of this week (prepared)" }
    : { unprepared: "Normal forecast (unprepared)", prepared: "Scenario forecast (prepared)" };
}

/** The words of the menus: plain in the simple view, technical in the detailed view. */
function words(simple: boolean, scenario: any) {
  const sources = simple ? planSourcePlain(scenario) : planSources(scenario);
  const plan = (p: string) => (simple ? PLAN_PLAIN[p] : PLAN_LABEL[p]) ?? p;
  const router = (r: string) => (simple ? ROUTER_PLAIN[r] : ROUTER_LABEL[r]) ?? r;
  return {
    plan,
    router,
    sources,
    // One decision in one line, e.g. "Optimised shifts · planned with our forecast".
    decision: (p: string, prepared: boolean, r = "fifo") =>
      `${plan(p)} · ${(prepared ? sources.prepared : sources.unprepared).toLowerCase()}${r !== "fifo" ? ` · ${router(r)}` : ""}`,
    planField: simple ? "How shifts are planned" : "Shift planner",
    routerField: simple ? "Who answers which customer" : "Routing",
    sourceField: simple ? "What the planner knew" : "Plan built from",
  };
}

/**
 * Live floor tab: choose a scenario, a day, a shift planner, a router and the forecast the plan was built
 * from; the server simulates that day and LiveFloor replays it.
 */
function FloorPanel({ simple }: { simple: boolean }) {
  const config = useApi<any>("/api/twin/config");
  const [form, setForm] = useState({ scenario: "promo_spike", plan: "cpsat", router: "fifo", day: 2, prepared: false });
  // Any change in the form changes the URL, so useApi asks the server for the new day.
  const floor = useApi<any>(
    `/api/twin/floor?scenario=${form.scenario}&plan=${form.plan}&router=${form.router}&day=${form.day}&prepared=${form.prepared}`,
  );
  const c = config.data;
  const scenario = c?.scenarios?.[form.scenario];
  const w = words(simple, scenario);
  return (
    <div className="space-y-5">
      <Card>
        <div className="grid gap-4 md:grid-cols-5">
          <div>
            <label className="label">Scenario</label>
            <select className="field" value={form.scenario} onChange={(e) => setForm({ ...form, scenario: e.target.value })}>
              {c && Object.entries(c.scenarios).map(([name, s]: any) => <option key={name} value={name}>{s.label}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Day of the week</label>
            <select className="field" value={form.day} onChange={(e) => setForm({ ...form, day: Number(e.target.value) })}>
              {DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
            </select>
          </div>
          <div>
            <label className="label">{w.planField}</label>
            <select className="field" value={form.plan} onChange={(e) => setForm({ ...form, plan: e.target.value })}>
              {(c?.plans ?? ["cpsat"]).map((p: string) => <option key={p} value={p}>{w.plan(p)}</option>)}
            </select>
          </div>
          <div>
            <label className="label">{w.routerField}</label>
            <select className="field" value={form.router} onChange={(e) => setForm({ ...form, router: e.target.value })}>
              {(c?.routers ?? ["fifo"]).filter((r: string) => r !== "ppo" || c?.ppo_available).map((r: string) => <option key={r} value={r}>{w.router(r)}</option>)}
            </select>
          </div>
          <div>
            <label className="label">{w.sourceField}</label>
            <select className="field" value={form.prepared ? "1" : "0"} onChange={(e) => setForm({ ...form, prepared: e.target.value === "1" })}>
              <option value="0">{w.sources.unprepared}</option>
              <option value="1">{w.sources.prepared}</option>
            </select>
          </div>
        </div>
        {floor.data && simple && (
          <p className="mt-3 text-sm text-ink2">
            <b className="text-ink">{floor.data.label}, {dayLabel(floor.data.date)}.</b> {scenario?.description}
          </p>
        )}
        {floor.data && !simple && (
          <p className="mt-3 text-sm text-ink2">
            {floor.data.label} · {floor.data.date} · {floor.data.summary.contacts} live contacts, {floor.data.agents.length} agents ·
            day result: service level {(floor.data.summary.service_level * 100).toFixed(1)}%, {floor.data.summary.abandoned} hung up.
          </p>
        )}
      </Card>
      {floor.error && <ErrorBox error={floor.error} />}
      {floor.loading || !floor.data ? (
        <Skeleton className="h-[560px]" />
      ) : simple ? (
        <SimpleSingleFloor floor={floor.data} decision={w.decision(form.plan, form.prepared, form.router)} />
      ) : (
        <LiveFloor floor={floor.data} />
      )}
    </div>
  );
}

/** One side of the side-by-side view: a shift planner and what its plan was built from. */
interface Side {
  plan: string;
  prepared: boolean;
}

/**
 * Side by side tab: the same day and the SAME customers (same seed: common random numbers) under two staffing
 * decisions, played on one shared clock. One floor keeps its customers while the other loses them, and the
 * cost counters show what each decision costs.
 */
function FloorCompare({ simple }: { simple: boolean }) {
  const config = useApi<any>("/api/twin/config");
  const [setup, setSetup] = useState({ scenario: "black_friday_aftermath_2017", day: 2, router: "fifo" });
  const [sides, setSides] = useState<Side[]>([
    { plan: "cpsat", prepared: false },
    { plan: "cpsat", prepared: true },
  ]);
  const c = config.data;
  // An API without this scenario yet (not restarted): fall back to the first scenario it knows.
  useEffect(() => {
    if (c && !c.scenarios[setup.scenario]) setSetup((s) => ({ ...s, scenario: Object.keys(c.scenarios)[0] }));
  }, [c, setup.scenario]);
  const url = (s: Side) =>
    `/api/twin/floor?scenario=${setup.scenario}&plan=${s.plan}&router=${setup.router}&day=${setup.day}&prepared=${s.prepared}`;
  const left = useApi<Floor>(url(sides[0]));
  const right = useApi<Floor>(url(sides[1]));
  const floors = [left.data, right.data];
  const [open, close] = left.data?.opening_hours ?? [8, 22];
  // ONE clock for both floors, so they stay in step; a new day starts again at the opening hour.
  const clock = useFloorClock(open, close);
  useEffect(() => {
    clock.restart();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [left.data, right.data]);
  // "Jump to the peak" = the busiest half hour of the two floors.
  const peakT = useMemo(() => {
    const peaks = floors.filter((f): f is Floor => !!f).map((f) => busiestHalfHour(waitingSeries(f)));
    return peaks.sort((x, y) => y.load - x.load)[0]?.t ?? open * 3600;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [left.data, right.data, open]);
  const scenario = c?.scenarios?.[setup.scenario];
  const w = words(simple, scenario);
  const sources = w.sources;
  const setSide = (i: number, change: Partial<Side>) => setSides(sides.map((s, j) => (j === i ? { ...s, ...change } : s)));
  const name = (s: Side) =>
    simple ? w.decision(s.plan, s.prepared) : `${PLAN_LABEL[s.plan] ?? s.plan} · ${s.prepared ? sources.prepared : sources.unprepared}`;
  const sideName = (i: number) => (simple ? (i === 0 ? "Left" : "Right") : i === 0 ? "A" : "B");
  // The planner and plan-source menus of one side.
  const sideMenus = (side: Side, i: number) => (
    <div className="flex flex-wrap items-end gap-3">
      <span className="flex h-8 min-w-8 items-center justify-center rounded-xl bg-raised px-2 font-display text-sm font-semibold text-brand">{sideName(i)}</span>
      <div className="min-w-[140px] flex-1">
        <label className="label">{w.planField}</label>
        <select className="field" value={side.plan} onChange={(e) => setSide(i, { plan: e.target.value })}>
          {(c?.plans ?? ["cpsat"]).map((p: string) => <option key={p} value={p}>{w.plan(p)}</option>)}
        </select>
      </div>
      <div className="min-w-[180px] flex-1">
        <label className="label">{w.sourceField}</label>
        <select className="field" value={side.prepared ? "1" : "0"} onChange={(e) => setSide(i, { prepared: e.target.value === "1" })}>
          <option value="0">{sources.unprepared}</option>
          <option value="1">{sources.prepared}</option>
        </select>
      </div>
    </div>
  );

  return (
    <div className="space-y-5">
      <Card>
        {/* What both floors share: the scenario, the day and the routing. */}
        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <label className="label">Scenario</label>
            <select className="field" value={setup.scenario} onChange={(e) => setSetup({ ...setup, scenario: e.target.value })}>
              {c && Object.entries(c.scenarios).map(([key, s]: any) => <option key={key} value={key}>{s.label}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Day of the week</label>
            <select className="field" value={setup.day} onChange={(e) => setSetup({ ...setup, day: Number(e.target.value) })}>
              {DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
            </select>
          </div>
          <div>
            <label className="label">{simple ? "Who answers which customer (both sides)" : "Routing (both floors)"}</label>
            <select className="field" value={setup.router} onChange={(e) => setSetup({ ...setup, router: e.target.value })}>
              {(c?.routers ?? ["fifo"]).filter((r: string) => r !== "ppo" || c?.ppo_available).map((r: string) => <option key={r} value={r}>{w.router(r)}</option>)}
            </select>
          </div>
        </div>
        <p className="mt-3 text-sm text-ink2">
          {simple && scenario?.description ? <><b className="text-ink">{scenario.label}.</b> {scenario.description} </> : null}
          Both sides face exactly the same customers (same arrivals, problems and patience); only the staffing decision differs.
        </p>
        {/* Simple view: the two decisions are chosen here, the pictures follow below. */}
        {simple && (
          <div className="mt-4 grid gap-4 border-t border-line pt-4 lg:grid-cols-2">
            {sides.map((side, i) => <div key={i}>{sideMenus(side, i)}</div>)}
          </div>
        )}
      </Card>

      {simple && (left.error || right.error) && <ErrorBox error={(left.error ?? right.error) as string} />}
      {simple &&
        (left.data && right.data && !left.loading && !right.loading ? (
          <SimpleSideBySide left={left.data} right={right.data} leftName={name(sides[0])} rightName={name(sides[1])} clock={clock} peakT={peakT} />
        ) : (
          !(left.error || right.error) && <Skeleton className="h-[520px]" />
        ))}

      {/* Detailed view: one set of controls for both floors, and the two animated floors. */}
      {!simple && <>
      <div className="flex flex-wrap items-center gap-4">
        <div className="font-display text-3xl font-semibold tabular text-ink">{hhmm(clock.t)}</div>
        <div className="min-w-[320px] flex-1">
          <FloorControls clock={clock} peakT={peakT} />
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        {sides.map((side, i) => {
          const result = i === 0 ? left : right;
          const title = sideMenus(side, i);
          if (result.error) return <div key={i} className="space-y-3">{title}<ErrorBox error={result.error} /></div>;
          if (!result.data || result.loading) return <div key={i} className="space-y-3">{title}<Skeleton className="h-[460px]" /></div>;
          return <LiveFloor key={i} floor={result.data} clock={clock} compact title={title} />;
        })}
      </div>
      <FloorLegend threshold={left.data?.threshold_seconds ?? 20} />
      </>}

      {/* The whole day, decided: what each decision gives and costs. */}
      {left.data && right.data && (
        <Card title="The whole day" subtitle={`${left.data.label} · ${left.data.date} · ${left.data.summary.contacts} live customers on both floors`}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-muted">
                  <th className="py-2 pr-4 font-semibold">Decision</th>
                  <th className="py-2 pr-4 font-semibold">On time</th>
                  <th className="py-2 pr-4 font-semibold">Hung up</th>
                  <th className="py-2 pr-4 font-semibold">Agent hours</th>
                  <th className="py-2 font-semibold">Cost (wages + lost customers)</th>
                </tr>
              </thead>
              <tbody>
                {[left.data, right.data].map((f, i) => (
                  <tr key={i} className="border-t border-line">
                    <td className="py-2 pr-4 text-ink"><b>{sideName(i)}</b> · {name(sides[i])}</td>
                    <td className="py-2 pr-4 tabular" style={{ color: f.summary.service_level < 0.8 ? "var(--critical)" : "var(--good-text)" }}>{(f.summary.service_level * 100).toFixed(0)}%</td>
                    <td className="py-2 pr-4 tabular">{num(f.summary.abandoned, 0)}</td>
                    <td className="py-2 pr-4 tabular">{f.summary.agent_hours ?? "–"}</td>
                    <td className="py-2 tabular">{f.summary.cost_eur == null ? "–" : `€${num(f.summary.cost_eur, 0)}`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {left.data.summary.cost_eur != null && right.data.summary.cost_eur != null && (
            <p className="mt-3 text-sm text-ink2">
              {simple ? "The right side" : "B"} {left.data.summary.abandoned >= right.data.summary.abandoned ? "keeps" : "loses"}{" "}
              <b className="text-ink">{num(Math.abs(left.data.summary.abandoned - right.data.summary.abandoned), 0)}</b> more customers than{" "}
              {simple ? "the left side" : "A"}, and the day costs{" "}
              <b className="text-ink">€{num(Math.abs(left.data.summary.cost_eur - right.data.summary.cost_eur), 0)} {right.data.summary.cost_eur <= left.data.summary.cost_eur ? "less" : "more"}</b>.
            </p>
          )}
        </Card>
      )}
    </div>
  );
}

/**
 * Scenario lab tab: run the twin with one configuration (POST /api/twin/run) or compare four decisions (POST
 * /api/twin/compare).
 */
function ScenarioLab({ simple }: { simple: boolean }) {
  const config = useApi<any>("/api/twin/config");
  const [form, setForm] = useState<any>({ scenario: "promo_spike", plan: "cpsat", router: "fifo", seeds: 5, prepared: true });
  // custom = what-if volume multipliers per problem group; absence = share of absent agents. null means "use
  // the scenario's own values".
  const [custom, setCustom] = useState<Record<string, number> | null>(null);
  const [absence, setAbsence] = useState<number | null>(null);
  const [result, setResult] = useState<any>(null);
  const [compare, setCompare] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const scenario = config.data?.scenarios?.[form.scenario];
  const multipliers = custom ?? scenario?.multipliers ?? {};

  // Run one configuration over several seeds: the result has the mean and 95% CI of each KPI, the hourly
  // queue and the staffing plan.
  const run = async () => {
    setBusy("run"); setError(null);
    try {
      setResult(await postJson("/api/twin/run", { ...form, multipliers: custom ?? undefined, absence_rate: absence ?? undefined }));
    } catch (e: any) { setError(e.message); } finally { setBusy(null); }
  };
  // Same scenario and seeds for four options (common random numbers): unprepared vs prepared CP-SAT, fixed
  // shifts, and PPO (or the skill-score router if no PPO model is trained).
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

  // KPIs by name, and the hourly queue with a readable label (e.g. "Mon 14h").
  const kpis: Record<string, any> = useMemo(
    () => Object.fromEntries((result?.kpis ?? []).map((k: any) => [k.kpi, k])), [result]);
  const queue = (result?.queue ?? []).map((r: any) => ({
    ...r, label: `${DAYS[Math.floor(r.hour_index / 24) % 7]} ${r.hour_index % 24}h`,
  }));

  if (config.error) return <ErrorBox error={config.error} />;
  if (!config.data) return <Loading />;
  const c = config.data;
  const w = words(simple, scenario);
  return (
    <div className="space-y-6">
      <Card title={simple ? "Try a decision on a simulated week" : "What-if configuration"}>
        <div className="grid gap-4 md:grid-cols-5">
          <div>
            <label className="label">Scenario</label>
            <select className="field" value={form.scenario} onChange={(e) => { setForm({ ...form, scenario: e.target.value }); setCustom(null); setAbsence(null); }}>
              {Object.entries(c.scenarios).map(([name, s]: any) => <option key={name} value={name}>{s.label}</option>)}
            </select>
          </div>
          <div>
            <label className="label">{simple ? w.planField : "Shift planner (DSO3)"}</label>
            <select className="field" value={form.plan} onChange={(e) => setForm({ ...form, plan: e.target.value })}>
              {c.plans.map((p: string) => <option key={p} value={p}>{w.plan(p)}</option>)}
            </select>
          </div>
          <div>
            <label className="label">{simple ? w.routerField : "Routing (DSO1)"}</label>
            <select className="field" value={form.router} onChange={(e) => setForm({ ...form, router: e.target.value })}>
              {c.routers.filter((r: string) => r !== "ppo" || c.ppo_available).map((r: string) => <option key={r} value={r}>{w.router(r)}</option>)}
            </select>
          </div>
          <div>
            <label className="label">{w.sourceField}</label>
            <select className="field" value={form.prepared ? "1" : "0"} onChange={(e) => setForm({ ...form, prepared: e.target.value === "1" })}>
              <option value="1">{w.sources.prepared}</option>
              <option value="0">{w.sources.unprepared}</option>
            </select>
          </div>
          <div>
            <label className="label">{simple ? "Simulated weeks (repeats)" : "Seeds (replications)"}</label>
            <input className="field" type="number" min={1} max={30} value={form.seeds} onChange={(e) => setForm({ ...form, seeds: Number(e.target.value) })} />
          </div>
        </div>
        <p className="mt-3 text-sm text-ink2">{scenario?.description} <span className="text-muted">Week of {scenario?.week_start}.</span></p>
        {/* What-if sliders (detailed view): volume multiplier per problem group (x0.5 to x3), and the share of
           absent agents. */}
        {!simple && <div className="mt-4 grid gap-4 md:grid-cols-5">
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
        </div>}
        {/* Run, compare, or go back to the scenario's own values. */}
        <div className="mt-5 flex flex-wrap gap-2">
          <button className="btn btn-primary" onClick={run} disabled={!!busy}><Play size={16} /> {busy === "run" ? "Simulating…" : simple ? "Simulate the week" : "Run the twin"}</button>
          <button className="btn btn-ghost" onClick={runCompare} disabled={!!busy}><Scale size={16} /> {busy === "compare" ? "Comparing…" : simple ? "Compare 4 decisions" : "Compare unprepared vs prepared vs fixed"}</button>
          {(custom || absence !== null) && <button className="btn btn-ghost" onClick={() => { setCustom(null); setAbsence(null); }}>Reset scenario</button>}
        </div>
      </Card>

      {error && <ErrorBox error={error} />}
      {busy === "run" && <Loading text={simple ? "Planning the shifts and simulating the week" : "Planning shifts with CP-SAT and simulating the week"} />}

      {/* Simple view: out of 100 customers, and the cost of the week. */}
      {result && simple && (
        <SimpleRunResult
          kpis={kpis}
          seeds={result.request.seeds}
          decision={w.decision(result.request.plan, result.request.prepared, result.request.router)}
        />
      )}

      {result && !simple && (
        <>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <Pill>{result.request.seeds} seeds</Pill>
            <Pill>simulated in {num(result.elapsed_seconds, 1)} s</Pill>
            <span>Mean over seeds, [95% confidence interval].</span>
          </div>
          {/* KPI tiles: mean over the seeds, with the 95% confidence interval under it. */}
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
            <Card title="Agents available vs busy" action={<Legend items={[{ label: "Available", color: "var(--series-1)" }, { label: "Busy", color: "var(--series-3)" }]} />}>
              <div className="h-60">
                <ResponsiveContainer>
                  <LineChart data={queue}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="label" minTickGap={60} tickLine={false} axisLine={{ stroke: "var(--baseline)" }} />
                    <YAxis width={32} tickLine={false} axisLine={false} />
                    <Tooltip content={<ChartTooltip format={(v: number) => num(v, 1)} />} />
                    <Line dataKey="on_duty" name="Available" stroke="var(--series-1)" strokeWidth={2} dot={false} type="stepAfter" />
                    <Line dataKey="busy" name="Busy" stroke="var(--series-3)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>
          {/* The staffing plan used, as a day x hour heatmap (red outline = below the Erlang C
             requirement). */}
          <Card title={`Staffing plan: ${PLAN_LABEL[result.request.plan] ?? result.request.plan}`}
            subtitle="Agents scheduled per hour (regular + overtime). A red outline marks hours below the Erlang C requirement.">
            <StaffingHeatmap rows={result.plan} value={(r) => r.regular + r.overtime} open={c.opening_hours} highlight={(r) => r.regular + r.overtime < r.required} />
          </Card>
        </>
      )}

      {compare && simple && <SimpleCompareResult summary={compare.summary} scenario={scenario} />}
      {compare && !simple && (
        <Card title="Same customers, four decisions" subtitle="Mean [95% CI] over seeds with common random numbers">
          <CompareTable summary={compare.summary} />
        </Card>
      )}
    </div>
  );
}

/**
 * Comparison table: one column per option, one row per KPI, mean [95% CI].
 */
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
