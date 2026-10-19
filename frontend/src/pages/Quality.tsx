import { RefreshCw, Save } from "lucide-react";
import { useState } from "react";
import { Card, ErrorBox, Loading, PageHeader, Status } from "../components/ui";
import { postJson, useApi } from "../lib/api";
import { num } from "../lib/format";

const CRITERIA = ["compliance", "relevance", "satisfaction", "sentiment", "resolution"];

export default function QualityPage() {
  const [labeler, setLabeler] = useState(() => {
    try { return localStorage.getItem("callverse-labeler") ?? ""; } catch { return ""; }
  });
  const [seed, setSeed] = useState(0);
  const next = useApi<any>(`/api/quality/next?labeler=${encodeURIComponent(labeler || "anonymous")}&seed=${seed}`);
  const calibration = useApi<any>("/api/quality/calibration");
  const [scores, setScores] = useState<Record<string, number>>({ compliance: 3, relevance: 3, satisfaction: 3, sentiment: 3, resolution: 3 });
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [recomputing, setRecomputing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    if (!next.data) return;
    setSaving(true); setError(null);
    try {
      try { localStorage.setItem("callverse-labeler", labeler); } catch { /* not remembered */ }
      await postJson("/api/quality/labels", { ticket_id: next.data.ticket_id, labeler: labeler || "anonymous", ...scores, comment });
      setComment(""); setScores({ compliance: 3, relevance: 3, satisfaction: 3, sentiment: 3, resolution: 3 });
      setSeed((s) => s + 1); calibration.reload();
    } catch (e: any) { setError(e.message); } finally { setSaving(false); }
  };
  const recompute = async () => {
    setRecomputing(true);
    try { await postJson("/api/quality/calibrate", {}); calibration.reload(); } catch (e: any) { setError(e.message); } finally { setRecomputing(false); }
  };

  const cal = calibration.data;
  return (
    <div className="space-y-6">
      <PageHeader
        tag="DSO2 · can the AI judge be trusted?"
        color="var(--layer-agents)"
        title="Human labeling & judge calibration"
        subtitle="Grade conversations with the same scorecard as the Quality agent. With 20+ human labels, the calibration switches from proxy labels (the generator's answer key) to your grades, and reports Cohen's quadratic kappa and Spearman's rho per criterion."
      />
      {cal && (
        <div className="grid gap-4 md:grid-cols-3">
          <div className="card p-4">
            <div className="text-xs font-medium uppercase tracking-wide text-muted">Human-labeled conversations</div>
            <div className="mt-1 text-2xl font-semibold text-ink">{cal.human_labels} / {cal.target}</div>
            <div className="mt-2 h-1.5 rounded-full bg-raised"><div className="h-1.5 rounded-full" style={{ width: `${Math.min(100, (cal.human_labels / cal.target) * 100)}%`, background: "var(--series-1)" }} /></div>
          </div>
          <div className="card p-4 md:col-span-2">
            <div className="mb-2 flex items-center justify-between">
              <div className="text-xs font-medium uppercase tracking-wide text-muted">Judge agreement (trusted if kappa ≥ {cal.min_kappa})</div>
              <button className="btn btn-ghost py-1 text-xs" onClick={recompute} disabled={recomputing}><RefreshCw size={13} /> {recomputing ? "Computing…" : "Recompute"}</button>
            </div>
            {cal.agreement.length ? (
              <table className="data">
                <thead><tr><th>Criterion</th><th>Labels</th><th className="text-right">n</th><th className="text-right">Kappa</th><th className="text-right">Spearman</th><th className="text-right">±1 agreement</th><th /></tr></thead>
                <tbody>
                  {cal.agreement.map((r: any) => (
                    <tr key={r.criterion + r.label_source}>
                      <td className="text-ink">{r.criterion}</td><td className="text-xs">{r.label_source}</td><td className="text-right">{r.n}</td>
                      <td className="text-right">{num(r.quadratic_kappa, 2)}</td><td className="text-right">{num(r.spearman, 2)}</td>
                      <td className="text-right">{num((r.within_one ?? 0) * 100, 0)}%</td>
                      <td><Status ok={r.quadratic_kappa >= cal.min_kappa} label={r.quadratic_kappa >= cal.min_kappa ? "trusted" : "not trusted"} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <div className="text-sm text-muted">Not computed yet: click Recompute or run <code>callverse judge-calibrate</code>.</div>}
          </div>
        </div>
      )}

      {error && <ErrorBox error={error} />}
      <div className="grid gap-6 lg:grid-cols-5">
        <Card title="Conversation to grade" className="lg:col-span-3" subtitle={next.data ? `${next.data.ticket_id} · ${next.data.intent}` : undefined}
          action={<button className="btn btn-ghost py-1 text-xs" onClick={() => setSeed((s) => s + 1)}>Skip</button>}>
          {next.loading || !next.data ? <Loading /> : (
            <div className="space-y-2">
              {next.data.messages.map((m: any) => (
                <div key={m.turn} className="text-sm">
                  <span className="mr-2 text-[10px] font-semibold uppercase tracking-wide text-muted">{m.speaker}</span>
                  <span className="text-ink">{m.text}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card title="Your grades (1 = very poor, 5 = excellent)" className="lg:col-span-2">
          <label className="label">Your name</label>
          <input className="field mb-4" value={labeler} placeholder="e.g. hamza" onChange={(e) => setLabeler(e.target.value)} />
          {CRITERIA.map((c) => (
            <div key={c} className="mb-3">
              <div className="flex justify-between text-sm"><span className="capitalize text-ink">{c}</span><b className="tabular text-ink">{scores[c]}</b></div>
              <p className="text-[11px] text-muted">{next.data?.rubric?.[c]}</p>
              <div className="mt-1 flex gap-1">
                {[1, 2, 3, 4, 5].map((v) => (
                  <button key={v} onClick={() => setScores({ ...scores, [c]: v })}
                    className="h-8 flex-1 rounded-md border text-sm"
                    style={{ borderColor: scores[c] === v ? "var(--brand)" : "var(--hairline)", background: scores[c] === v ? "var(--brand)" : "transparent", color: scores[c] === v ? "white" : "var(--text-primary)" }}>{v}</button>
                ))}
              </div>
            </div>
          ))}
          <textarea className="field mb-3" rows={2} placeholder="Comment (optional)" value={comment} onChange={(e) => setComment(e.target.value)} />
          <button className="btn btn-primary w-full justify-center" onClick={save} disabled={saving || !next.data}><Save size={16} /> {saving ? "Saving…" : "Save and next"}</button>
        </Card>
      </div>
    </div>
  );
}
