/**
 * The twin crowd of the contact centre page: real waiting queues, simulated by the digital twin.
 *
 * The digital twin (DSO4) simulates one day of the centre, customer by customer, from the real arrival data and
 * a staffing plan (GET /api/twin/floor, the same day as the Twin page's live floor). The centre replays one
 * hour of that day on its floor, starting just before the twin's busiest half hour:
 *
 * - every simulated customer walks in, waits in the waiting line (a red bar: waiting longer than 20 s),
 *   is served at a desk for the simulated handling time, then leaves;
 * - a customer whose patience runs out gives up and walks out in red;
 * - an advisor busy with a message left overnight shows an envelope;
 * - the twin's screen on the wall counts, for the replayed hour, who waited, was helped or gave up.
 *
 * The crowd is a simulation (no AI, no LLM cost). The figures are smaller and wear the colour of their
 * problem, and they never slow down the real chats, which stay the spotlight on top. The numbers come from
 * the same helpers as the Twin page's simple view (floorStats in SimpleTwin.tsx), so both pages agree.
 */
import { GROUPS, GROUP_LABEL, num, useApi } from "@callverse/shared";
import { motion } from "framer-motion";
import { Mail, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { type Floor, busiestHalfHour, hhmm, waitingSeries } from "../LiveFloor";
import { type FloorStats, dayLabel, floorStats, groupColor } from "../SimpleTwin";
import { CROWD_LINE, DESK_COUNT, DOOR, type Point, crowdSpot } from "./floor";
import { Person, lookFor } from "./people";

/** A day of the twin to replay, and what it shows. */
export interface CrowdPreset {
  id: string;
  label: string;
  scenario: string;
  day: number; // 0 = the scenario week's Monday
  prepared: boolean; // false: staff planned as if it were a normal week
  note: string;
}

export const CROWD_PRESETS: CrowdPreset[] = [
  { id: "normal", label: "Normal day", scenario: "baseline", day: 0, prepared: true, note: "a calm day: almost nobody waits" },
  {
    id: "aftermath",
    label: "After Black Friday",
    scenario: "black_friday_aftermath_2017",
    day: 0,
    prepared: true,
    note: "the real busiest support week: the advisors start the day with last night's messages",
  },
  {
    id: "promo",
    label: "Promo spike, unprepared",
    scenario: "promo_spike",
    day: 2,
    prepared: false,
    note: "a campaign day staffed like a normal week: the longest waiting line",
  },
];

const SIM_PER_SECOND = 40; // simulated seconds per real second at 1x (an hour in 90 seconds)
const WINDOW = 60 * 60; // one simulated hour is replayed
const CROWD_H = 96; // a simulated customer is smaller than a real one (140)
const ARRIVE_S = 1.4; // real seconds to walk from the door
const LEAVE_S = 1.6; // real seconds to walk out (and fade)

const floorUrl = (p: CrowdPreset) => `/api/twin/floor?scenario=${p.scenario}&plan=cpsat&router=fifo&day=${p.day}&prepared=${p.prepared}`;

/** One simulated customer on the floor at this moment. */
export interface CrowdFigure {
  key: string;
  group: string;
  at: Point;
  kind: "queue" | "desk" | "leave" | "gaveup";
  late: boolean; // waiting longer than the service threshold
  walking: boolean;
}

/** What the crowd looks like at one simulated moment, and the numbers of the replayed hour so far. */
export interface CrowdView {
  figures: CrowdFigure[];
  mail: number[]; // desks answering a message left overnight
  overflow: number; // waiting customers beyond the 24 places of the line
  busy: Set<number>; // desks serving a simulated customer or a message
  stats: FloorStats;
  hour: { arrived: number; helped: number; gaveUp: number; onTime: number | null; waiting: number };
}

/**
 * The crowd at simulated time T. `slots` remembers which desk each simulated advisor uses (an advisor keeps
 * the same desk while on duty). `sps`: simulated seconds per real second (walks last the same real time).
 */
export function crowdView(floor: Floor, T: number, from: number, slots: Map<number, number>, sps: number): CrowdView {
  const c = floor.contacts;
  const stats = floorStats(floor, T);
  // 1) Desks: the twin's advisors on duty, one desk each (at most 8).
  const onDuty = new Set(stats.desks.map((d) => d.agentId));
  for (const agent of [...slots.keys()]) if (!onDuty.has(agent)) slots.delete(agent);
  const used = new Set(slots.values());
  for (const desk of stats.desks) {
    if (slots.has(desk.agentId)) continue;
    let slot = 0;
    while (used.has(slot)) slot++;
    if (slot < DESK_COUNT) {
      slots.set(desk.agentId, slot);
      used.add(slot);
    }
  }
  const figures: CrowdFigure[] = [];
  const mail: number[] = [];
  const busy = new Set<number>();
  for (const desk of stats.desks) {
    const slot = slots.get(desk.agentId);
    if (slot === undefined || desk.serving === null) continue;
    busy.add(slot);
    if (!desk.live) mail.push(slot);
    else figures.push({ key: `c${desk.serving}`, group: c.group[desk.serving], at: crowdSpot(slot), kind: "desk", late: false, walking: false });
  }
  // 2) The waiting line, the longest wait first.
  stats.queue.slice(0, CROWD_LINE.length).forEach((i, place) =>
    figures.push({
      key: `c${i}`,
      group: c.group[i],
      at: CROWD_LINE[place],
      kind: "queue",
      late: T - c.arrival[i] > floor.threshold_seconds,
      walking: T - c.arrival[i] < ARRIVE_S * sps,
    }),
  );
  // 3) Who just left: served (walks out), or gave up (walks out in red). And the replayed hour's numbers.
  const hour = { arrived: 0, helped: 0, gaveUp: 0, onTime: null as number | null, waiting: stats.waiting };
  let due = 0;
  let inTime = 0;
  for (let i = 0; i < c.id.length; i++) {
    if (c.live && !c.live[i]) continue;
    const start = c.start[i];
    const end = c.end[i];
    const quit = c.abandon_at[i];
    if (end !== null && start !== null && end <= T && T - end < LEAVE_S * sps)
      figures.push({ key: `c${i}`, group: c.group[i], at: DOOR, kind: "leave", late: false, walking: true });
    if (c.abandoned[i] && quit !== null && quit <= T && T - quit < LEAVE_S * sps)
      figures.push({ key: `c${i}`, group: c.group[i], at: DOOR, kind: "gaveup", late: true, walking: true });
    if (c.arrival[i] < from || c.arrival[i] > T) continue;
    hour.arrived++;
    if (start !== null && start <= T) hour.helped++;
    if (c.abandoned[i] && quit !== null && quit <= T) hour.gaveUp++;
    if (c.arrival[i] + floor.threshold_seconds <= T) {
      due++;
      if (start !== null && start - c.arrival[i] <= floor.threshold_seconds) inTime++;
    }
  }
  hour.onTime = due ? inTime / due : null;
  return { figures, mail, overflow: Math.max(0, stats.queue.length - CROWD_LINE.length), busy, stats, hour };
}

/**
 * Loads the twin's day for the chosen preset and plays one hour of it: the simulated clock moves
 * SIM_PER_SECOND x the page's speed every real second. Returns the crowd at the current moment.
 */
export function useCrowd(preset: CrowdPreset | null, speed: number) {
  const floor = useApi<Floor>(preset ? floorUrl(preset) : null);
  const data = preset && !floor.loading ? floor.data : null;
  const [span, setSpan] = useState<{ from: number; to: number } | null>(null);
  const [t, setT] = useState(0);
  const [round, setRound] = useState(0);
  const time = useRef(0);
  const slots = useRef(new Map<number, number>());
  const speedRef = useRef(speed);
  speedRef.current = speed;

  // A new day (or "again"): start 15 minutes before the busiest half hour, for one hour.
  useEffect(() => {
    if (!data) {
      setSpan(null);
      return;
    }
    const busiest = busiestHalfHour(waitingSeries(data));
    const [open, close] = data.opening_hours;
    const from = Math.max(open * 3600, busiest.t - 15 * 60);
    const to = Math.min((close + 1) * 3600, from + WINDOW);
    time.current = from;
    slots.current = new Map();
    setSpan({ from, to });
    setT(from);
  }, [data, round]);

  // The simulated clock: one step per screen refresh (at most half a second at a time, so a hidden tab does not
  // jump ahead), shown about ten times a second.
  useEffect(() => {
    if (!data || !span) return;
    let frame = 0;
    let last = performance.now();
    let shown = 0;
    const tick = (now: number) => {
      const dt = Math.min(0.5, (now - last) / 1000);
      last = now;
      time.current = Math.min(span.to, time.current + dt * SIM_PER_SECOND * speedRef.current);
      if (now - shown > 100 || time.current >= span.to) {
        shown = now;
        setT(time.current);
      }
      if (time.current < span.to) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [data, span]);

  const sps = SIM_PER_SECOND * speed;
  const view = useMemo(
    () => (data && span ? crowdView(data, t, span.from, slots.current, sps) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, span, t],
  );
  return {
    view,
    floor: data,
    span,
    t,
    loading: !!preset && floor.loading,
    error: preset ? floor.error : null,
    done: !!span && t >= span.to,
    again: () => setRound((r) => r + 1),
  };
}

// --------------------------------------------------------------------------- drawing
/** The simulated customers on the floor: they walk in, queue, are served, and leave (or give up in red). */
export function CrowdLayer({ view }: { view: CrowdView }) {
  const width = CROWD_H / 2;
  return (
    <>
      {view.figures.map((f) => {
        const leaving = f.kind === "leave" || f.kind === "gaveup";
        return (
          <motion.div
            key={f.key}
            className="pointer-events-none absolute left-0 top-0"
            initial={{ x: DOOR.x - width / 2, y: DOOR.y - CROWD_H, opacity: 0 }}
            animate={{ x: f.at.x - width / 2, y: f.at.y - CROWD_H, opacity: leaving ? 0 : 1 }}
            transition={{
              x: { duration: leaving ? LEAVE_S : f.kind === "queue" ? 0.6 : 0.9, ease: "easeInOut" },
              y: { duration: leaving ? LEAVE_S : f.kind === "queue" ? 0.6 : 0.9, ease: "easeInOut" },
              opacity: { duration: leaving ? LEAVE_S : 0.4 },
            }}
            style={{ zIndex: Math.round(f.at.y) }}
          >
            <Person
              role="customer"
              look={lookFor(f.key)}
              height={CROWD_H}
              walking={f.walking}
              color={f.kind === "gaveup" ? "#dc2626" : groupColor(f.group)}
              title={`Simulated customer (twin) · ${GROUP_LABEL[f.group] ?? f.group}${f.kind === "gaveup" ? " · gave up" : ""}`}
            />
            {f.late && f.kind === "queue" && (
              <span className="absolute left-1/2 h-1.5 w-8 -translate-x-1/2 rounded-full" style={{ bottom: -6, background: "var(--critical)" }} />
            )}
          </motion.div>
        );
      })}
      {view.mail.map((slot) => {
        const at = crowdSpot(slot);
        return (
          <div
            key={`mail-${slot}`}
            className="pointer-events-none absolute flex h-7 w-9 items-center justify-center rounded-lg border border-line bg-surface shadow-soft"
            style={{ left: at.x - 18, top: at.y - 46, zIndex: Math.round(at.y) }}
            title="Answering a message left overnight (simulated)"
          >
            <Mail size={16} className="text-ink2" aria-hidden />
          </div>
        );
      })}
      {view.overflow > 0 && (
        <div className="pointer-events-none absolute rounded-full bg-surface px-2 py-0.5 text-sm font-semibold text-ink shadow-soft" style={{ left: 520, top: 760, zIndex: 900 }}>
          +{view.overflow}
        </div>
      )}
    </>
  );
}

/** The twin's screen on the wall (next to the KPI wall): the replayed hour, its clock and its numbers. */
export function TwinBoard({ crowd, preset }: { crowd: ReturnType<typeof useCrowd>; preset: CrowdPreset }) {
  const { view, floor, span, t, done } = crowd;
  const progress = span ? Math.min(1, (t - span.from) / (span.to - span.from)) : 0;
  const s = view?.stats;
  const h = view?.hour;
  const tiles = [
    { label: "Waiting", value: h ? num(h.waiting, 0) : "–", alert: (h?.waiting ?? 0) >= 3 },
    { label: "Helped", value: h ? num(h.helped, 0) : "–" },
    { label: "Gave up", value: h ? num(h.gaveUp, 0) : "–", alert: (h?.gaveUp ?? 0) > 0 },
    { label: "On time", value: h?.onTime == null ? "–" : `${Math.round(h.onTime * 100)}%` },
  ];
  return (
    <div
      className="absolute flex flex-col rounded-2xl px-3.5 py-2.5"
      style={{ left: 186, top: 18, width: 322, height: 190, zIndex: 6, background: "#0b1020", border: "5px solid #334155" }}
      role="region"
      aria-label="Twin crowd: simulated customers"
    >
      <div className="flex items-center justify-between gap-2 text-[11px] font-semibold uppercase tracking-[0.13em]" style={{ color: "#fcd34d" }}>
        <span className="truncate">Twin crowd · simulated</span>
        {done && (
          <button
            className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-white"
            style={{ background: "rgba(148,163,184,0.3)" }}
            onClick={crowd.again}
            title="Replay the same hour"
            aria-label="Replay the same hour"
          >
            <RotateCcw size={11} />
          </button>
        )}
      </div>
      <div className="truncate text-[11.5px]" style={{ color: "#cbd5e1" }}>
        {preset.label}
        {floor ? ` · ${dayLabel(floor.date)}` : ""}
      </div>
      <div className="mt-1 flex items-center gap-3">
        <span className="font-display text-[28px] font-semibold leading-none tabular text-white">{span ? hhmm(t) : "--:--"}</span>
        <div className="min-w-0 flex-1">
          <div className="h-1.5 overflow-hidden rounded-full" style={{ background: "rgba(148,163,184,0.25)" }}>
            <div className="h-full rounded-full" style={{ width: `${progress * 100}%`, background: "#fcd34d" }} />
          </div>
          <div className="mt-0.5 truncate text-[10.5px]" style={{ color: "#94a3b8" }}>
            {span
              ? `${hhmm(span.from)} → ${hhmm(span.to)}${done ? " · replay over" : ""}`
              : crowd.error
                ? "the twin did not answer"
                : "the twin plans this day (first time: up to a minute)…"}
          </div>
        </div>
      </div>
      <div className="mt-2 grid grid-cols-4 gap-1.5">
        {tiles.map((tile) => (
          <div key={tile.label} className="rounded-lg px-1.5 py-1 text-center" style={{ background: "rgba(148,163,184,0.13)" }}>
            <div className="font-display text-[18px] font-semibold leading-none tabular" style={{ color: tile.alert ? "#fca5a5" : "#ffffff" }}>
              {tile.value}
            </div>
            <div className="mt-0.5 text-[10px]" style={{ color: "#cbd5e1" }}>
              {tile.label}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-1.5 text-[10.5px] leading-tight" style={{ color: "#94a3b8" }}>
        {s ? (
          <>
            <div className="truncate">
              {s.onDuty} advisors on duty{s.onDuty > DESK_COUNT ? ` (${DESK_COUNT} desks shown)` : ""}
            </div>
            <div className="truncate">{s.busyMessages ? `${s.busyMessages} answering last night's messages ✉` : "no message left from last night"}</div>
          </>
        ) : (
          <div className="truncate">{preset.note}</div>
        )}
      </div>
    </div>
  );
}

/** The legend line of the crowd: the problem colours. */
export function CrowdLegend() {
  return (
    <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1">
      <b className="text-ink">Simulated customers</b> (digital twin), colour = problem:
      {GROUPS.map((g) => (
        <span key={g} className="inline-flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: groupColor(g) }} /> {GROUP_LABEL[g]}
        </span>
      ))}
      <span className="inline-flex items-center gap-1">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: "#dc2626" }} /> gave up
      </span>
    </span>
  );
}
