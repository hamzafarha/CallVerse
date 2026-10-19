import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, ChartTooltip, ErrorBox, Legend, Loading, PageHeader, Stat } from "../components/ui";
import { useApi } from "../lib/api";
import { GROUPS, GROUP_COLOR, GROUP_LABEL, MODEL_COLOR, num, signed } from "../lib/format";

const MODELS = ["lightgbm", "seasonal_naive", "weekday_mean_4w", "sarima", "prophet"];
const MODEL_LABEL: Record<string, string> = {
  lightgbm: "LightGBM (main)",
  seasonal_naive: "Same day last week (baseline)",
  weekday_mean_4w: "4-week weekday mean",
  sarima: "SARIMA",
  prophet: "Prophet",
};

export default function ForecastPage() {
  const { data, error, loading } = useApi<any>("/api/forecast");
  if (error) return <ErrorBox error={error} />;
  if (loading || !data) return <Loading />;
  const s = data.summary;
  const series = data.total_series.map((r: any) => ({ ...r, date: String(r.date).slice(0, 10) }));
  const levels = ["total", ...GROUPS];
  const wmape: Record<string, any> = Object.fromEntries(s.wmape.map((r: any) => [r.intent_group, r]));
  const available = MODELS.filter((m) => wmape.total?.[m] !== undefined);
  const nextWeek = Object.values(
    data.next_week.reduce((acc: any, r: any) => {
      const day = String(r.date).slice(0, 10);
      acc[day] = acc[day] ?? { date: day };
      acc[day][r.intent_group] = r.contacts;
      return acc;
    }, {}),
  );
  const horizon = Object.values(
    data.by_horizon.reduce((acc: any, r: any) => {
      acc[r.horizon] = acc[r.horizon] ?? { horizon: `D+${r.horizon}` };
      acc[r.horizon][r.model] = r.wmape;
      return acc;
    }, {}),
  );
  return (
    <div className="space-y-6">
      <PageHeader
        tag="DSO4 · part 1"
        color="var(--layer-sim)"
        title="How many customers will contact us?"
        subtitle="Daily contacts per problem type, forecast 1 to 7 days ahead. Rolling-origin backtest: every Sunday from Oct 2017 to Aug 2018, each model only sees the past. Features: lagged orders, deliveries, late deliveries, overdue backlog, promotions and holidays."
      />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="LightGBM wMAPE (total)" value={`${num(s.main_wmape, 1)}%`} hint="weighted mean absolute % error" />
        <Stat label="Naive baseline wMAPE" value={`${num(s.naive_wmape, 1)}%`} hint="same day last week" />
        <Stat label="Gain vs baseline" value={signed(-s.gain_vs_naive_percent, 1)} hint={s.beats_baseline ? "error reduced: main idea kept" : "does not beat baseline"} tone={s.beats_baseline ? "good" : "bad"} />
        <Stat label="RMSE (total)" value={num(s.rmse_total, 2)} hint="contacts per day (unscaled)" />
      </div>

      <Card
        title="Actual vs forecast, total contacts per day"
        subtitle="Out-of-sample: each point was forecast 1-7 days before it happened"
        action={<Legend items={[
          { label: "Actual", color: MODEL_COLOR.actual },
          { label: "LightGBM", color: MODEL_COLOR.lightgbm },
          { label: "Same day last week", color: MODEL_COLOR.seasonal_naive, dashed: true },
        ]} />}
      >
        <div className="h-80">
          <ResponsiveContainer>
            <LineChart data={series} margin={{ right: 8, top: 8 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="date" minTickGap={50} tickLine={false} axisLine={{ stroke: "var(--baseline)" }} />
              <YAxis width={36} tickLine={false} axisLine={false} />
              <Tooltip content={<ChartTooltip format={(v: number) => num(v, 1)} />} />
              <Line dataKey="actual" name="Actual" stroke={MODEL_COLOR.actual} strokeWidth={1.5} dot={false} />
              <Line dataKey="lightgbm" name="LightGBM" stroke={MODEL_COLOR.lightgbm} strokeWidth={2} dot={false} />
              <Line dataKey="seasonal_naive" name="Same day last week" stroke={MODEL_COLOR.seasonal_naive} strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="wMAPE by level and model (%)" subtitle="Lower is better; best of each row in bold">
          <div className="overflow-x-auto">
            <table className="data">
              <thead><tr><th>Level</th>{available.map((m) => <th key={m} className="text-right">{MODEL_LABEL[m].split(" (")[0]}</th>)}</tr></thead>
              <tbody>
                {levels.filter((l) => wmape[l]).map((level) => {
                  const best = Math.min(...available.map((m) => wmape[level][m]));
                  return (
                    <tr key={level}>
                      <td className="text-ink">{level === "total" ? "Total" : GROUP_LABEL[level]}</td>
                      {available.map((m) => (
                        <td key={m} className={`text-right ${wmape[level][m] === best ? "font-bold text-ink" : ""}`}>{num(wmape[level][m], 1)}</td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-muted">Small groups are noisy (a few contacts a day): their error is close to the Poisson noise floor, so the total is the decision level.</p>
        </Card>
        <Card title="Error by forecast horizon (total)" subtitle="wMAPE % of LightGBM and the naive baseline, 1 to 7 days ahead"
          action={<Legend items={[{ label: "LightGBM", color: MODEL_COLOR.lightgbm }, { label: "Naive", color: MODEL_COLOR.seasonal_naive }]} />}>
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={horizon} barGap={2}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="horizon" tickLine={false} axisLine={{ stroke: "var(--baseline)" }} />
                <YAxis width={32} tickLine={false} axisLine={false} />
                <Tooltip content={<ChartTooltip format={(v: number) => `${num(v, 1)}%`} />} cursor={{ fill: "var(--hairline)" }} />
                <Bar dataKey="lightgbm" name="LightGBM" fill={MODEL_COLOR.lightgbm} radius={[4, 4, 0, 0]} />
                <Bar dataKey="seasonal_naive" name="Naive" fill={MODEL_COLOR.seasonal_naive} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Next week forecast" subtitle="Model retrained on all history, by problem type (contacts/day, unscaled)"
          action={<Legend items={GROUPS.map((g) => ({ label: GROUP_LABEL[g], color: GROUP_COLOR[g] }))} />}>
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={nextWeek as any[]}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="date" tickLine={false} axisLine={{ stroke: "var(--baseline)" }} tickFormatter={(d) => d.slice(5)} />
                <YAxis width={32} tickLine={false} axisLine={false} />
                <Tooltip content={<ChartTooltip format={(v: number) => num(v, 1)} />} cursor={{ fill: "var(--hairline)" }} />
                {GROUPS.map((g) => (
                  <Bar key={g} dataKey={g} name={GROUP_LABEL[g]} stackId="a" fill={GROUP_COLOR[g]} stroke="var(--surface-1)" strokeWidth={2} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="What drives the forecast" subtitle="LightGBM feature importance (share of gain)">
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={data.importance} layout="vertical" margin={{ left: 40 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="feature" width={150} tickLine={false} axisLine={false} />
                <Tooltip content={<ChartTooltip format={(v: number) => `${num(v, 1)}%`} />} cursor={{ fill: "var(--hairline)" }} />
                <Bar dataKey="gain_percent" name="Gain %" fill="var(--series-1)" radius={[0, 4, 4, 0]} barSize={14} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
    </div>
  );
}
