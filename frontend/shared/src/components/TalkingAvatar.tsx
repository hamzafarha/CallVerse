import { motion, useReducedMotion } from "framer-motion";
import { useId } from "react";

/** What a call participant is doing; it drives the face. */
export type AvatarState = "speaking" | "thinking" | "typing" | "listening" | "idle";

/** A persona's face: colour, brows and resting mouth. No face is ever chosen from a name. */
const PERSONA_FACE: Record<string, { color: string; brows: [string, string]; mouth: string }> = {
  impatient: { color: "var(--critical)", brows: ["M 32 40 L 44 44", "M 56 44 L 68 40"], mouth: "M 41 72 Q 50 66 59 72" },
  normal: { color: "var(--series-1)", brows: ["M 32 42 L 44 42", "M 56 42 L 68 42"], mouth: "M 42 70 L 58 70" },
  patient: { color: "var(--good)", brows: ["M 32 42 Q 38 38 44 41", "M 56 41 Q 62 38 68 42"], mouth: "M 41 68 Q 50 75 59 68" },
};

const INK = "var(--text-primary)";

/** Animated face of a call participant (SVG). `agent`: the AI advisor, in the brand
 * colours with a headset; `person`: a simple face whose colour and mood follow the
 * persona. The mouth opens on every spoken word (`word` counter), or moves steadily
 * when the voice reports no words; the eyes blink, look at the other participant, and
 * look up with "···" while thinking or typing. */
export function TalkingAvatar({
  kind,
  persona = "normal",
  headset = false,
  state,
  word = 0,
  lipSync = "loop",
  lookAt = "right",
  size = 72,
  label,
}: {
  kind: "agent" | "person";
  persona?: string;
  headset?: boolean;
  state: AvatarState;
  word?: number;
  lipSync?: "words" | "loop";
  lookAt?: "left" | "right";
  size?: number;
  label?: string;
}) {
  const id = useId().replace(/:/g, "");
  const reduced = !!useReducedMotion();
  const agent = kind === "agent";
  const face = PERSONA_FACE[persona] ?? PERSONA_FACE.normal;
  const busy = state === "thinking" || state === "typing";
  const look = busy ? { x: 0, y: -2.2 } : { x: lookAt === "left" ? -2.2 : 2.2, y: 0 };
  const eyeY = agent ? 50.5 : 52;
  const breathing = !reduced && state === "listening";

  return (
    <motion.svg
      viewBox="0 -14 100 114"
      width={size}
      height={size * 1.14}
      role="img"
      aria-label={label}
      animate={{ scale: breathing ? [1, 1.02, 1] : 1 }}
      transition={breathing ? { repeat: Infinity, duration: 3.2, ease: "easeInOut" } : { duration: 0.2 }}
    >
      <defs>
        <linearGradient id={`${id}-agent`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" style={{ stopColor: "var(--brand)" }} />
          <stop offset="100%" style={{ stopColor: "var(--brand-2)" }} />
        </linearGradient>
      </defs>

      {busy &&
        [0, 1, 2].map((i) => (
          <motion.circle
            key={i}
            cx={40 + i * 10}
            cy={-4}
            r={3.2}
            style={{ fill: "var(--text-muted)" }}
            animate={reduced ? undefined : { y: [0, -5, 0], opacity: [0.35, 1, 0.35] }} // transform, not the cy attribute (no "cy undefined" on exit)
            transition={{ repeat: Infinity, duration: 0.9, delay: i * 0.15 }}
          />
        ))}

      {/* head */}
      {agent ? (
        <rect x={20} y={24} width={60} height={60} rx={22} fill={`url(#${id}-agent)`} />
      ) : (
        <>
          <circle cx={50} cy={54} r={32} style={{ fill: `color-mix(in srgb, ${face.color} 22%, white)` }} />
          <path
            d="M 19 50 Q 18 18 50 18 Q 82 18 81 50 Q 70 36 50 36 Q 30 36 19 50 Z"
            style={{ fill: `color-mix(in srgb, ${face.color} 78%, black)` }}
          />
        </>
      )}

      {/* cheeks */}
      <circle cx={agent ? 33 : 35} cy={64} r={4} style={{ fill: agent ? "white" : face.color, opacity: agent ? 0.18 : 0.28 }} />
      <circle cx={agent ? 67 : 65} cy={64} r={4} style={{ fill: agent ? "white" : face.color, opacity: agent ? 0.18 : 0.28 }} />

      {/* eyes: blink every few seconds (agents and people at a different pace) */}
      <motion.g
        style={{ transformBox: "fill-box", transformOrigin: "center" }}
        animate={reduced ? undefined : { scaleY: [1, 1, 0.08, 1] }}
        transition={{ repeat: Infinity, duration: agent ? 4.3 : 5.1, times: [0, 0.93, 0.965, 1] }}
      >
        {agent ? (
          <>
            <rect x={32} y={43} width={13} height={15} rx={6.5} fill="white" />
            <rect x={55} y={43} width={13} height={15} rx={6.5} fill="white" />
          </>
        ) : (
          <>
            <ellipse cx={39} cy={eyeY} rx={6} ry={6.5} fill="white" />
            <ellipse cx={61} cy={eyeY} rx={6} ry={6.5} fill="white" />
          </>
        )}
        <motion.g animate={look} transition={{ type: "spring", stiffness: 120, damping: 14 }}>
          <circle cx={agent ? 38.5 : 39} cy={eyeY} r={3} style={{ fill: agent ? "#1e1b4b" : INK }} />
          <circle cx={agent ? 61.5 : 61} cy={eyeY} r={3} style={{ fill: agent ? "#1e1b4b" : INK }} />
        </motion.g>
      </motion.g>

      {!agent &&
        face.brows.map((d) => <path key={d} d={d} strokeWidth={2.6} strokeLinecap="round" fill="none" style={{ stroke: INK }} />)}

      <Mouth
        speaking={state === "speaking"}
        word={word}
        lipSync={lipSync}
        idle={agent ? "M 42 67 Q 50 74 58 67" : face.mouth}
        y={agent ? 69 : 70}
        color={agent ? "white" : INK}
        reduced={reduced}
      />

      {(agent || headset) && (
        <g strokeLinecap="round" opacity={0.85} style={{ stroke: INK, fill: "none" }}>
          <path d="M 15 56 Q 15 12 50 12 Q 85 12 85 56" strokeWidth={3.6} />
          <path d="M 16 64 Q 18 82 37 81" strokeWidth={2.6} />
          <rect x={10} y={47} width={9} height={17} rx={4} style={{ fill: INK, stroke: "none" }} />
          <rect x={81} y={47} width={9} height={17} rx={4} style={{ fill: INK, stroke: "none" }} />
          <circle cx={38.5} cy={81} r={3} style={{ fill: INK, stroke: "none" }} />
        </g>
      )}
    </motion.svg>
  );
}

function Mouth({
  speaking,
  word,
  lipSync,
  idle,
  y,
  color,
  reduced,
}: {
  speaking: boolean;
  word: number;
  lipSync: "words" | "loop";
  idle: string;
  y: number;
  color: string;
  reduced: boolean;
}) {
  if (!speaking) return <path d={idle} strokeWidth={2.8} strokeLinecap="round" fill="none" style={{ stroke: color }} />;
  const shape = { cx: 50, cy: y, rx: 6.5, style: { fill: color } };
  if (reduced) return <ellipse {...shape} ry={3.5} />;
  if (lipSync === "words") {
    // a new key on every word replays the open-and-close movement
    return (
      <motion.ellipse key={word} {...shape} initial={{ ry: 1.6 }} animate={{ ry: [1.6, 6.5, 2.4] }} transition={{ duration: 0.26, ease: "easeOut" }} />
    );
  }
  return (
    <motion.ellipse
      {...shape}
      initial={{ ry: 1.6 }}
      animate={{ ry: [1.6, 6, 2.2, 5, 1.6] }}
      transition={{ repeat: Infinity, duration: 0.85, ease: "easeInOut" }}
    />
  );
}
