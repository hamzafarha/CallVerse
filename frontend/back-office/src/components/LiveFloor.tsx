import { GROUPS, GROUP_LABEL, Segmented, clsx, motion, num, pct, useCssVars, useDocumentTheme } from "@callverse/shared";
import { FastForward, Mail, Pause, Play, RotateCcw, Zap } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Area, AreaChart, ReferenceLine, ResponsiveContainer, YAxis } from "recharts";

/** Animated replay of one simulated day of the digital twin.
 *
 * Every dot is a customer contact of the SimPy run: it arrives, waits in the
 * queue, travels to the desk of the agent the router picked, is served, then
 * leaves — or hangs up (red) when its patience runs out. Desks are colored by
 * the agent's main skill and filled with the problem type being handled. */

interface Floor {
  date: string;
  label: string;
  opening_hours: [number, number];
  threshold_seconds: number;
  agents: { agent_id: number; primary_group: string; overtime: boolean; on_call: boolean; duty: boolean[] | null }[];
  contacts: {
    id: string[];
    group: string[];
    patience: string[];
    arrival: number[];
    start: (number | null)[];
    end: (number | null)[];
    abandon_at: (number | null)[];
    abandoned: boolean[];
    agent: (number | null)[];
    live: boolean[];
  };
  summary: { contacts: number; backlog: number; answered: number; abandoned: number; service_level: number; mean_wait_seconds: number };
}

const SPEEDS = [
  { value: "60", label: "60×" },
  { value: "300", label: "5 min/s" },
  { value: "900", label: "15 min/s" },
  { value: "1800", label: "30 min/s" },
];
const TRAVEL = 0.45; // real seconds a customer takes to walk to the desk
const FADE = 0.9; // real seconds for leaving / hanging-up animations

const VARS = ["--series-1", "--series-2", "--series-3", "--series-4", "--surface-1", "--surface-2", "--surface-3", "--hairline", "--text-muted", "--text-primary", "--critical", "--good", "--brand", "--baseline"];

function hhmm(seconds: number): string {
  const h = Math.floor(seconds / 3600) % 24;
  const m = Math.floor((seconds % 3600) / 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export function LiveFloor({ floor }: { floor: Floor }) {
  const theme = useDocumentTheme();
  const canvas = useRef<HTMLCanvasElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const colors = useCssVars(VARS, theme);
  const [open, close] = floor.opening_hours;
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState("300");
  const [view, setView] = useState({ t: open * 3600, waiting: 0, serving: 0, answered: 0, abandoned: 0, sl: 1, onDuty: 0, backlog: 0 });
  const time = useRef(open * 3600);
  const playingRef = useRef(playing);
  const speedRef = useRef(Number(speed));
  playingRef.current = playing;
  speedRef.current = Number(speed);

  const c = useMemo(() => ({ ...floor.contacts, live: floor.contacts.live ?? floor.contacts.id.map(() => true) }), [floor]);
  const n = c.id.length;
  const order = useMemo(() => Array.from({ length: n }, (_, i) => i).sort((a, b) => c.arrival[a] - c.arrival[b]), [c, n]);
  const agentIndex = useMemo(() => new Map(floor.agents.map((a, i) => [a.agent_id, i])), [floor.agents]);
  const series = useMemo(() => {
    const points = [];
    for (let t = open * 3600; t <= close * 3600 + 3600; t += 120) {
      let waiting = 0;
      for (let i = 0; i < n; i++) {
        if (!c.live[i]) continue;
        const leave = c.start[i] ?? c.abandon_at[i] ?? Infinity;
        if (c.arrival[i] <= t && t < leave) waiting++;
      }
      points.push({ t, waiting });
    }
    return points;
  }, [c, n, open, close]);
  // Busiest 30 minutes = most customer-minutes of waiting (a sustained queue, not a one-off blip)
  const peak = useMemo(() => {
    const window = 15; // 15 samples of 2 minutes
    let best = { t: open * 3600, load: -1 };
    for (let i = 0; i + window <= series.length; i++) {
      const load = series.slice(i, i + window).reduce((sum, p) => sum + p.waiting, 0);
      if (load > best.load) best = { t: series[i].t, load };
    }
    return best;
  }, [series, open]);

  useEffect(() => {
    time.current = open * 3600;
  }, [floor, open]);

  useEffect(() => {
    const el = canvas.current;
    const container = box.current;
    if (!el || !container) return;
    const ctx = el.getContext("2d");
    if (!ctx) return;
    const groupColor: Record<string, string> = Object.fromEntries(GROUPS.map((g, i) => [g, colors[`--series-${i + 1}`] || "#888"]));
    const positions = new Map<number, { x: number; y: number }>();
    let width = 0;
    let height = 0;
    const resize = () => {
      const ratio = window.devicePixelRatio || 1;
      width = container.clientWidth;
      height = Math.max(380, Math.min(520, width * 0.5));
      el.width = width * ratio;
      el.height = height * ratio;
      el.style.width = `${width}px`;
      el.style.height = `${height}px`;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(container);

    const agents = floor.agents;
    const cols = Math.max(4, Math.ceil(Math.sqrt(agents.length * 1.7)));
    let last = performance.now();
    let lastUi = 0;
    let frame = 0;

    const draw = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      if (playingRef.current) {
        time.current = Math.min((close + 1.5) * 3600, time.current + dt * speedRef.current);
      }
      const T = time.current;
      const travel = TRAVEL * speedRef.current;
      const fade = FADE * speedRef.current;
      const hour = Math.floor(T / 3600);

      // layout
      const pad = 18;
      const queueW = width * 0.36;
      const deskX = queueW + 70;
      const deskW = width - deskX - pad;
      const rows = Math.ceil(agents.length / cols);
      const cell = Math.min(deskW / cols, (height - 70) / Math.max(rows, 1));
      const deskSize = cell * 0.78;
      const deskTop = 46 + (height - 70 - rows * cell) / 2;
      const deskPos = (index: number) => ({
        x: deskX + (index % cols) * cell + cell / 2,
        y: deskTop + Math.floor(index / cols) * cell + cell / 2,
      });
      const qCols = Math.max(6, Math.floor((queueW - pad) / 14));
      const queueSlot = (i: number) => ({
        x: queueW - 10 - (i % qCols) * 14,
        y: 60 + Math.floor(i / qCols) * 14,
      });

      ctx.clearRect(0, 0, width, height);
      // zones
      ctx.fillStyle = colors["--surface-2"] || "#111";
      roundRect(ctx, pad / 2, 30, queueW, height - 40, 16);
      ctx.fill();
      ctx.font = "600 10px 'Inter Variable', sans-serif";
      ctx.fillStyle = colors["--text-muted"] || "#999";
      ctx.fillText("QUEUE  ·  arrivals enter from the left", pad, 20);
      ctx.fillText("AGENT DESKS  ·  border = skill, fill = problem handled", deskX, 20);

      // gather states
      const busy = new Map<number, number>();
      const waiting: number[] = [];
      let answered = 0;
      let abandoned = 0;
      let inTime = 0;
      let due = 0;
      let backlog = 0;
      for (const i of order) {
        const arrival = c.arrival[i];
        if (arrival > T) break;
        const start = c.start[i];
        if (!c.live[i]) {
          // overnight messages: no queue, they only occupy a desk while worked on
          if (start === null || start > T) backlog++;
          const desk = agentIndex.get(c.agent[i] ?? -1);
          if (start !== null && start <= T && T < (c.end[i] ?? Infinity) && desk !== undefined) busy.set(desk, i);
          continue;
        }
        const leaveQueue = start ?? c.abandon_at[i] ?? Infinity;
        if (arrival + floor.threshold_seconds <= T) {
          due++;
          if (start !== null && start - arrival <= floor.threshold_seconds) inTime++;
        }
        if (T < leaveQueue) waiting.push(i);
        if (start !== null && start <= T) {
          answered++;
          const end = c.end[i] ?? Infinity;
          const desk = agentIndex.get(c.agent[i] ?? -1);
          if (desk !== undefined && T < end) busy.set(desk, i);
        }
        if (c.abandoned[i] && (c.abandon_at[i] ?? Infinity) <= T) abandoned++;
      }

      // desks
      agents.forEach((agent, index) => {
        const p = deskPos(index);
        const onDuty = agent.duty ? !!agent.duty[Math.min(23, hour)] : busy.has(index);
        const skill = groupColor[agent.primary_group] ?? colors["--baseline"];
        const serving = busy.get(index);
        ctx.globalAlpha = onDuty || serving !== undefined ? 1 : 0.28;
        ctx.fillStyle = serving !== undefined ? groupColor[c.group[serving]] : colors["--surface-1"] || "#000";
        roundRect(ctx, p.x - deskSize / 2, p.y - deskSize / 2, deskSize, deskSize, deskSize * 0.22);
        if (serving !== undefined && !c.live[serving]) ctx.globalAlpha = 0.4;
        ctx.fill();
        ctx.globalAlpha = onDuty || serving !== undefined ? 1 : 0.28;
        if (serving !== undefined && !c.live[serving]) envelope(ctx, p.x, p.y, deskSize * 0.34, colors["--text-primary"]);
        ctx.lineWidth = 2;
        ctx.strokeStyle = skill;
        ctx.setLineDash(onDuty ? [] : [3, 3]);
        ctx.stroke();
        ctx.setLineDash([]);
        if (serving !== undefined) {
          const start = c.start[serving] ?? T;
          const end = c.end[serving] ?? T + 1;
          const progress = Math.min(1, Math.max(0, (T - start) / Math.max(1, end - start)));
          ctx.beginPath();
          ctx.strokeStyle = "rgba(255,255,255,0.9)";
          ctx.lineWidth = 2.5;
          ctx.arc(p.x, p.y, deskSize * 0.26, -Math.PI / 2, -Math.PI / 2 + progress * Math.PI * 2);
          ctx.stroke();
        }
        if (agent.overtime) {
          ctx.fillStyle = colors["--text-muted"];
          ctx.font = "700 8px 'Inter Variable', sans-serif";
          ctx.fillText(agent.on_call ? "+OT" : "OT", p.x - deskSize / 2 + 3, p.y + deskSize / 2 - 3);
        }
        ctx.globalAlpha = 1;
      });

      // waiting customers (smoothly sliding to their slot)
      waiting.forEach((i, rank) => {
        const target = queueSlot(rank);
        const current = positions.get(i) ?? { x: pad, y: target.y };
        current.x += (target.x - current.x) * Math.min(1, dt * 7);
        current.y += (target.y - current.y) * Math.min(1, dt * 7);
        positions.set(i, current);
        const waited = T - c.arrival[i];
        dot(ctx, current.x, current.y, 4.6, groupColor[c.group[i]], 1);
        if (waited > floor.threshold_seconds) {
          ctx.beginPath();
          ctx.strokeStyle = colors["--critical"];
          ctx.lineWidth = 1.2;
          ctx.arc(current.x, current.y, 7, 0, Math.PI * 2);
          ctx.stroke();
        }
      });

      // transitions: to desk, leaving, hanging up
      for (const i of order) {
        const arrival = c.arrival[i];
        if (arrival > T) break;
        if (!c.live[i]) continue;
        const start = c.start[i];
        if (start !== null && T >= start && T < start + travel) {
          const desk = agentIndex.get(c.agent[i] ?? -1);
          if (desk === undefined) continue;
          const from = positions.get(i) ?? { x: queueW - 10, y: 60 };
          const to = deskPos(desk);
          const k = ease((T - start) / travel);
          dot(ctx, from.x + (to.x - from.x) * k, from.y + (to.y - from.y) * k - Math.sin(k * Math.PI) * 30, 4.6, groupColor[c.group[i]], 1);
        }
        const end = c.end[i];
        if (start !== null && end !== null && T >= end && T < end + fade) {
          const desk = agentIndex.get(c.agent[i] ?? -1);
          if (desk === undefined) continue;
          const p = deskPos(desk);
          const k = (T - end) / fade;
          dot(ctx, p.x + k * 40, p.y - k * 26, 3.5, colors["--good"], 1 - k);
        }
        const gone = c.abandon_at[i];
        if (c.abandoned[i] && gone !== null && T >= gone && T < gone + fade) {
          const p = positions.get(i) ?? { x: pad, y: 60 };
          const k = (T - gone) / fade;
          dot(ctx, p.x - k * 10, p.y + k * 40, 4.6, colors["--critical"], 1 - k);
        }
      }
      for (const key of positions.keys()) if (!waiting.includes(key) && (c.start[key] ?? 0) + travel < T) positions.delete(key);

      if (now - lastUi > 120) {
        lastUi = now;
        const onDuty = agents.filter((a) => (a.duty ? a.duty[Math.min(23, hour)] : false)).length;
        setView({ t: T, waiting: waiting.length, serving: busy.size, answered, abandoned, sl: due ? inTime / due : 1, onDuty, backlog });
      }
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [floor, colors, order, agentIndex, c, open, close]);

  const restart = () => {
    time.current = open * 3600;
    setPlaying(true);
  };
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        <Clock t={view.t} />
        <Kpi label="Waiting now" value={num(view.waiting, 0)} accent={view.waiting > 10 ? "var(--critical)" : undefined} />
        <Kpi label="Busy agents" value={`${view.serving} / ${view.onDuty}`} />
        <Kpi label="Backlog left" value={num(view.backlog, 0)} />
        <Kpi label="Answered" value={num(view.answered, 0)} />
        <Kpi label="Hung up" value={num(view.abandoned, 0)} accent={view.abandoned ? "var(--critical)" : undefined} />
        <Kpi label={`Service level (${floor.threshold_seconds}s)`} value={pct(view.sl, 0)} accent={view.sl < 0.8 ? "var(--critical)" : "var(--good-text)"} />
      </div>
      <div ref={box} className="relative overflow-hidden rounded-2xl border border-line bg-surface">
        <canvas ref={canvas} className="block" />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <motion.button whileTap={{ scale: 0.9 }} className="btn btn-primary btn-icon h-10 w-10" onClick={() => setPlaying(!playing)} aria-label={playing ? "Pause" : "Play"}>
          {playing ? <Pause size={16} /> : <Play size={16} />}
        </motion.button>
        <button className="btn btn-ghost btn-icon h-10 w-10" onClick={restart} aria-label="Restart">
          <RotateCcw size={15} />
        </button>
        <button className="btn btn-soft h-10" onClick={() => (time.current = peak.t)}>
          <Zap size={14} /> Jump to the peak ({hhmm(peak.t)})
        </button>
        <Segmented id="floor-speed" size="sm" value={speed} onChange={setSpeed} options={SPEEDS.map((s) => ({ value: s.value, label: s.label }))} />
        <div className="flex min-w-[200px] flex-1 items-center gap-3">
          <FastForward size={14} className="text-muted" />
          <input
            type="range"
            min={open * 3600}
            max={(close + 1.5) * 3600}
            step={60}
            value={view.t}
            onChange={(e) => (time.current = Number(e.target.value))}
            className="w-full"
          />
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-[1fr_auto]">
        <div className="h-20 rounded-2xl border border-line bg-surface px-2 pt-2">
          <ResponsiveContainer>
            <AreaChart data={series} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
              <defs>
                <linearGradient id="floor-fill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="var(--brand)" stopOpacity={0.45} />
                  <stop offset="100%" stopColor="var(--brand)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <YAxis hide />
              <Area dataKey="waiting" stroke="var(--brand)" fill="url(#floor-fill)" strokeWidth={2} isAnimationActive={false} />
              <ReferenceLine x={series.findIndex((p) => p.t >= view.t)} stroke="var(--brand-2)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink2 md:max-w-[340px]">
          {GROUPS.map((g, i) => (
            <span key={g} className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: `var(--series-${i + 1})` }} /> {GROUP_LABEL[g]}
            </span>
          ))}
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full border-2" style={{ borderColor: "var(--critical)" }} /> waiting &gt; {floor.threshold_seconds}s
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: "var(--critical)" }} /> hung up
          </span>
          <span className="inline-flex items-center gap-1.5"><Mail size={13} /> overnight backlog being worked on</span>
        </div>
      </div>
    </div>
  );
}

function Clock({ t }: { t: number }) {
  return (
    <div className="card col-span-2 flex items-center gap-3 p-4 md:col-span-1">
      <div className="font-display text-3xl font-semibold tabular text-ink">{hhmm(t)}</div>
      <div className="text-[11px] leading-tight text-muted">
        twin
        <br />
        clock
      </div>
    </div>
  );
}

function Kpi({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="card p-4">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">{label}</div>
      <div className={clsx("mt-1 font-display text-xl font-semibold tabular")} style={{ color: accent ?? "var(--text-primary)" }}>
        {value}
      </div>
    </div>
  );
}

/** Small envelope (overnight message), drawn so it does not depend on an emoji font. */
function envelope(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, color: string) {
  const h = w * 0.68;
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.6;
  ctx.lineJoin = "round";
  ctx.strokeRect(x - w / 2, y - h / 2, w, h);
  ctx.beginPath();
  ctx.moveTo(x - w / 2, y - h / 2);
  ctx.lineTo(x, y + h * 0.1);
  ctx.lineTo(x + w / 2, y - h / 2);
  ctx.stroke();
  ctx.restore();
}

function ease(k: number): number {
  const x = Math.max(0, Math.min(1, k));
  return x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2;
}

function dot(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, color: string, alpha: number) {
  ctx.globalAlpha = Math.max(0, alpha);
  ctx.beginPath();
  ctx.fillStyle = color;
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalAlpha = 1;
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
