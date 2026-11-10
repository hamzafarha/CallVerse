/**
 * The people of the contact centre page, drawn in SVG (no images), following the agreed style sheet:
 *
 * - A, full-body figures: they stand, sit at a desk or walk on the floor (legs and arms swing);
 * - B, portrait badges: head and shoulders in a round badge, shown inside the speech bubbles.
 *
 * One colour and one accessory per role, the same everywhere: customer blue + phone, receptionist teal +
 * headset and tablet, advisor purple + headset with a microphone, supervisor navy + red tie and badge,
 * quality lead amber + clipboard, manager grey + glasses. Skin and hair change from person to person: they are
 * picked from the person's id (never from a name), so the same advisor always looks the same.
 */
import type { CSSProperties, ReactNode } from "react";

export type Role = "customer" | "reception" | "advisor" | "supervisor" | "quality" | "manager";
export type Pose = "stand" | "point" | "raise";
export type HairStyle = "short" | "long" | "bun" | "curly";

/** What each role stands for in CallVerse (the real agent behind the figure). */
export const ROLE: Record<Role, { color: string; tint: string; legs: string; title: string; agent: string }> = {
  customer: { color: "#3b82f6", tint: "#dbeafe", legs: "#334155", title: "Customer", agent: "sends the request" },
  reception: { color: "#14b8a6", tint: "#ccfbf1", legs: "#334155", title: "Receptionist", agent: "Workforce agent" },
  advisor: { color: "#7c3aed", tint: "#ede9fe", legs: "#334155", title: "Advisor", agent: "Advisor agent" },
  supervisor: { color: "#1e3a5f", tint: "#e0e7ff", legs: "#1e293b", title: "Supervisor", agent: "escalations" },
  quality: { color: "#f59e0b", tint: "#fef3c7", legs: "#334155", title: "Quality lead", agent: "Quality agent" },
  manager: { color: "#475569", tint: "#e2e8f0", legs: "#1e293b", title: "Manager", agent: "watches the KPIs" },
};

export interface Look {
  skin: string;
  hair: string;
  style: HairStyle;
}

const SKINS = ["#f3cfb3", "#e8b08a", "#d9a077", "#c68863", "#a86b4c", "#7a4a2e", "#5c3a24"];
const HAIRS = ["#1f1a17", "#3b2a20", "#5a3825", "#8a5a2b", "#c08a4a", "#2b2d42"];
const STYLES: HairStyle[] = ["short", "long", "bun", "curly"];
const INK = "#1f2937"; // headset, glasses and phone

/** The staff who are always the same person: their look is the one of the style sheet. */
export const STAFF_LOOK: Record<"reception" | "supervisor" | "quality" | "manager", Look> = {
  reception: { skin: "#a86b4c", hair: "#2b2d42", style: "short" },
  supervisor: { skin: "#d9a077", hair: "#8a5a2b", style: "short" },
  quality: { skin: "#7a4a2e", hair: "#3b2a20", style: "short" },
  manager: { skin: "#e0b090", hair: "#9ca3af", style: "short" },
};

/** A small stable number made from a text (the same text always gives the same number). */
export function hashOf(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return h >>> 0;
}

/** A look picked from an id (customer id, "advisor-03"...): skin, hair colour and hair style. */
export function lookFor(id: string): Look {
  const h = hashOf(id);
  return { skin: SKINS[h % SKINS.length], hair: HAIRS[(h >>> 4) % HAIRS.length], style: STYLES[(h >>> 9) % STYLES.length] };
}

// Advisors are simulated agents with an id ("advisor-03"): the centre gives each one a friendly first name.
const ADVISOR_NAMES = [
  "Beatriz", "Carlos", "Daniela", "Eduardo", "Fernanda", "Gustavo", "Helena", "Igor",
  "Juliana", "Lucas", "Mariana", "Nicolas", "Olivia", "Pedro", "Renata", "Samuel",
];

/** "advisor-03" -> 3. */
export const advisorNumber = (id: string) => Number(String(id).replace(/\D/g, "")) || 0;
/** "advisor-03" -> "Eduardo" (always the same name for the same id). */
export const advisorName = (id: string) => ADVISOR_NAMES[advisorNumber(id) % ADVISOR_NAMES.length];

// ------------------------------------------------------------------------- shared head
/**
 * The head, in any size: (cx, cy) its centre and r its radius. Hair (with its style), then the role's
 * accessories that sit on the head: the headset (receptionist, advisor), the microphone (advisor) and the
 * glasses (manager).
 */
function Head({ cx, cy, r, look, role }: { cx: number; cy: number; r: number; look: Look; role: Role }) {
  const headset = role === "reception" || role === "advisor";
  const cap = `M ${cx - 1.02 * r} ${cy - 0.1 * r} A ${1.02 * r} ${1.02 * r} 0 0 1 ${cx + 1.02 * r} ${cy - 0.1 * r} Q ${cx} ${cy - 0.6 * r} ${cx - 1.02 * r} ${cy - 0.1 * r} Z`;
  const curls = [200, 235, 270, 305, 340].map((deg) => {
    const a = (deg * Math.PI) / 180;
    return { x: cx + 0.96 * r * Math.cos(a), y: cy + 0.96 * r * Math.sin(a) };
  });
  return (
    <g>
      {/* Hair behind the head: long hair falls to the shoulders, a bun sits on top. */}
      {look.style === "long" && (
        <path
          d={`M ${cx - 1.08 * r} ${cy - 0.05 * r} Q ${cx - 1.15 * r} ${cy + 1.2 * r} ${cx - 0.75 * r} ${cy + 1.35 * r} L ${cx + 0.75 * r} ${cy + 1.35 * r} Q ${cx + 1.15 * r} ${cy + 1.2 * r} ${cx + 1.08 * r} ${cy - 0.05 * r} Z`}
          fill={look.hair}
        />
      )}
      {look.style === "bun" && <circle cx={cx} cy={cy - r} r={0.36 * r} fill={look.hair} />}
      <circle cx={cx} cy={cy} r={r} fill={look.skin} />
      <path d={cap} fill={look.hair} />
      {look.style === "curly" && curls.map((c, i) => <circle key={i} cx={c.x} cy={c.y} r={0.28 * r} fill={look.hair} />)}
      {headset && (
        <>
          <path d={`M ${cx - 1.04 * r} ${cy} A ${1.04 * r} ${1.04 * r} 0 0 1 ${cx + 1.04 * r} ${cy}`} stroke={INK} strokeWidth={0.19 * r} fill="none" />
          <rect x={cx - 1.2 * r} y={cy - 0.28 * r} width={0.36 * r} height={0.62 * r} rx={0.15 * r} fill={INK} />
          <rect x={cx + 0.84 * r} y={cy - 0.28 * r} width={0.36 * r} height={0.62 * r} rx={0.15 * r} fill={INK} />
        </>
      )}
      {role === "advisor" && (
        <>
          <path
            d={`M ${cx - 1.06 * r} ${cy + 0.32 * r} Q ${cx - 0.98 * r} ${cy + 0.88 * r} ${cx - 0.42 * r} ${cy + 0.86 * r}`}
            stroke={INK}
            strokeWidth={0.12 * r}
            fill="none"
            strokeLinecap="round"
          />
          <circle cx={cx - 0.38 * r} cy={cy + 0.86 * r} r={0.11 * r} fill={INK} />
        </>
      )}
      {role === "manager" && (
        <g stroke={INK} strokeWidth={0.11 * r} fill="none">
          <circle cx={cx - 0.4 * r} cy={cy + 0.12 * r} r={0.32 * r} />
          <circle cx={cx + 0.4 * r} cy={cy + 0.12 * r} r={0.32 * r} />
          <path d={`M ${cx - 0.08 * r} ${cy + 0.1 * r} L ${cx + 0.08 * r} ${cy + 0.1 * r}`} />
        </g>
      )}
    </g>
  );
}

/** The tie of the supervisor (red) and the manager (navy), from the collar down. */
function Tie({ x, top, length, width, color }: { x: number; top: number; length: number; width: number; color: string }) {
  return <path d={`M ${x} ${top} L ${x - width / 2} ${top + length * 0.2} L ${x} ${top + length} L ${x + width / 2} ${top + length * 0.2} Z`} fill={color} />;
}

// ---------------------------------------------------------------------- A: full body
/**
 * A full-body figure (style A), drawn in a 100 x 200 box, `height` pixels tall. `walking` swings the legs and
 * the arms; `pose` raises the right arm (the receptionist points to a desk, the quality lead shows a score).
 * `color` replaces the role's colour (the twin crowd wears the colour of its problem).
 */
export function Person({
  role,
  look,
  height = 150,
  walking = false,
  pose = "stand",
  color,
  style,
  title,
}: {
  role: Role;
  look: Look;
  height?: number;
  walking?: boolean;
  pose?: Pose;
  color?: string;
  style?: CSSProperties;
  title?: string;
}) {
  const r = { ...ROLE[role], ...(color ? { color } : {}) };
  const armTurn = pose === "point" ? -120 : pose === "raise" ? -165 : 0;
  return (
    <svg viewBox="0 0 100 200" width={height / 2} height={height} className={walking ? "cv-person cv-walking" : "cv-person"} style={style} role="img" aria-label={title ?? r.title}>
      {title && <title>{title}</title>}
      <g className="cv-body">
        {/* Legs, then arms, then the body on top (as in the style sheet). */}
        <rect className="cv-leg-l" x={28} y={136} width={18} height={62} rx={9} fill={r.legs} />
        <rect className="cv-leg-r" x={54} y={136} width={18} height={62} rx={9} fill={r.legs} />
        <rect className="cv-arm-l" x={8} y={66} width={17} height={64} rx={8.5} fill={r.color} />
        <rect
          className="cv-arm-r"
          x={75}
          y={66}
          width={17}
          height={64}
          rx={8.5}
          fill={r.color}
          style={armTurn ? { transform: `rotate(${armTurn}deg)` } : undefined}
        />
        <rect x={19} y={60} width={62} height={84} rx={18} fill={r.color} />
        {role === "customer" && <rect x={80} y={108} width={15} height={27} rx={3.5} fill="#111827" />}
        {role === "reception" && <rect x={32} y={84} width={36} height={25} rx={4} fill="#e5e7eb" />}
        {role === "supervisor" && (
          <>
            <Tie x={50} top={61} length={42} width={14} color="#dc2626" />
            <rect x={62} y={73} width={12} height={8} rx={2} fill="#facc15" />
          </>
        )}
        {role === "manager" && <Tie x={50} top={61} length={42} width={14} color="#1e293b" />}
        {role === "quality" && (
          <>
            <rect x={30} y={80} width={40} height={46} rx={5} fill="#fef9c3" stroke="#a16207" strokeWidth={2.5} />
            <path d="M 38 103 L 47 112 L 62 93" stroke="#16a34a" strokeWidth={5} fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </>
        )}
        <Head cx={50} cy={29.5} r={26} look={look} role={role} />
      </g>
    </svg>
  );
}

// -------------------------------------------------------------------- B: portrait badge
/** A round portrait badge (style B): the head and the shoulders, on the role's light colour. */
export function Portrait({ role, look, size = 40, title }: { role: Role; look: Look; size?: number; title?: string }) {
  const r = ROLE[role];
  const clip = `cv-clip-${role}-${hashOf(look.skin + look.hair + look.style)}`;
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} role="img" aria-label={title ?? r.title} className="shrink-0">
      <defs>
        <clipPath id={clip}>
          <circle cx={50} cy={50} r={47} />
        </clipPath>
      </defs>
      <circle cx={50} cy={50} r={47} fill={r.tint} />
      <g clipPath={`url(#${clip})`}>
        <path d="M 12 104 Q 14 64 50 62 Q 86 64 88 104 Z" fill={r.color} />
        {role === "supervisor" && <Tie x={50} top={63} length={32} width={10} color="#dc2626" />}
        {role === "manager" && <Tie x={50} top={63} length={32} width={10} color="#1e293b" />}
        {role === "quality" && (
          <>
            <rect x={62} y={76} width={18} height={21} rx={3} fill="#fef9c3" stroke="#a16207" strokeWidth={2} />
            <path d="M 66 86 L 70 90 L 77 81" stroke="#16a34a" strokeWidth={3} fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </>
        )}
        <Head cx={50} cy={43} r={20} look={look} role={role} />
      </g>
      <circle cx={50} cy={50} r={47} fill="none" stroke={r.color} strokeWidth={4} />
    </svg>
  );
}

/**
 * The centre's CSS: the walking and pointing movements (CSS, so many people can move at once without slowing
 * the page), and the line limits of the speech bubbles.
 */
export function CentreStyles(): ReactNode {
  return (
    <style>{`
      .cv-clamp { display: -webkit-box; -webkit-line-clamp: 6; -webkit-box-orient: vertical; overflow: hidden; }
      .cv-clamp-2 { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
      .cv-person { overflow: visible; }
      .cv-person .cv-leg-l { transform-origin: 37px 140px; }
      .cv-person .cv-leg-r { transform-origin: 63px 140px; }
      .cv-person .cv-arm-l { transform-origin: 16px 72px; }
      .cv-person .cv-arm-r { transform-origin: 84px 72px; transition: transform .35s ease; }
      .cv-walking .cv-leg-l, .cv-walking .cv-arm-r { animation: cv-step .42s ease-in-out infinite alternate; }
      .cv-walking .cv-leg-r, .cv-walking .cv-arm-l { animation: cv-step .42s ease-in-out infinite alternate-reverse; }
      .cv-walking .cv-body { animation: cv-bob .21s ease-in-out infinite alternate; }
      @keyframes cv-step { from { transform: rotate(16deg); } to { transform: rotate(-16deg); } }
      @keyframes cv-bob { from { transform: translateY(0); } to { transform: translateY(-3px); } }
      @media (prefers-reduced-motion: reduce) { .cv-walking * { animation: none !important; } }
    `}</style>
  );
}
