import { ExternalLink } from "lucide-react";
import { Card, ErrorBox, Loading, PageHeader, Pill } from "../components/ui";
import { useApi } from "../lib/api";
import { num, pct } from "../lib/format";

const STACK = [
  { name: "FastAPI", text: "REST + WebSocket API for the twin and the agents; Pydantic request/response models; uvicorn." },
  { name: "React control room", text: "Vite + React + TypeScript + Tailwind + Recharts; live KPIs, what-if picker, agent playground, labeling." },
  { name: "Docker Compose", text: "One-command deploy: api, ui (nginx), mlflow (+ postgres); .env pins model versions and seeds." },
  { name: "MLflow", text: "Experiment tracking: forecast backtests, PPO runs, evaluation suites; params, metrics and artifacts per seed." },
  { name: "LLM tracing", text: "Every agent call traced (tokens, latency, cache, tools) to JSONL; Langfuse when keys are set." },
  { name: "GitHub Actions", text: "Versioned, tested builds: ruff, import-linter, pytest (env, forecast, KPI engine, API), frontend build." },
];

export default function MlopsPage() {
  const { data, error, loading } = useApi<any>("/api/mlops");
  if (error) return <ErrorBox error={error} />;
  if (loading || !data) return <Loading />;
  return (
    <div className="space-y-6">
      <PageHeader tag="Serving & MLOps" color="var(--layer-serve)" title="Reproducible, tracked, deployable"
        subtitle="Pinned model versions, fixed seeds, every run tracked. The MLflow UI runs on port 5000 (`mlflow ui` or Docker Compose).">
        <a className="btn btn-ghost" href="http://localhost:5000" target="_blank" rel="noreferrer"><ExternalLink size={15} /> Open MLflow</a>
        <a className="btn btn-ghost" href="/docs" target="_blank" rel="noreferrer"><ExternalLink size={15} /> API docs</a>
      </PageHeader>
      <div className="grid gap-4 md:grid-cols-3">
        {STACK.map((s) => (
          <div key={s.name} className="card p-4">
            <div className="text-sm font-semibold text-ink">{s.name}</div>
            <p className="mt-1 text-xs text-ink2">{s.text}</p>
          </div>
        ))}
      </div>
      <Card title="LLM tracing by agent" subtitle="From artifacts/traces/llm_calls.jsonl (local models: no per-token cost)">
        {data.llm_by_agent.length ? (
          <table className="data">
            <thead><tr><th>Agent</th><th className="text-right">Calls</th><th className="text-right">Cache hits</th><th className="text-right">Mean latency</th><th className="text-right">Prompt tokens</th><th className="text-right">Completion tokens</th></tr></thead>
            <tbody>
              {data.llm_by_agent.map((r: any) => (
                <tr key={r.agent}><td className="text-ink">{r.agent}</td><td className="text-right">{num(r.calls, 0)}</td><td className="text-right">{pct(r.cached_share, 0)}</td><td className="text-right">{num(r.mean_latency_ms / 1000, 1)} s</td><td className="text-right">{num(r.prompt_tokens, 0)}</td><td className="text-right">{num(r.completion_tokens, 0)}</td></tr>
              ))}
            </tbody>
          </table>
        ) : <div className="text-sm text-muted">No LLM call traced yet: run a conversation with the local LLMs.</div>}
      </Card>
      {data.model_lock && (
        <Card title="Pinned models" subtitle="artifacts/traces/llm_models.lock.json (`callverse llm-pin`)">
          <div className="flex flex-wrap gap-2">
            {Object.entries(data.model_lock).map(([role, m]: any) => (
              <Pill key={role}>{role}: {m.resolved} · {m.family} {m.parameters} {m.quantization} · {String(m.digest ?? "").slice(0, 12)}</Pill>
            ))}
          </div>
        </Card>
      )}
      <Card title="MLflow runs" subtitle={data.mlflow_uri}>
        <div className="max-h-[480px] overflow-auto">
          <table className="data">
            <thead><tr><th>Experiment</th><th>Run</th><th>Started</th><th>Key metrics</th></tr></thead>
            <tbody>
              {data.runs.map((r: any) => (
                <tr key={r.run_id}>
                  <td className="text-xs text-ink">{r.experiment}</td><td className="text-xs">{r.run_name}</td>
                  <td className="whitespace-nowrap text-xs">{new Date(r.start_time).toLocaleString()}</td>
                  <td className="text-xs text-muted">{Object.entries(r.metrics).slice(0, 4).map(([k, v]) => `${k}=${num(v, 3)}`).join(" · ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card title="Artifacts" subtitle="Models, forecasts and evaluation tables written by the pipeline">
        <div className="grid gap-x-6 md:grid-cols-2">
          {data.artifacts.map((a: any) => (
            <div key={a.folder + a.file} className="flex justify-between border-b border-line py-1.5 text-xs">
              <span className="text-ink2"><span className="text-muted">{a.folder}/</span>{a.file}</span><span className="tabular text-muted">{num(a.size_kb, 0)} KB</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
