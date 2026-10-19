import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, ChartTooltip, ErrorBox, Legend, Loading, PageHeader, Status } from "../components/ui";
import { useApi } from "../lib/api";
import { GROUPS, GROUP_COLOR, GROUP_LABEL, num } from "../lib/format";

export default function DataPage() {
  const { data, error, loading } = useApi<any>("/api/data/summary");
  if (error) return <ErrorBox error={error} />;
  if (loading || !data) return <Loading />;
  const weekly = data.weekly.map((r: any) => ({ ...r, week: String(r.week).slice(0, 10) }));
  const groupTotals = GROUPS.map((g) => ({
    group: GROUP_LABEL[g],
    key: g,
    contacts: data.intents.filter((r: any) => r.intent_group === g).reduce((s: number, r: any) => s + r.contacts, 0),
  }));
  return (
    <div className="space-y-6">
      <PageHeader
        tag="Data layer"
        color="var(--layer-data)"
        title="From real orders to realistic contacts"
        subtitle="There are no public call-center logs, so contacts are generated from real Olist orders (late deliveries, cancellations, payment anomalies, low reviews) with explicit contact-rate assumptions, then given real customer wording from the Bitext dataset."
      />

      <Card
        title="Weekly contacts by problem type"
        subtitle="Peaks follow Black Friday and Christmas 2017 because more orders and more late deliveries create more contacts."
        action={<Legend items={GROUPS.map((g) => ({ label: GROUP_LABEL[g], color: GROUP_COLOR[g] }))} />}
      >
        <div className="h-72">
          <ResponsiveContainer>
            <AreaChart data={weekly} margin={{ left: 0, right: 8, top: 8 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="week" tickLine={false} axisLine={{ stroke: "var(--baseline)" }} minTickGap={40} />
              <YAxis tickLine={false} axisLine={false} width={40} />
              <Tooltip content={<ChartTooltip />} />
              {GROUPS.map((g) => (
                <Area key={g} type="monotone" dataKey={g} name={GROUP_LABEL[g]} stackId="1"
                  stroke="var(--surface-1)" strokeWidth={1} fill={GROUP_COLOR[g]} fillOpacity={0.9} />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Contacts per problem type">
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={groupTotals} layout="vertical" margin={{ left: 20 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="group" width={110} tickLine={false} axisLine={false} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--hairline)" }} />
                <Bar dataKey="contacts" name="Contacts" radius={[0, 4, 4, 0]} barSize={18}
                  fill="var(--series-1)" label={{ position: "right", fill: "var(--text-secondary)", fontSize: 11 }} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Time of day profile" subtitle="Share of contacts per hour (from Olist purchase hours)">
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={data.hour_profile}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="hour" tickLine={false} axisLine={{ stroke: "var(--baseline)" }} interval={2} />
                <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} width={36} tickLine={false} axisLine={false} />
                <Tooltip content={<ChartTooltip format={(v: number) => `${(v * 100).toFixed(1)}%`} />} cursor={{ fill: "var(--hairline)" }} />
                <Bar dataKey="share" name="Share" fill="var(--series-1)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Post-chat satisfaction (CSAT)" subtitle="30% of customers answer the survey">
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={data.csat}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="score" tickLine={false} axisLine={{ stroke: "var(--baseline)" }} />
                <YAxis width={40} tickLine={false} axisLine={false} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--hairline)" }} />
                <Bar dataKey="tickets" name="Tickets" fill="var(--series-1)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Why customers contact us (hidden cause)" subtitle="Order situation that generated each contact">
          <table className="data">
            <thead><tr><th>Situation</th><th className="text-right">Contacts</th></tr></thead>
            <tbody>
              {data.situations.map((r: any) => (
                <tr key={r.situation}><td className="text-ink">{r.situation.replaceAll("_", " ")}</td><td className="text-right">{num(r.contacts, 0)}</td></tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Data contracts (Pandera)" subtitle="Checked after every pipeline run, before the forecast and the twin read the data">
          <table className="data">
            <thead><tr><th>Table</th><th className="text-right">Rows</th><th>Contract</th></tr></thead>
            <tbody>
              {data.contracts.map((r: any) => (
                <tr key={r.table}><td className="text-ink">{r.table}</td><td className="text-right">{num(r.rows, 0)}</td><td><Status ok={r.passed} /></td></tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <Card title="Sample contacts" subtitle="Real Bitext wording, linked to a real Olist order">
        <div className="overflow-x-auto">
          <table className="data">
            <thead><tr><th>Contact</th><th>When</th><th>Intent</th><th>Message</th><th>Cause</th></tr></thead>
            <tbody>
              {data.sample_contacts.map((r: any) => (
                <tr key={r.contact_id}>
                  <td className="font-mono text-xs">{r.contact_id}</td>
                  <td className="whitespace-nowrap text-xs">{String(r.contact_timestamp).slice(0, 16).replace("T", " ")}</td>
                  <td className="text-xs">{r.intent}</td>
                  <td className="text-ink">{r.message_text}</td>
                  <td className="text-xs text-muted">{r.generator_situation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
