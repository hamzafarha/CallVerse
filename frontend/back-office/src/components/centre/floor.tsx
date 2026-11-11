/**
 * The contact centre's room, drawn on a fixed 1600 x 900 stage that the page scales to the screen:
 *
 * - the walls and the floor (one SVG): entrance, waiting area, advisors' area, supervisor's office, quality
 *   corner and the frame of the KPI wall;
 * - the furniture with people at it: the reception counter (receptionist = Workforce agent) and the advisors'
 *   desks (advisor = Advisor agent). A desk is a button: it opens that advisor's history;
 * - the people who walk (customers, supervisor, quality lead), the speech bubbles and the tool badges;
 * - the positions where people stand and the walkways they follow (so nobody walks through a desk).
 *
 * Depth: everything that stands on the floor gets a z-index equal to the y of its feet, so a person in front
 * of a desk (lower on the screen) is drawn over it, like in a real room.
 */
import { AnimatedNumber, CALLER_LABEL, TOOL_LABEL, TypingDots, clsx, num } from "@callverse/shared";
import { AnimatePresence, motion } from "framer-motion";
import {
  BookOpen,
  Camera,
  CheckCircle2,
  Clock,
  Gavel,
  History,
  Landmark,
  LifeBuoy,
  Package,
  Scale,
  ShieldCheck,
  Smartphone,
  Ticket,
  UserRoundSearch,
  Volume2,
  Wrench,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { type CSSProperties, useLayoutEffect, useRef, useState } from "react";
import { Person, Portrait, ROLE, STAFF_LOOK, advisorName, lookFor, type Look, type Pose, type Role } from "./people";

// -------------------------------------------------------------------------- the stage
export const STAGE_W = 1600;
export const STAGE_H = 900;
const WALL_Y = 236; // where the back wall meets the floor
export const PERSON_H = 140; // height of a standing person
const SEATED_H = 150; // advisors and the receptionist (their desk hides the legs)

export interface Point {
  x: number;
  y: number;
}

// Where people stand (the point under their feet) and the walkways between the areas.
export const DOOR: Point = { x: 120, y: 250 };
export const LOBBY: Point = { x: 150, y: 665 };
export const RECEPTION: Point = { x: 330, y: 500 }; // the receptionist, behind the counter
export const RECEPTION_FRONT: Point = { x: 390, y: 665 }; // where a new customer explains the problem
export const AISLE_X = 480; // walkway between the reception and the desks
export const STAFF_AISLE_X = 1255; // walkway between the desks and the supervisor's office
export const SUPERVISOR_HOME: Point = { x: 1440, y: 440 };
export const QUALITY_HOME: Point = { x: 1440, y: 800 };
const MANAGER_SPOT: Point = { x: 1250, y: 335 };
export const DESK_COUNT = 8;
const COLUMNS = [620, 790, 960, 1130];
const ROWS = [330, 600];

/** The middle of a desk's top (desks 0-3 on the first row, 4-7 on the second). */
export const deskCentre = (slot: number): Point => ({ x: COLUMNS[slot % 4], y: ROWS[Math.floor(slot / 4) % 2] });
/** An advisor handles up to two chats at once (like real chat agents): two places in front of each desk. */
export const DESK_CAPACITY = 2;
/** Where a customer stands, in front of the desk: place 0 on the left, place 1 on the right. */
export const deskFront = (slot: number, place = 0): Point =>
  place === 0 ? { x: deskCentre(slot).x - 40, y: deskCentre(slot).y + 175 } : { x: deskCentre(slot).x + 42, y: deskCentre(slot).y + 178 };
/** Where the supervisor or the quality lead stands: behind the desk, next to the advisor. */
export const deskSupport = (slot: number): Point => ({ x: deskCentre(slot).x - 62, y: deskCentre(slot).y + 42 });
/** The waiting area: the three chairs, then a line of people standing next to them. */
export const WAITING_SPOTS: Point[] = [68, 140, 212, 284, 356, 428].map((x) => ({ x, y: 872 }));

// ---------------------------------------------------------------------------- room
/** Walls, floor and the areas of the centre (one SVG, behind everything). */
export function Room() {
  const label = { fontSize: 13, fontWeight: 700, letterSpacing: 1.6 } as const;
  return (
    <svg viewBox={`0 0 ${STAGE_W} ${STAGE_H}`} width={STAGE_W} height={STAGE_H} className="absolute left-0 top-0" aria-hidden>
      <defs>
        <pattern id="cv-tiles" width="80" height="80" patternUnits="userSpaceOnUse">
          <path d="M 80 0 L 0 0 0 80" fill="none" stroke="var(--hairline)" strokeWidth="1.5" />
        </pattern>
        <linearGradient id="cv-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#7dd3fc" />
          <stop offset="1" stopColor="#e0f2fe" />
        </linearGradient>
      </defs>
      {/* Back wall, floor tiles and skirting board. */}
      <rect x={0} y={0} width={STAGE_W} height={WALL_Y} fill="var(--surface-3)" />
      <rect x={0} y={WALL_Y} width={STAGE_W} height={STAGE_H - WALL_Y} fill="var(--surface-2)" />
      <rect x={0} y={WALL_Y} width={STAGE_W} height={STAGE_H - WALL_Y} fill="url(#cv-tiles)" />
      <rect x={0} y={WALL_Y - 7} width={STAGE_W} height={7} fill="var(--baseline)" />

      {/* Entrance: customers come in and leave through this door. */}
      <text x={120} y={50} textAnchor="middle" fill="var(--text-secondary)" {...label}>
        ENTRANCE
      </text>
      <rect x={70} y={62} width={100} height={WALL_Y - 62} rx={6} fill="var(--surface-1)" stroke="var(--baseline)" strokeWidth={3} />
      <rect x={84} y={78} width={72} height={84} rx={4} fill="url(#cv-sky)" opacity={0.65} />
      <circle cx={152} cy={170} r={4.5} fill="var(--text-muted)" />

      {/* The centre's name on the wall. */}
      <text x={345} y={112} textAnchor="middle" className="font-display" fontSize={38} fontWeight={700} fill="var(--text-primary)">
        CallVerse
      </text>
      <text x={345} y={146} textAnchor="middle" fontSize={17} fill="var(--text-secondary)">
        Contact centre · live
      </text>

      {/* Two windows above the supervisor's office. */}
      {[1290, 1445].map((x) => (
        <g key={x}>
          <rect x={x} y={40} width={125} height={140} rx={8} fill="url(#cv-sky)" stroke="var(--baseline)" strokeWidth={4} />
          <path d={`M ${x + 62.5} 40 V 180 M ${x} 110 H ${x + 125}`} stroke="var(--baseline)" strokeWidth={4} />
        </g>
      ))}

      {/* Areas on the floor. */}
      <rect x={530} y={250} width={700} height={610} rx={24} fill="var(--brand-soft)" />
      <text x={552} y={846} fill="var(--brand)" {...label}>
        ADVISORS · click a desk to see its chats
      </text>
      <rect x={1300} y={250} width={285} height={250} rx={18} fill="rgba(147,197,253,0.10)" stroke="rgba(96,165,250,0.65)" strokeWidth={3} />
      <text x={1318} y={278} fill="#3b82f6" {...label}>
        SUPERVISOR
      </text>
      <rect x={1478} y={330} width={92} height={38} rx={6} fill="#d9b48f" stroke="#a47c52" strokeWidth={2} />
      <rect x={1300} y={540} width={285} height={335} rx={18} fill="rgba(245,158,11,0.08)" stroke="rgba(245,158,11,0.55)" strokeWidth={3} strokeDasharray="10 8" />
      <text x={1318} y={568} fill="#d97706" {...label}>
        QUALITY
      </text>
      <rect x={1478} y={690} width={92} height={38} rx={6} fill="#d9b48f" stroke="#a47c52" strokeWidth={2} />
      <rect x={1490} y={680} width={26} height={16} rx={2} fill="#fef9c3" stroke="#a16207" strokeWidth={1.5} />
      <rect x={1524} y={676} width={26} height={20} rx={2} fill="#fef9c3" stroke="#a16207" strokeWidth={1.5} />

      {/* Waiting area: three chairs. */}
      <text x={40} y={716} fill="var(--text-secondary)" {...label}>
        WAITING AREA
      </text>
      {[40, 112, 184].map((x) => (
        <g key={x}>
          <rect x={x} y={776} width={56} height={22} rx={8} fill="#94a3b8" />
          <rect x={x + 4} y={796} width={48} height={30} rx={8} fill="#64748b" />
        </g>
      ))}

      {/* Plants. */}
      {[
        { x: 498, y: WALL_Y + 6 },
        { x: 1270, y: 880 },
      ].map(({ x, y }) => (
        <g key={x}>
          <circle cx={x - 12} cy={y - 50} r={16} fill="#22c55e" />
          <circle cx={x + 12} cy={y - 54} r={17} fill="#16a34a" />
          <circle cx={x} cy={y - 70} r={16} fill="#4ade80" />
          <path d={`M ${x - 16} ${y - 36} H ${x + 16} L ${x + 12} ${y} H ${x - 12} Z`} fill="#b45309" />
        </g>
      ))}

      {/* The KPI wall's frame (a screen on the wall; its numbers are drawn by KpiWall). */}
      <rect x={520} y={18} width={680} height={190} rx={16} fill="#0b1020" stroke="#334155" strokeWidth={5} />
    </svg>
  );
}

// ------------------------------------------------------------------- tools and dots
/** An icon for each tool of the Advisor agent and of the Client agent (the customer's phone). */
const TOOL_ICON: Record<string, LucideIcon> = {
  lookup_order: Package,
  get_ticket_history: History,
  get_customer_history: UserRoundSearch,
  check_refund_eligibility: Scale,
  recommend_resolution: Gavel,
  validate_bank_code: Landmark,
  open_ticket: Ticket,
  escalate_to_human: LifeBuoy,
  search_knowledge_base: BookOpen,
  check_draft_reply: ShieldCheck,
  view_my_order_page: Smartphone,
  check_my_waiting_time: Clock,
  send_evidence: Camera,
};

export interface ToolPop {
  key: string;
  name: string;
  ok: boolean;
  caller?: string;
}

/** The last tools used, as small labels that pop up next to the person (the newest at the bottom). */
function ToolStack({ pops, style }: { pops: ToolPop[]; style: CSSProperties }) {
  return (
    <div className="pointer-events-none absolute flex flex-col gap-1" style={style}>
      <AnimatePresence initial={false}>
        {pops.map((pop) => {
          const Icon = TOOL_ICON[pop.name] ?? Wrench;
          return (
            <motion.div
              key={pop.key}
              layout
              initial={{ opacity: 0, scale: 0.6, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.8 }}
              transition={{ type: "spring", stiffness: 420, damping: 26 }}
              className="flex w-max items-center gap-1 rounded-full border-2 bg-surface px-2 py-0.5 text-[11.5px] font-semibold text-ink shadow-soft"
              style={{ borderColor: pop.ok ? "var(--good)" : "var(--critical)" }}
              title={`${TOOL_LABEL[pop.name] ?? pop.name} · ${CALLER_LABEL[pop.caller ?? ""] ?? "tool call"}`}
            >
              <Icon size={13} aria-hidden />
              {TOOL_LABEL[pop.name] ?? pop.name}
              {pop.ok ? <CheckCircle2 size={12} color="var(--good)" aria-hidden /> : <XCircle size={12} color="var(--critical)" aria-hidden />}
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

/** "..." above a person who is thinking or typing. */
function Dots({ style }: { style: CSSProperties }) {
  return (
    <div className="pointer-events-none absolute flex h-6 -translate-x-1/2 items-center rounded-full bg-surface px-2.5 text-ink2 shadow-soft" style={style}>
      <TypingDots />
    </div>
  );
}

// ------------------------------------------------------------------ people at furniture
/** The reception counter with the receptionist (the Workforce agent) behind it. */
export function ReceptionUnit({ pose, thinking }: { pose: Pose; thinking: boolean }) {
  return (
    <div className="absolute" style={{ left: RECEPTION.x - 115, top: RECEPTION.y - 160, width: 230, height: 165, zIndex: RECEPTION.y }}>
      <Person role="reception" look={STAFF_LOOK.reception} height={SEATED_H} pose={pose} title="Receptionist: the Workforce agent" style={{ position: "absolute", left: 115 - SEATED_H / 4, top: 10 }} />
      {thinking && <Dots style={{ left: 115, top: -14 }} />}
      <svg width={230} height={165} viewBox="0 0 230 165" className="pointer-events-none absolute left-0 top-0">
        <rect x={10} y={100} width={210} height={16} rx={6} fill="#f1f5f9" stroke="#94a3b8" strokeWidth={2} />
        <rect x={16} y={114} width={198} height={46} rx={6} fill="#e2e8f0" stroke="#94a3b8" strokeWidth={2} />
        <rect x={17} y={122} width={196} height={7} fill={ROLE.reception.color} />
        <text x={115} y={150} textAnchor="middle" fontSize={12.5} fontWeight={700} fill="#0f766e">
          RECEPTION · Workforce agent
        </text>
      </svg>
    </div>
  );
}

export interface DeskStats {
  chats: number;
  quality: number | null;
}

/** One advisor's desk: the advisor (Advisor agent) sits behind it. Clicking it opens the advisor's history. */
export function DeskUnit({
  slot,
  advisorId,
  stats,
  busy,
  thinking,
  tools,
  onOpen,
}: {
  slot: number;
  advisorId: string;
  stats: DeskStats | null;
  busy: boolean;
  thinking: boolean;
  tools: ToolPop[];
  onOpen: (advisorId: string) => void;
}) {
  const c = deskCentre(slot);
  const name = advisorName(advisorId);
  const score = stats?.quality != null ? `★ ${num(stats.quality, 1)} · ${stats.chats} chat${stats.chats === 1 ? "" : "s"}` : "no chat yet";
  return (
    <button
      type="button"
      onClick={() => onOpen(advisorId)}
      className="group absolute rounded-2xl outline-none focus-visible:ring-4 focus-visible:ring-[var(--brand)]"
      style={{ left: c.x - 90, top: c.y - 100, width: 180, height: 165, zIndex: c.y + 62 }}
      title={`Desk ${slot + 1}: ${name} (${advisorId}). Click to see the chats and their Quality scores.`}
      aria-label={`Desk ${slot + 1}, ${name}: see the chats and their Quality scores`}
    >
      <span className="absolute inset-x-1 -top-2 bottom-0 rounded-2xl opacity-0 transition-opacity group-hover:opacity-100" style={{ background: "color-mix(in srgb, var(--brand) 16%, transparent)" }} />
      <Person role="advisor" look={lookFor(advisorId)} height={SEATED_H} title={`${name}: Advisor agent`} style={{ position: "absolute", left: 90 - SEATED_H / 4, top: 0 }} />
      <svg width={180} height={165} viewBox="0 0 180 165" className="pointer-events-none absolute left-0 top-0">
        {/* Screen: blue while the desk serves a customer. */}
        <rect x={116} y={48} width={48} height={33} rx={4} fill="#1f2937" />
        <rect x={119} y={51} width={42} height={27} rx={2} fill={busy ? "#38bdf8" : "#64748b"} />
        <rect x={137} y={81} width={6} height={10} fill="#1f2937" />
        {/* The desk: top, then the front panel with the name plate and the advisor's average score. */}
        <rect x={18} y={90} width={144} height={16} rx={5} fill="#d9b48f" stroke="#a47c52" strokeWidth={2} />
        <rect x={24} y={104} width={132} height={58} rx={6} fill="#c49a6c" stroke="#a47c52" strokeWidth={2} />
        <rect x={42} y={110} width={96} height={19} rx={4} fill="#fff7ed" />
        <text x={90} y={124} textAnchor="middle" fontSize={12} fontWeight={700} fill="#3f2d1c">
          Desk {slot + 1} · {name}
        </text>
        <text x={90} y={149} textAnchor="middle" fontSize={12} fontWeight={600} fill="#3f2d1c">
          {score}
        </text>
      </svg>
      {thinking && <Dots style={{ left: 90, top: -12 }} />}
      <ToolStack pops={tools} style={{ left: 118, bottom: 122 }} />
    </button>
  );
}

/** The manager, next to the KPI wall. */
export function Manager() {
  return (
    <div className="absolute" style={{ left: MANAGER_SPOT.x - PERSON_H / 4, top: MANAGER_SPOT.y - PERSON_H, zIndex: MANAGER_SPOT.y }}>
      <Person role="manager" look={STAFF_LOOK.manager} height={PERSON_H} title="Manager: watches the KPI wall" />
    </div>
  );
}

// ------------------------------------------------------------------------ walkers
export interface Walker {
  id: string; // the chat id for a customer; "supervisor" or "quality" for the staff who walk
  role: Role;
  name: string;
  look: Look;
  x: number; // where the feet are (the walk is animated towards this point)
  y: number;
  ms: number; // how long the current walk lasts
  walking: boolean;
  visible: boolean;
  pose: Pose;
}

/** A person who walks on the floor (customer, supervisor, quality lead), with the tools and "..." above. */
export function WalkerView({ walker, tools, thinking }: { walker: Walker; tools: ToolPop[]; thinking: boolean }) {
  const move = { duration: walker.ms / 1000, ease: "linear" } as const;
  const who = walker.role === "customer" ? `${walker.name}: customer` : `${ROLE[walker.role].title}: ${ROLE[walker.role].agent}`;
  return (
    <motion.div
      className="pointer-events-none absolute left-0 top-0"
      initial={false}
      animate={{ x: walker.x - PERSON_H / 4, y: walker.y - PERSON_H, opacity: walker.visible ? 1 : 0 }}
      transition={{ x: move, y: move, opacity: { duration: 0.35 } }}
      style={{ zIndex: Math.round(walker.y) }}
    >
      <Person role={walker.role} look={walker.look} height={PERSON_H} walking={walker.walking} pose={walker.pose} title={who} />
      {thinking && <Dots style={{ left: PERSON_H / 4, top: -18 }} />}
      <ToolStack pops={tools} style={{ left: PERSON_H / 2 - 4, bottom: PERSON_H - 34 }} />
    </motion.div>
  );
}

// ------------------------------------------------------------------------- bubbles
export interface Bubble {
  key: string; // a new key = a new bubble (animated in)
  z: number; // creation order: the newest bubble is drawn on top of the others
  owner: string; // who it belongs to: a walker id, "reception" or "desk-3"
  chat?: string;
  role: Role;
  look: Look;
  placement: "above" | "left" | "right";
  x: number; // the top of the speaker's head
  y: number;
  kind: "say" | "card" | "score";
  title: string;
  text?: string;
  lines?: string[];
  tone?: "info" | "good" | "bad";
  score?: { overall: number; scores: Record<string, number>; resolved?: boolean | null; correct?: boolean | null };
  dim?: boolean; // an older message of the same chat
  speaking?: boolean; // its person is saying it now (voices on)
  tools?: { name: string; ok: boolean }[]; // the tools used for this message (shown inside the bubble)
}

const BUBBLE_W = 310;
const TONE: Record<string, string> = { info: "", good: "var(--good)", bad: "var(--critical)" };
const CRITERIA = ["compliance", "relevance", "satisfaction", "sentiment", "resolution"];
const clamp = (v: number, low: number, high: number) => Math.min(high, Math.max(low, v));

/** A speech bubble (the real words), an information card (routing, escalation) or the Quality score card. */
export function BubbleView({ bubble }: { bubble: Bubble }) {
  const role = ROLE[bubble.role];
  const border = (bubble.tone && TONE[bubble.tone]) || role.color;
  // A bubble above a head on the first row can be taller than the room above it (a long answer with its tool
  // chips): it is then pushed down just enough to stay inside the stage (offsetHeight ignores the stage's
  // scale, so it is in stage pixels).
  const box = useRef<HTMLDivElement>(null);
  const [push, setPush] = useState(0);
  useLayoutEffect(() => {
    if (bubble.placement !== "above" || !box.current) return;
    const top = bubble.y - 12 - box.current.offsetHeight;
    setPush(top < 8 ? 8 - top : 0);
  }, [bubble.key, bubble.placement, bubble.y, bubble.text, bubble.tools?.length]);
  // Placement: centred above the head, or beside it; always kept inside the stage.
  const position: CSSProperties =
    bubble.placement === "above"
      ? { left: clamp(bubble.x - BUBBLE_W / 2, 8, STAGE_W - BUBBLE_W - 8), top: bubble.y - 12 + push, transform: "translateY(-100%)" }
      : {
          left: clamp(bubble.placement === "left" ? bubble.x - 42 - BUBBLE_W : bubble.x + 42, 8, STAGE_W - BUBBLE_W - 8),
          top: clamp(bubble.y + 34, 130, STAGE_H - 90),
          transform: "translateY(-50%)",
        };
  return (
    <div ref={box} className="pointer-events-none absolute" style={{ ...position, width: BUBBLE_W, zIndex: 2000 + bubble.z }}>
      {/* An older message stays solid (nothing shows through it) but greyed: the newest one is the one to read. */}
      <motion.div
        initial={{ opacity: 0, scale: 0.92, y: 6 }}
        animate={{ opacity: 1, scale: bubble.dim ? 0.96 : 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96 }}
        transition={{ type: "spring", stiffness: 380, damping: 30 }}
        className={clsx("rounded-2xl border-2 bg-surface p-3 shadow-lift", bubble.dim ? "text-muted" : "text-ink")}
        style={{ borderColor: bubble.dim ? "var(--hairline)" : border }}
      >
        <div className="flex items-center gap-2">
          <Portrait role={bubble.role} look={bubble.look} size={36} />
          <div className="min-w-0 flex-1 text-[12.5px] font-semibold leading-tight text-ink2">{bubble.title}</div>
          {bubble.speaking && (
            <motion.span animate={{ scale: [1, 1.2, 1] }} transition={{ duration: 0.9, repeat: Infinity }} title="Speaking" aria-label="Speaking">
              <Volume2 size={18} color={border} aria-hidden />
            </motion.span>
          )}
        </div>
        {bubble.kind === "say" && <p className="cv-clamp mt-2 text-[15px] leading-snug">{bubble.text}</p>}
        {bubble.kind === "say" && !!bubble.tools?.length && <ToolChips tools={bubble.tools} />}
        {bubble.kind === "card" && (
          <ul className="mt-2 space-y-1 text-[14px] leading-snug">
            {bubble.lines?.map((line, i) => (
              <li key={i} className={i === 0 ? "font-semibold" : "text-ink2"}>
                {line}
              </li>
            ))}
          </ul>
        )}
        {bubble.kind === "score" && bubble.score && <ScoreCard score={bubble.score} note={bubble.text} />}
      </motion.div>
    </div>
  );
}

/** The tools used for a message, inside its bubble: the badges that popped up while the person worked move
 * here when the message arrives, so they never sit under the bubble. */
function ToolChips({ tools }: { tools: { name: string; ok: boolean }[] }) {
  return (
    <div className="mt-2 flex flex-wrap gap-1 border-t border-line pt-2">
      {tools.map((tool, i) => {
        const Icon = TOOL_ICON[tool.name] ?? Wrench;
        return (
          <span key={i} className="inline-flex items-center gap-1 rounded-full border bg-raised px-1.5 py-0.5 text-[11px] font-medium text-ink2" style={{ borderColor: tool.ok ? "var(--good)" : "var(--critical)" }}>
            <Icon size={11} aria-hidden /> {TOOL_LABEL[tool.name] ?? tool.name}
            {tool.ok ? <CheckCircle2 size={10} color="var(--good)" aria-hidden /> : <XCircle size={10} color="var(--critical)" aria-hidden />}
          </span>
        );
      })}
    </div>
  );
}

/** The Quality agent's verdict: overall score, the five criteria, and its reason in one or two lines. */
function ScoreCard({ score, note }: { score: NonNullable<Bubble["score"]>; note?: string }) {
  const color = score.overall >= 4 ? "var(--good)" : score.overall >= 3 ? "var(--warning)" : "var(--critical)";
  return (
    <div className="mt-2">
      <div className="flex items-end gap-2">
        <span className="font-display text-[34px] font-bold leading-none" style={{ color }}>
          {num(score.overall, 1)}
        </span>
        <span className="pb-1 text-sm text-muted">/ 5</span>
        <span className="ml-auto pb-1 text-[12px] font-semibold" style={{ color: score.resolved ? "var(--good-text)" : "var(--critical)" }}>
          {score.resolved ? "Resolved" : "Not resolved"}
          {score.correct === true ? " · policy-correct" : score.correct === false ? " · differs from policy" : ""}
        </span>
      </div>
      <div className="mt-2 space-y-1">
        {CRITERIA.map((c) => (
          <div key={c} className="grid grid-cols-[86px_1fr_14px] items-center gap-2 text-[11.5px] text-ink2">
            <span>{c}</span>
            <span className="h-1.5 overflow-hidden rounded-full bg-sunken">
              <span className="block h-full rounded-full" style={{ width: `${((score.scores[c] ?? 0) / 5) * 100}%`, background: color }} />
            </span>
            <span className="text-right tabular">{score.scores[c] ?? "–"}</span>
          </div>
        ))}
      </div>
      {note && <p className="cv-clamp-2 mt-2 text-[12px] leading-snug text-ink2">“{note}”</p>}
    </div>
  );
}

// ------------------------------------------------------------------------ KPI wall
/** The KPI wall: the numbers of every finished live chat, updated after each Quality review. */
export function KpiWall({ totals }: { totals: any | null }) {
  const tiles = [
    { label: "Customers served", value: totals?.chats, format: (v: number) => num(Math.round(v), 0) },
    { label: "Expected wait", value: totals?.wait_seconds, format: (v: number) => `${Math.round(v)} s` },
    { label: "Solved first time", value: totals?.fcr == null ? null : totals.fcr * 100, format: (v: number) => `${Math.round(v)}%` },
    { label: "Quality score", value: totals?.quality, format: (v: number) => `${v.toFixed(1)}/5` },
    { label: "Customer rating", value: totals?.csat, format: (v: number) => `${v.toFixed(1)}/5` },
  ];
  const tokens = totals?.tokens ?? 0;
  return (
    <div className="absolute flex flex-col" style={{ left: 536, top: 30, width: 648, height: 166, zIndex: 5 }} role="region" aria-label="KPI wall">
      <div className="flex items-center justify-between px-1 text-[12px] font-semibold uppercase tracking-[0.14em]" style={{ color: "#93c5fd" }}>
        <span>KPI wall · every live chat so far</span>
        <span className="flex items-center gap-1.5">
          <span className="live-dot" /> live
        </span>
      </div>
      <div className="mt-2 grid flex-1 grid-cols-5 gap-2">
        {tiles.map((tile) => (
          <div key={tile.label} className="flex flex-col justify-center rounded-xl px-3" style={{ background: "rgba(148,163,184,0.13)" }}>
            <div className="font-display text-[27px] font-semibold leading-none text-white">
              <AnimatedNumber value={tile.value} format={tile.format} />
            </div>
            <div className="mt-1.5 text-[12px] leading-tight" style={{ color: "#cbd5e1" }}>
              {tile.label}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-2 truncate px-1 text-[12px]" style={{ color: "#94a3b8" }}>
        AI text used: {tokens >= 1000 ? `${num(tokens / 1000, 1)}k` : tokens} tokens · answered by the AI: {totals?.by_ai ?? 0} · by a person: {totals?.by_human ?? 0}
      </div>
    </div>
  );
}
