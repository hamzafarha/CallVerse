/**
 * The "simple view" of the digital twin: what happens to the CUSTOMERS, in pictures anyone understands, for a
 * jury that has never seen a queueing model.
 *
 * - every agent has a desk: its border = the agent's speciality, its colour = the case it is handling now;
 * - the waiting line is people coloured by their problem; when an agent takes a customer, that person slides
 *   from the line to the agent's desk (routing); a customer who gives up drops out in red;
 * - two counters grow live: customers helped and customers who gave up;
 * - race bars compare the lost customers and the cost so far;
 * - a caption tells the story by itself, written from the simulation's own numbers (no AI involved);
 * - in the Scenario lab, "out of 100 customers" is drawn as 100 little people.
 *
 * Everything is computed from the same data as the detailed view (GET /api/twin/floor, POST /api/twin/run and
 * /api/twin/compare): only the way it is shown changes.
 */
import { GROUPS, GROUP_LABEL, clsx, num } from "@callverse/shared";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { Headset, Mail, MessageCircle, Trophy, User, UserCheck, UserX } from "lucide-react";
import { type ReactNode, useEffect, useMemo } from "react";
import {
  type Floor,
  type FloorClock,
  FloorControls,
  busiestHalfHour,
  costSoFar,
  hhmm,
  useFloorClock,
  waitingSeries,
} from "./LiveFloor";

// ------------------------------------------------------------------ plain words
/** Shift planners, in words a jury understands. */
export const PLAN_PLAIN: Record<string, string> = {
  cpsat: "Optimised shifts",
  rules_erlang: "Rule-of-thumb shifts",
  fixed: "Same shifts every day",
  fixed_tuned: "Same shifts, smaller team",
  erlang_hourly: "Staff matched hour by hour",
};

/** Routers: who answers which customer. */
export const ROUTER_PLAIN: Record<string, string> = {
  fifo: "First come, first served",
  skill_score: "Best-skilled free agent",
  ppo: "Learned dispatcher (AI)",
};

/** What the planner knew: the forecast of this week, or nothing special. */
export function planSourcePlain(scenario: any): { unprepared: string; prepared: string } {
  return {
    unprepared: scenario?.reference_week ? "Staff copied from a normal week" : "Planned as if it were a normal week",
    prepared: "Planned with our forecast",
  };
}

/** "2017-12-20" -> "Wednesday 20 Dec 2017". */
export function dayLabel(iso?: string): string {
  if (!iso) return "";
  const date = new Date(`${iso}T12:00:00`);
  return date.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "short", year: "numeric" });
}

const euros = (value: number | null | undefined) => (value == null ? "–" : `€${num(Math.round(value), 0)}`);

// ------------------------------------------------------------------- live counts
/** What is happening at time T (seconds from midnight) on one simulated day. */
export interface FloorStats {
  t: number;
  onDuty: number;
  busy: number;
  busyLive: number; // talking to a live customer
  busyMessages: number; // answering an overnight message (the night's backlog, worked in the morning)
  waiting: number;
  waitingLong: number; // waiting longer than the service threshold (20 s)
  helped: number;
  gaveUp: number;
  arrived: number;
  onTime: number | null; // share answered within the threshold, among the customers already due
  cost: number | null;
  desks: Desk[]; // the agents at work, in a fixed order, with the case each one is handling
  queue: number[]; // the waiting customers (contact positions), the longest waiting first
}

/** One agent at work: its speciality, and the contact it is handling now (null = free). */
export interface Desk {
  agentId: number;
  skill: string;
  serving: number | null;
  live: boolean; // a live customer (false: a message left overnight)
}

/** Count everything at time T, from the contacts and agents of the floor. */
export function floorStats(floor: Floor, T: number): FloorStats {
  const c = floor.contacts;
  const threshold = floor.threshold_seconds;
  const hour = Math.min(23, Math.max(0, Math.floor(T / 3600)));
  const talking = new Set<number>();
  const onMessages = new Set<number>();
  const servingBy = new Map<number, number>(); // agent id -> contact being handled
  const queue: number[] = [];
  let waiting = 0;
  let waitingLong = 0;
  let helped = 0;
  let gaveUp = 0;
  let arrived = 0;
  let due = 0;
  let inTime = 0;
  for (let i = 0; i < c.id.length; i++) {
    const arrival = c.arrival[i];
    if (arrival > T) continue;
    const start = c.start[i];
    const live = !c.live || c.live[i];
    // An agent is busy while a conversation (or an overnight message) is in progress.
    if (start !== null && start <= T && T < (c.end[i] ?? Infinity) && c.agent[i] !== null) {
      (live ? talking : onMessages).add(c.agent[i] as number);
      servingBy.set(c.agent[i] as number, i);
    }
    if (!live) continue; // overnight messages never stand in the live line
    arrived++;
    const leave = start ?? c.abandon_at[i] ?? Infinity;
    if (T < leave) {
      waiting++;
      queue.push(i);
      if (T - arrival > threshold) waitingLong++;
    }
    if (start !== null && start <= T) helped++;
    if (c.abandoned[i] && (c.abandon_at[i] ?? Infinity) <= T) gaveUp++;
    if (arrival + threshold <= T) {
      due++;
      if (start !== null && start - arrival <= threshold) inTime++;
    }
  }
  // The desks: every agent whose shift covers this hour, or who is still finishing a conversation.
  const desks: Desk[] = floor.agents
    .filter((a) => (a.duty ? a.duty[hour] : false) || servingBy.has(a.agent_id))
    .map((a) => {
      const serving = servingBy.get(a.agent_id) ?? null;
      return { agentId: a.agent_id, skill: a.primary_group, serving, live: serving !== null && (!c.live || c.live[serving]) };
    });
  queue.sort((x, y) => c.arrival[x] - c.arrival[y]);
  const busy = talking.size + onMessages.size;
  return {
    t: T,
    desks,
    queue,
    onDuty: desks.length,
    busy,
    busyLive: talking.size,
    busyMessages: onMessages.size,
    waiting,
    waitingLong,
    helped,
    gaveUp,
    arrived,
    onTime: due ? inTime / due : null,
    cost: costSoFar(floor, T, gaveUp),
  };
}

/** The counts, recomputed when the clock moves by 20 simulated seconds or more. */
export function useFloorStats(floor: Floor | null | undefined, t: number): FloorStats | null {
  const step = Math.round(t / 20);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => (floor ? floorStats(floor, t) : null), [floor, step]);
}

// ------------------------------------------------------------------- the story
export interface Story {
  kind: string; // the type of moment: the caption animates only when it changes
  text: string;
}

/** The caption of a single floor, from its numbers at this moment. */
export function storyOne(floor: Floor, s: FloorStats, peakT: number): Story {
  const [open, close] = floor.opening_hours;
  const T = s.t;
  const threshold = floor.threshold_seconds;
  if (T >= close * 3600) {
    const share = s.arrived ? Math.round((100 * s.gaveUp) / s.arrived) : 0;
    return {
      kind: "end",
      text: `The day is over: ${num(s.helped, 0)} customers helped, ${num(s.gaveUp, 0)} gave up (${share} out of 100). The day cost ${euros(s.cost)}.`,
    };
  }
  if (T < open * 3600 + 15 * 60) {
    return { kind: "open", text: `${hhmm(open * 3600)}: the centre opens with ${s.onDuty} agents. The first customers arrive.` };
  }
  if (s.waiting > 0 && s.busyMessages >= Math.max(1, s.onDuty / 2)) {
    return {
      kind: "messages",
      text: `Morning rush: ${s.busyMessages} of ${s.onDuty} agents are still answering last night's messages, so new customers have to wait.`,
    };
  }
  if (s.waitingLong >= 3) {
    return {
      kind: "short",
      text: `Not enough agents right now: ${s.waitingLong} customers have waited more than ${threshold} seconds. After about 3 minutes, people give up.`,
    };
  }
  if (Math.abs(T - (peakT + 900)) < 1800) {
    return { kind: "peak", text: `Busiest moment of the day: ${s.busy} of ${s.onDuty} agents are talking to customers.` };
  }
  if (s.waiting > 0 && s.busy >= s.onDuty) {
    return { kind: "full", text: `All ${s.onDuty} agents are busy: new customers have to wait their turn.` };
  }
  return { kind: "calm", text: `The agents keep up: customers are answered within seconds (${s.busy} of ${s.onDuty} agents busy).` };
}

/** The caption of the side-by-side view: what differs between the left and the right floor right now. */
export function storyTwo(floor: Floor, a: FloorStats, b: FloorStats): Story {
  const [open, close] = floor.opening_hours;
  const T = a.t;
  if (T >= close * 3600) {
    const kept = a.gaveUp - b.gaveUp;
    const saved = (a.cost ?? 0) - (b.cost ?? 0);
    const who = kept >= 0 ? "right" : "left";
    const money = (kept >= 0 ? saved : -saved) >= 0 ? `the day cost ${euros(Math.abs(saved))} less` : `the day cost ${euros(Math.abs(saved))} more`;
    return { kind: "end", text: `The day is over: the ${who} side kept ${num(Math.abs(kept), 0)} more customers, and ${money}.` };
  }
  if (T < open * 3600 + 15 * 60) {
    return {
      kind: "open",
      text: `The same customers arrive on both sides. Only the staffing differs: ${a.onDuty} agents on the left, ${b.onDuty} on the right.`,
    };
  }
  const lost = a.gaveUp - b.gaveUp;
  if (Math.abs(lost) >= 10) {
    const [worse, better, x, y] = lost > 0 ? ["left", "right", a.gaveUp, b.gaveUp] : ["right", "left", b.gaveUp, a.gaveUp];
    return {
      kind: `lose-${worse}`,
      text: `The ${worse} side is losing customers: ${num(x as number, 0)} have already given up, against ${num(y as number, 0)} on the ${better}.`,
    };
  }
  const wait = a.waitingLong - b.waitingLong;
  if (Math.abs(wait) >= 3) {
    const [worse, better] = wait > 0 ? ["left", "right"] : ["right", "left"];
    return { kind: `wait-${worse}`, text: `Customers wait too long on the ${worse}; on the ${better} they are answered quickly.` };
  }
  return {
    kind: "even",
    text: `Both sides keep up for now: ${a.busy} of ${a.onDuty} agents busy on the left, ${b.busy} of ${b.onDuty} on the right.`,
  };
}

/** The caption bar: a speech bubble whose text slides in when the moment changes. */
export function StoryLine({ story }: { story: Story }) {
  return (
    <div
      className="flex min-h-[52px] items-center gap-3 rounded-2xl px-4 py-3 text-[15px] leading-snug text-ink"
      style={{ background: "color-mix(in srgb, var(--brand) 10%, transparent)" }}
      role="status"
      aria-live="polite"
    >
      <MessageCircle size={20} className="shrink-0 text-brand" aria-hidden />
      <AnimatePresence mode="wait">
        <motion.span key={story.kind} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.25 }}>
          {story.text}
        </motion.span>
      </AnimatePresence>
    </div>
  );
}

// ------------------------------------------------------------------- pictures
/** The time of day, big, next to play / pause / jump to the peak / speed / slider. */
export function ClockBar({ clock, peakT }: { clock: FloorClock; peakT: number }) {
  return (
    <div className="flex flex-wrap items-center gap-4">
      <div className="font-display text-4xl font-semibold tabular text-ink">{hhmm(clock.t)}</div>
      <div className="min-w-[300px] flex-1">
        <FloorControls clock={clock} peakT={peakT} />
      </div>
    </div>
  );
}

const MAX_QUEUE = 30; // more waiting customers than this becomes "+N"

/** The colour of a problem group: the same fixed colours as everywhere in CallVerse. */
export const groupColor = (group: string | null | undefined) =>
  `var(--series-${Math.max(0, (GROUPS as readonly string[]).indexOf(group ?? "")) + 1})`;
// Exit colours (an animation cannot start from a CSS variable): gave up = red, helped and done = green.
const GONE_RED = "#dc2626";
const DONE_GREEN = "#16a34a";
const SLIDE = { type: "spring", stiffness: 320, damping: 32 } as const;

/**
 * One floor in pictures: the waiting line (people coloured by problem), the desks (border = speciality,
 * colour = the case being handled), helped vs gave up, on time and cost. Each customer has a layoutId, so the
 * same person slides from the line to the desk of the agent who takes it.
 */
export function SimpleFloorCard({
  floor,
  floorKey,
  stats,
  title,
  decision,
  highlight = false,
}: {
  floor: Floor;
  floorKey: string;
  stats: FloorStats;
  title?: ReactNode;
  decision: string;
  highlight?: boolean;
}) {
  const c = floor.contacts;
  const threshold = floor.threshold_seconds;
  const shown = stats.queue.slice(0, MAX_QUEUE);
  return (
    <div className={clsx("card space-y-4 p-5", highlight && "ring-2 ring-[var(--good)]")}>
      <div>
        {title && <div className="text-xs font-semibold uppercase tracking-wider text-muted">{title}</div>}
        <div className="font-display text-lg font-semibold text-ink">{decision}</div>
      </div>
      {/* layoutId names are local to this floor (two floors side by side share contact positions). */}
      <LayoutGroup id={floorKey}>
        {/* The waiting line, the longest waiting first; a red bar = waiting longer than the threshold. */}
        <div>
          <div className="mb-1.5 text-sm text-ink2">
            Waiting line: <b className="text-ink">{stats.waiting}</b> {stats.waiting === 1 ? "customer" : "customers"}
            {stats.waitingLong > 0 && <span style={{ color: "var(--critical)" }}> · {stats.waitingLong} waiting more than {threshold} s</span>}
          </div>
          <div className="flex min-h-[34px] flex-wrap items-start gap-1">
            <AnimatePresence initial={false} mode="popLayout">
              {shown.map((i) => {
                const late = stats.t - c.arrival[i] > threshold;
                // The simulation knows the end: a customer who will be answered leaves at once (the same
                // person then slides to the desk); one who gives up drops out in red.
                const exit = c.abandoned[i]
                  ? { opacity: 0, y: 24, color: GONE_RED, transition: { duration: 0.6 } }
                  : { opacity: 0, transition: { duration: 0 } };
                return (
                  <motion.div
                    key={i}
                    layoutId={`c${i}`}
                    className="flex flex-col items-center"
                    style={{ color: groupColor(c.group[i]) }}
                    initial={{ opacity: 0, x: -14 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={exit}
                    transition={SLIDE}
                    title={`${GROUP_LABEL[c.group[i]] ?? c.group[i]}: waiting for ${Math.round(stats.t - c.arrival[i])} s`}
                  >
                    <User size={22} aria-hidden />
                    <span className="mt-0.5 h-1 w-4 rounded-full" style={{ background: late ? "var(--critical)" : "transparent" }} />
                  </motion.div>
                );
              })}
            </AnimatePresence>
            {stats.waiting > MAX_QUEUE && <span className="self-center text-sm text-muted">+{stats.waiting - MAX_QUEUE}</span>}
            {stats.waiting === 0 && <span className="self-center text-sm text-muted">Nobody is waiting</span>}
          </div>
        </div>
        {/* The desks: one per agent at work. */}
        <div>
          <div className="mb-1.5 text-sm text-ink2">
            <b className="text-ink">{stats.onDuty}</b> agents at work · <b className="text-ink">{stats.busyLive}</b> talking to a customer
            {stats.busyMessages > 0 && (
              <>
                {" "}· <b className="text-ink">{stats.busyMessages}</b> answering last night's messages
              </>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {stats.desks.map((desk) => (
              <DeskTile key={desk.agentId} desk={desk} floor={floor} />
            ))}
            {stats.desks.length === 0 && <span className="text-sm text-muted">No agent at work</span>}
          </div>
        </div>
      </LayoutGroup>
      {/* The two numbers that matter. */}
      <div className="grid grid-cols-2 gap-3">
        <BigCount icon={<UserCheck size={16} aria-hidden />} label="Helped" value={stats.helped} color="var(--good-text)" />
        <BigCount icon={<UserX size={16} aria-hidden />} label="Gave up" value={stats.gaveUp} color="var(--critical)" />
      </div>
      <div className="flex flex-wrap justify-between gap-2 text-sm text-ink2">
        <span>
          Answered within {threshold} s: <b className="text-ink">{stats.onTime == null ? "–" : `${Math.round(stats.onTime * 100)}%`}</b>
        </span>
        <span>
          Cost so far: <b className="text-ink">{euros(stats.cost)}</b>
        </span>
      </div>
    </div>
  );
}

/**
 * One agent's desk: the border is the agent's speciality, the fill is the problem of the case being handled;
 * inside, the customer (who slid here from the line) or an envelope for a message left overnight.
 */
function DeskTile({ desk, floor }: { desk: Desk; floor: Floor }) {
  const c = floor.contacts;
  const busy = desk.serving !== null;
  const caseGroup = busy ? c.group[desk.serving as number] : null;
  const now = busy
    ? `now: ${desk.live ? "a customer" : "a message left overnight"} about "${GROUP_LABEL[caseGroup ?? ""] ?? caseGroup}"`
    : "free";
  return (
    <div
      className="flex h-[60px] w-[60px] flex-col items-center justify-center gap-0.5 rounded-xl border-2 transition-colors duration-300"
      style={{
        borderColor: groupColor(desk.skill),
        background: busy ? `color-mix(in srgb, ${groupColor(caseGroup)} 26%, transparent)` : "transparent",
      }}
      title={`Agent ${desk.agentId} · speciality: ${GROUP_LABEL[desk.skill] ?? desk.skill} · ${now}`}
    >
      <Headset size={15} style={{ color: busy ? "var(--text-primary)" : "var(--text-muted)" }} aria-hidden />
      <div className="flex h-[22px] items-center justify-center">
        <AnimatePresence initial={false} mode="popLayout">
          {busy && desk.live && (
            <motion.div
              key={desk.serving}
              layoutId={`c${desk.serving}`}
              style={{ color: groupColor(caseGroup) }}
              exit={{ opacity: 0, y: -16, color: DONE_GREEN, transition: { duration: 0.5 } }}
              transition={SLIDE}
            >
              <User size={20} aria-hidden />
            </motion.div>
          )}
          {busy && !desk.live && (
            <motion.div key={`m${desk.serving}`} initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}>
              <Mail size={18} style={{ color: groupColor(caseGroup) }} aria-hidden />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function BigCount({ icon, label, value, color }: { icon: ReactNode; label: string; value: number; color: string }) {
  return (
    <div className="rounded-xl px-3 py-2.5" style={{ background: `color-mix(in srgb, ${color} 12%, transparent)` }}>
      <div className="flex items-center gap-1.5 text-xs font-semibold" style={{ color }}>
        {icon} {label}
      </div>
      <div className="font-display text-2xl font-semibold tabular" style={{ color }}>
        {num(value, 0)}
      </div>
    </div>
  );
}

export interface BarRow {
  label: string;
  value: number;
  display: string;
  tone: "good" | "bad" | "neutral";
}

const TONE: Record<BarRow["tone"], string> = { good: "var(--good)", bad: "var(--critical)", neutral: "var(--brand)" };

/** Horizontal bars that grow with their value (the longest = 100%). */
export function RaceBars({ title, rows }: { title: string; rows: BarRow[] }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div>
      <div className="mb-2 text-sm font-semibold text-ink">{title}</div>
      <div className="space-y-2">
        {rows.map((row) => (
          <div key={row.label} className="grid grid-cols-[minmax(90px,30%)_1fr_auto] items-center gap-3 text-sm">
            <span className="truncate text-ink2" title={row.label}>{row.label}</span>
            <div className="h-3.5 overflow-hidden rounded-full bg-raised">
              <div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${(100 * row.value) / max}%`, background: TONE[row.tone] }} />
            </div>
            <span className="w-20 text-right font-semibold tabular text-ink">{row.display}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** What the pictures mean: the four problem colours, then the desks and the waiting line. */
export function SimpleLegend({ threshold }: { threshold: number }) {
  return (
    <div className="space-y-1.5 text-xs text-ink2">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
        <span className="font-semibold text-ink">Customer problem:</span>
        {GROUPS.map((g) => (
          <span key={g} className="inline-flex items-center gap-1">
            <User size={15} style={{ color: groupColor(g) }} aria-hidden /> {GROUP_LABEL[g]}
          </span>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
        <span>Desk border = the agent's speciality · desk colour = the problem being handled</span>
        <span className="inline-flex items-center gap-1"><Mail size={14} aria-hidden /> a message left overnight</span>
        <span className="inline-flex items-center gap-1">
          <span className="h-1 w-4 rounded-full" style={{ background: "var(--critical)" }} /> waiting more than {threshold} s
        </span>
        <span>Customers who wait about 3 minutes give up and leave.</span>
      </div>
    </div>
  );
}

// -------------------------------------------------------------- whole views
/** Live floor tab, simple view: the clock, the story, the floor in pictures, and helped vs gave up. */
export function SimpleSingleFloor({ floor, decision }: { floor: Floor; decision: string }) {
  const [open, close] = floor.opening_hours;
  const clock = useFloorClock(open, close);
  useEffect(() => {
    clock.restart();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [floor]);
  const stats = useFloorStats(floor, clock.t);
  const peakT = useMemo(() => busiestHalfHour(waitingSeries(floor)).t, [floor]);
  if (!stats) return null;
  return (
    <div className="space-y-4">
      <ClockBar clock={clock} peakT={peakT} />
      <StoryLine story={storyOne(floor, stats, peakT)} />
      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <SimpleFloorCard floor={floor} floorKey="floor" stats={stats} decision={decision} />
        <div className="card space-y-5 p-5">
          <RaceBars
            title="Customers so far today"
            rows={[
              { label: "Helped", value: stats.helped, display: num(stats.helped, 0), tone: "good" },
              { label: "Gave up", value: stats.gaveUp, display: num(stats.gaveUp, 0), tone: "bad" },
            ]}
          />
          <p className="text-sm leading-relaxed text-ink2">
            {num(floor.summary.contacts, 0)} customers will contact the centre today. Watch the red counter: every customer who gives up
            is a lost sale and an unhappy client.
          </p>
        </div>
      </div>
      <SimpleLegend threshold={floor.threshold_seconds} />
    </div>
  );
}

/** Side by side tab, simple view: the same customers, two decisions, one clock. */
export function SimpleSideBySide({
  left,
  right,
  leftName,
  rightName,
  clock,
  peakT,
}: {
  left: Floor;
  right: Floor;
  leftName: string;
  rightName: string;
  clock: FloorClock;
  peakT: number;
}) {
  const a = useFloorStats(left, clock.t);
  const b = useFloorStats(right, clock.t);
  if (!a || !b) return null;
  const over = clock.t >= left.opening_hours[1] * 3600;
  const leftBetter = a.gaveUp <= b.gaveUp;
  return (
    <div className="space-y-4">
      <ClockBar clock={clock} peakT={peakT} />
      <StoryLine story={storyTwo(left, a, b)} />
      <div className="grid gap-5 lg:grid-cols-2">
        <SimpleFloorCard floor={left} floorKey="left" stats={a} title="Left" decision={leftName} highlight={over && a.gaveUp < b.gaveUp} />
        <SimpleFloorCard floor={right} floorKey="right" stats={b} title="Right" decision={rightName} highlight={over && b.gaveUp < a.gaveUp} />
      </div>
      <div className="card grid gap-6 p-5 md:grid-cols-2">
        <RaceBars
          title="Customers lost so far"
          rows={[
            { label: "Left", value: a.gaveUp, display: num(a.gaveUp, 0), tone: leftBetter ? "good" : "bad" },
            { label: "Right", value: b.gaveUp, display: num(b.gaveUp, 0), tone: leftBetter ? "bad" : "good" },
          ]}
        />
        <RaceBars
          title="Cost so far (wages + lost customers)"
          rows={[
            { label: "Left", value: a.cost ?? 0, display: euros(a.cost), tone: "neutral" },
            { label: "Right", value: b.cost ?? 0, display: euros(b.cost), tone: "neutral" },
          ]}
        />
      </div>
      <SimpleLegend threshold={left.threshold_seconds} />
    </div>
  );
}

// ---------------------------------------------------------------- Scenario lab
/** "Out of 100 customers": 100 little people, coloured by what happened to them. */
export function HundredCustomers({ onTime, gaveUp }: { onTime: number; gaveUp: number }) {
  const green = Math.round(onTime * 100);
  const red = Math.min(100 - green, Math.round(gaveUp * 100));
  const amber = 100 - green - red;
  return (
    <div>
      <div className="grid w-fit grid-cols-[repeat(20,minmax(0,1fr))] gap-0.5" role="img" aria-label={`Out of 100 customers: ${green} answered on time, ${amber} answered late, ${red} gave up`}>
        {Array.from({ length: 100 }, (_, i) => (
          <User key={i} size={18} style={{ color: i < green ? "var(--good)" : i < green + amber ? "var(--warning)" : "var(--critical)" }} aria-hidden />
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink2">
        <Dot color="var(--good)" text={`${green} answered within 20 s`} />
        <Dot color="var(--warning)" text={`${amber} answered, but later`} />
        <Dot color="var(--critical)" text={`${red} gave up`} />
      </div>
    </div>
  );
}

function Dot({ color, text }: { color: string; text: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} /> {text}
    </span>
  );
}

/** One what-if run, in plain words: out of 100 customers, and what the week costs (with its range). */
export function SimpleRunResult({ kpis, seeds, decision }: { kpis: Record<string, any>; seeds: number; decision: string }) {
  const sl = kpis.service_level;
  const ab = kpis.abandon_rate;
  const cost = kpis.total_cost_eur;
  if (!sl || !ab || !cost) return null;
  const range = (k: any, f: (v: number) => string) => `between ${f(k.ci_low)} and ${f(k.ci_high)} over ${seeds} simulated weeks`;
  const per100 = (v: number) => `${Math.round(v * 100)}`;
  return (
    <div className="card space-y-5 p-6">
      <div>
        <div className="text-xs font-semibold uppercase tracking-wider text-muted">{decision}</div>
        <p className="mt-1 text-lg leading-snug text-ink">
          Out of every 100 customers, <b style={{ color: "var(--good-text)" }}>{per100(sl.mean)}</b> are answered within 20 seconds and{" "}
          <b style={{ color: "var(--critical)" }}>{per100(ab.mean)}</b> give up. The week costs about <b>{euros(cost.mean)}</b>.
        </p>
      </div>
      <HundredCustomers onTime={sl.mean} gaveUp={ab.mean} />
      <div className="grid gap-3 sm:grid-cols-3">
        <PlainTile label="Answered on time" value={`${per100(sl.mean)} of 100`} hint={range(sl, per100)} color="var(--good-text)" />
        <PlainTile label="Gave up" value={`${per100(ab.mean)} of 100`} hint={range(ab, per100)} color="var(--critical)" />
        <PlainTile label="Cost of the week" value={euros(cost.mean)} hint={range(cost, euros)} />
      </div>
      <p className="text-xs text-muted">Cost = agents' wages (overtime at 1.5×) + €8 for each customer who gives up.</p>
    </div>
  );
}

function PlainTile({ label, value, hint, color }: { label: string; value: string; hint: string; color?: string }) {
  return (
    <div className="rounded-xl bg-raised p-4">
      <div className="text-xs font-semibold text-muted">{label}</div>
      <div className="font-display text-2xl font-semibold tabular" style={{ color: color ?? "var(--text-primary)" }}>{value}</div>
      <div className="mt-1 text-xs text-ink2">{hint}</div>
    </div>
  );
}

/** The plain name of a compared option ("cpsat | fifo | unprepared"). */
export function optionPlain(option: string, scenario: any): string {
  const [plan, router, prepared] = option.split(" | ");
  const sources = planSourcePlain(scenario);
  const source = prepared === "prepared" ? sources.prepared : sources.unprepared;
  const routing = router && router !== "fifo" ? `, ${ROUTER_PLAIN[router] ?? router}` : "";
  return `${PLAN_PLAIN[plan] ?? plan} · ${source.toLowerCase()}${routing}`;
}

/** Four decisions on the same customers: who loses the fewest customers, and who costs the least. */
export function SimpleCompareResult({ summary, scenario }: { summary: any[]; scenario: any }) {
  const options = Array.from(new Set(summary.map((r) => r.option as string)));
  const value = (option: string, kpi: string) => Number(summary.find((r) => r.option === option && r.kpi === kpi)?.mean ?? 0);
  const rows = options.map((o) => ({ option: o, name: optionPlain(o, scenario), lost: value(o, "abandon_rate"), onTime: value(o, "service_level"), cost: value(o, "total_cost_eur") }));
  const kindest = [...rows].sort((x, y) => x.lost - y.lost)[0];
  const cheapest = [...rows].sort((x, y) => x.cost - y.cost)[0];
  return (
    <div className="card space-y-6 p-6">
      <p className="text-lg leading-snug text-ink">
        <Trophy size={18} className="mr-1.5 inline text-brand" aria-hidden />
        Fewest customers lost: <b>{kindest.name}</b> ({Math.round(kindest.lost * 100)} of 100 give up). Cheapest week: <b>{cheapest.name}</b> ({euros(cheapest.cost)}).
      </p>
      <RaceBars
        title="Customers who give up, out of 100"
        rows={rows.map((r) => ({ label: r.name, value: r.lost, display: `${Math.round(r.lost * 100)}`, tone: r === kindest ? "good" : "bad" }))}
      />
      <RaceBars
        title="Cost of the week (wages + lost customers)"
        rows={rows.map((r) => ({ label: r.name, value: r.cost, display: euros(r.cost), tone: r === cheapest ? "good" : "neutral" }))}
      />
      <p className="text-xs text-muted">Same simulated customers for every decision, averaged over several simulated weeks.</p>
    </div>
  );
}
