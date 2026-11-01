import { PolarAngleAxis, PolarGrid, Radar, RadarChart, ResponsiveContainer } from "recharts";
import { Ring } from "./motion";
import { Status } from "./ui";

const CRITERIA = ["compliance", "relevance", "satisfaction", "sentiment", "resolution"];

/** Quality agent's scorecard: radar of the five criteria + overall ring + verdicts. */
export function QualityScore({ review, compact = false }: { review: { scorecard: any; reference?: any; kpis?: any }; compact?: boolean }) {
  const card = review.scorecard;
  const data = CRITERIA.map((c) => ({ criterion: c, score: card.scores?.[c] ?? 0 }));
  const overall = card.overall ?? data.reduce((sum, d) => sum + d.score, 0) / data.length;
  const color = overall >= 4 ? "var(--good)" : overall >= 3 ? "var(--warning)" : "var(--critical)";
  return (
    <div className={compact ? "space-y-3" : "space-y-4"}>
      <div className="flex items-center gap-4">
        <Ring value={overall / 5} size={compact ? 64 : 84} stroke={compact ? 6 : 8} color={color}>
          <div className="text-center">
            <div className="font-display text-lg font-bold leading-none text-ink">{Number(overall).toFixed(1)}</div>
            <div className="text-[9px] uppercase tracking-wide text-muted">/ 5</div>
          </div>
        </Ring>
        <div className="space-y-1">
          <Status ok={card.correct} label={card.correct === null ? "correctness not judged" : card.correct ? "policy-correct answer" : "answer differs from policy"} />
          <br />
          <Status ok={card.resolved} label={card.resolved ? "resolved / correctly handed over" : "not resolved"} />
          <div className="text-[11px] text-muted">
            Judge: {card.judge === "llm" ? String(card.model ?? "LLM").split("/").pop() : "rule-based checklist"}
          </div>
        </div>
      </div>
      <div className={compact ? "h-44" : "h-56"}>
        <ResponsiveContainer>
          <RadarChart data={data} outerRadius="72%">
            <PolarGrid />
            <PolarAngleAxis dataKey="criterion" tick={{ fontSize: 11, fill: "var(--text-muted)" }} />
            <Radar dataKey="score" stroke="var(--brand)" fill="var(--brand)" fillOpacity={0.25} strokeWidth={2} isAnimationActive />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      {card.rationale && <p className="text-xs leading-relaxed text-ink2">“{card.rationale}”</p>}
      {review.reference?.outcome && (
        <p className="text-[11px] text-muted">
          Policy reference: <b className="text-ink2">{String(review.reference.outcome).replace(/_/g, " ")}</b>
          {review.reference.handed_to ? ` → ${review.reference.handed_to}` : ""}
        </p>
      )}
    </div>
  );
}
