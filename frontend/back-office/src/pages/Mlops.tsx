import {
  Bar as Meter,
  Card,
  ChartTooltip,
  ErrorBox,
  PageHeader,
  PageSkeleton,
  Pill,
  Reveal,
  Ring,
  Stagger,
  StaggerItem,
  Status,
  num,
  pct,
  postJson,
  useApi,
} from "@callverse/shared";
import { Boxes, Container, Cpu, ExternalLink, FlaskConical, GitBranch, Loader2, Rocket, ScrollText, Server, Zap } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

const STACK = [
  { icon: Server, name: "FastAPI", text: "REST + WebSocket API shared by both apps; Pydantic models; live agent sessions streamed token by token." },
  { icon: Boxes, name: "Front + back office", text: "Two React apps (Vite, TypeScript, Tailwind, Framer Motion) on one shared design system (npm workspaces)." },
  { icon: Cpu, name: "Hugging Face", text: "transformers + bitsandbytes 4-bit: SmolLM3-3B advisor/client, Granite-4.0-1B judge, bge-m3 embeddings. Commits pinned." },
  { icon: FlaskConical, name: "MLflow", text: "Forecast backtests, PPO runs and evaluation suites: params, metrics and artifacts per seed." },
  { icon: ScrollText, name: "LLM tracing", text: "Every agent call traced (tokens, latency, tokens/s, cache, tools) to JSONL; Langfuse when keys are set." },
  { icon: Container, name: "Docker + CI", text: "Compose: api, front office, back office (nginx), MLflow + Postgres. GitHub Actions: ruff, import-linter, pytest, both builds." },
];

const ROLE_TEXT: Record<string, string> = {
  advisor: "Answers customers (RAG + tools + rules engine)",
  client: "Plays the customer in the twin",
  judge: "Grades every conversation (different family)",
};

export default function MlopsPage() {
  const { data, error } = useApi<any>("/api/mlops");
  const system = useApi<any>("/api/system");
  const [warming, setWarming] = useState(false);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <PageSkeleton />;
  const llm = system.data?.llm;
  const gpu = llm?.gpu;

  const warmup = async () => {
    setWarming(true);
    const id = toast.loading("Loading the models on the GPU…");
    try {
      await postJson("/api/system/warmup");
      toast.success("Models loaded: the first chat answers at full speed", { id });
      system.reload();
    } catch (e: any) {
      toast.error(e.message, { id });
    } finally {
      setWarming(false);
    }
  };
  const latency = (data.llm_by_agent ?? []).map((r: any) => ({ ...r, seconds: r.mean_latency_ms / 1000 }));

  return (
    <div className="space-y-8">
      <PageHeader
        tag="Serving & MLOps"
        color="var(--layer-serve)"
        title="Reproducible, tracked, deployable"
        subtitle="Open-weight models pinned to a commit, fixed seeds, every run tracked and every LLM call traced."
      >
        <button className="btn btn-primary" onClick={warmup} disabled={warming || !system.data?.llm_available}>
          {warming ? <Loader2 size={15} className="animate-spin" /> : <Zap size={15} />} Load models on GPU
        </button>
        <a className="btn btn-ghost" href="http://localhost:5000" target="_blank" rel="noreferrer">
          <ExternalLink size={15} /> MLflow
        </a>
        <a className="btn btn-ghost" href="/docs" target="_blank" rel="noreferrer">
          <ExternalLink size={15} /> API docs
        </a>
      </PageHeader>

      {/* models */}
      <section>
        <Reveal>
          <h2 className="mb-1 text-xl font-semibold text-ink">Agent models · Hugging Face Hub</h2>
          <p className="mb-4 text-sm text-muted">
            {llm?.provider} · profile <b>{llm?.profile}</b> · {system.data?.llm_available ? "ready" : llm?.reason ?? "checking…"}
          </p>
        </Reveal>
        <div className="grid gap-4 lg:grid-cols-[1fr_1fr_1fr_280px]">
          {llm &&
            Object.entries(llm.roles).map(([role, m]: any, i: number) => (
              <Reveal key={role} delay={i * 0.06}>
                <div className="card card-hover h-full p-5">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">{role}</span>
                    <Status ok={m.loaded ? true : m.downloaded ? null : false} label={m.loaded ? `loaded · ${m.device}` : m.downloaded ? "downloaded" : "not downloaded"} />
                  </div>
                  <a
                    href={`https://huggingface.co/${m.base_model}`}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-3 flex items-center gap-2 font-semibold text-ink hover:text-brand"
                  >
                    <span className="text-xl" aria-hidden>
                      🤗
                    </span>
                    <span className="truncate">{String(m.base_model).split("/").pop()}</span>
                    <ExternalLink size={12} className="shrink-0 text-muted" />
                  </a>
                  <div className="mt-1 text-xs text-ink2">{ROLE_TEXT[role]}</div>
                  <div className="mt-4 flex flex-wrap gap-1.5">
                    <Pill>{m.family}</Pill>
                    <Pill>{m.parameters} params</Pill>
                    <Pill>{m.license}</Pill>
                  </div>
                  <div className="mt-4 space-y-1.5 text-[11px] text-muted">
                    <div className="truncate font-mono">repo {m.pinned}</div>
                    <div className="flex items-center gap-1 font-mono">
                      <GitBranch size={11} /> {m.revision ? String(m.revision).slice(0, 12) : "latest cached snapshot"}
                    </div>
                    <div>{m.quantization}</div>
                  </div>
                  {m.footprint_mb && (
                    <div className="mt-3">
                      <div className="mb-1 flex justify-between text-[11px] text-muted">
                        <span>VRAM</span>
                        <span>{(m.footprint_mb / 1024).toFixed(2)} GB</span>
                      </div>
                      <Meter value={m.footprint_mb / (gpu?.total_mb ?? 4096)} />
                    </div>
                  )}
                </div>
              </Reveal>
            ))}
          <Card title="GPU" icon={<Cpu size={16} />}>
            {gpu ? (
              <div className="flex flex-col items-center text-center">
                <Ring value={gpu.used_mb / gpu.total_mb} size={120} stroke={10} color="var(--brand)">
                  <div>
                    <div className="font-display text-2xl font-bold text-ink">{(gpu.used_mb / 1024).toFixed(1)}</div>
                    <div className="text-[10px] text-muted">of {(gpu.total_mb / 1024).toFixed(1)} GB</div>
                  </div>
                </Ring>
                <div className="mt-3 text-sm font-medium text-ink">{gpu.name}</div>
                <div className="text-xs text-muted">CUDA {gpu.torch_cuda} · 4-bit NF4 weights, bf16 compute</div>
              </div>
            ) : (
              <p className="text-sm text-muted">No CUDA GPU visible: agents use their offline backups.</p>
            )}
          </Card>
        </div>
      </section>

      <Stagger className="grid gap-4 md:grid-cols-3">
        {STACK.map((s) => (
          <StaggerItem key={s.name} className="card card-hover p-5">
            <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--brand-soft)] text-brand">
              <s.icon size={17} />
            </div>
            <div className="text-sm font-semibold text-ink">{s.name}</div>
            <p className="mt-1 text-xs leading-relaxed text-ink2">{s.text}</p>
          </StaggerItem>
        ))}
      </Stagger>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="LLM tracing by agent" subtitle="artifacts/traces/llm_calls.jsonl · local models: no per-token cost">
          {data.llm_by_agent.length ? (
            <>
              <div className="h-44">
                <ResponsiveContainer>
                  <BarChart data={latency}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="agent" tickLine={false} axisLine={{ stroke: "var(--baseline)" }} />
                    <YAxis width={36} tickLine={false} axisLine={false} unit="s" />
                    <Tooltip content={<ChartTooltip format={(v: number) => `${num(v, 1)} s`} />} cursor={{ fill: "var(--hairline)" }} />
                    <Bar dataKey="seconds" name="Mean latency" fill="var(--brand)" radius={[6, 6, 0, 0]} barSize={36} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <table className="data mt-3">
                <thead>
                  <tr>
                    <th>Agent</th>
                    <th className="text-right">Calls</th>
                    <th className="text-right">Cache hits</th>
                    <th className="text-right">Prompt tok.</th>
                    <th className="text-right">Completion tok.</th>
                  </tr>
                </thead>
                <tbody>
                  {data.llm_by_agent.map((r: any) => (
                    <tr key={r.agent}>
                      <td className="text-ink">{r.agent}</td>
                      <td className="text-right">{num(r.calls, 0)}</td>
                      <td className="text-right">{pct(r.cached_share, 0)}</td>
                      <td className="text-right">{num(r.prompt_tokens, 0)}</td>
                      <td className="text-right">{num(r.completion_tokens, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : (
            <div className="text-sm text-muted">No LLM call traced yet: run a conversation with the local LLMs.</div>
          )}
        </Card>
        <Card title="Latest LLM calls" subtitle="Newest first">
          <div className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
            {[...(data.llm_recent ?? [])].reverse().map((r: any, i: number) => (
              <div key={i} className="rounded-xl border border-line p-3 text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-semibold capitalize text-ink">{r.agent}</span>
                  <span className="font-mono text-muted">{String(r.model ?? "").split("/").pop()}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-3 text-muted">
                  <span>{num((r.latency_ms ?? 0) / 1000, 1)} s</span>
                  <span>
                    {num(r.prompt_tokens, 0)} → {num(r.completion_tokens, 0)} tok
                  </span>
                  {r.tokens_per_second && <span>{num(r.tokens_per_second, 1)} tok/s</span>}
                  {r.cached && <span className="text-brand">cache hit</span>}
                  {r.error && <span className="text-bad">error</span>}
                </div>
                {r.output_preview && <p className="mt-1.5 line-clamp-2 text-ink2">{r.output_preview}</p>}
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card title="MLflow runs" subtitle={data.mlflow_uri} icon={<Rocket size={16} />}>
        <div className="max-h-[480px] overflow-auto">
          <table className="data">
            <thead>
              <tr>
                <th>Experiment</th>
                <th>Run</th>
                <th>Started</th>
                <th>Key metrics</th>
              </tr>
            </thead>
            <tbody>
              {data.runs.map((r: any) => (
                <tr key={r.run_id}>
                  <td className="text-xs text-ink">{r.experiment}</td>
                  <td className="text-xs">{r.run_name}</td>
                  <td className="whitespace-nowrap text-xs">{new Date(r.start_time).toLocaleString()}</td>
                  <td className="text-xs text-muted">
                    {Object.entries(r.metrics)
                      .slice(0, 4)
                      .map(([k, v]) => `${k}=${num(v, 3)}`)
                      .join(" · ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card title="Artifacts" subtitle="Models, forecasts and evaluation tables written by the pipeline">
        <div className="grid gap-x-6 md:grid-cols-2">
          {data.artifacts.map((a: any) => (
            <div key={a.folder + a.file} className="flex justify-between border-b border-line py-2 text-xs">
              <span className="text-ink2">
                <span className="text-muted">{a.folder}/</span>
                {a.file}
              </span>
              <span className="tabular text-muted">{num(a.size_kb, 0)} KB</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
