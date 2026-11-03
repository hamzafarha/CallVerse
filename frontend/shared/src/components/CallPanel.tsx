/**
 * The "On call" band shown in voice mode: the two participants face each other, with a call timer and a sound
 * wave in the middle. Their faces react live (speaking, thinking, typing, listening).
 */
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { clock } from "../lib/format";
import type { Voice } from "../lib/voice";
import { TalkingAvatar, type AvatarState } from "./TalkingAvatar";
import { clsx } from "./ui";

/**
 * One side of the call: an AI agent or a person, with a name, a subtitle and what they are doing.
 */
export interface CallParticipant {
  kind: "agent" | "person";
  name: string;
  subtitle: string;
  state: AvatarState;
  persona?: string;
  headset?: boolean;
  note?: string; // replaces the state label, e.g. "copilot drafting…"
}

// Text under the name for each state.
const STATE_LABEL: Record<AvatarState, string> = {
  speaking: "speaking…",
  thinking: "thinking…",
  typing: "typing…",
  listening: "listening",
  idle: "",
};

/** The "On call" band of voice mode: both participants face each other and react live. */
export function CallPanel({
  voice,
  left,
  right,
  startedAt,
  compact = false,
}: {
  voice: Voice;
  left: CallParticipant;
  right: CallParticipant;
  startedAt: number | null;
  compact?: boolean; // slim band (advisor desk), so the conversation keeps the room
}) {
  const [now, setNow] = useState(() => Date.now());
  // Re-render every second so the call timer moves.
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const seconds = startedAt ? Math.max(0, (now - startedAt) / 1000) : 0;
  // Who is speaking now (if anyone).
  const talker = left.state === "speaking" ? left : right.state === "speaking" ? right : null;
  return (
    <motion.div
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: "auto", opacity: 1 }}
      exit={{ height: 0, opacity: 0 }}
      className="overflow-hidden border-b border-line bg-raised/40"
    >
      <div className={clsx("flex items-center justify-between gap-3 px-4 sm:px-6", compact ? "py-1.5" : "py-3")}>
        {/* The left participant looks right and the right one looks left: they face each other. */}
        <Participant p={left} voice={voice} lookAt="right" compact={compact} />
        <div className={clsx("flex shrink-0 items-center text-[11px] text-muted", compact ? "gap-2" : "flex-col gap-1.5")}>
          <span className="inline-flex items-center gap-1.5 font-semibold text-ink">
            <span className="live-dot" /> On call · <span className="tabular">{clock(seconds)}</span>
          </span>
          {/* The bars move while someone speaks. */}
          <Wave active={!!talker} />
          {!compact && <span className="max-w-[150px] truncate">{talker ? `${talker.name} is speaking` : "voice mode"}</span>}
        </div>
        <Participant p={right} voice={voice} lookAt="left" compact={compact} />
      </div>
    </motion.div>
  );
}

/**
 * One participant: animated face (with a pulsing ring while speaking), name, subtitle and status.
 */
function Participant({ p, voice, lookAt, compact = false }: { p: CallParticipant; voice: Voice; lookAt: "left" | "right"; compact?: boolean }) {
  const speaking = p.state === "speaking";
  const status = p.note ?? STATE_LABEL[p.state];
  return (
    <div className={clsx("flex min-w-0 items-center gap-3", lookAt === "left" && "flex-row-reverse text-right")}>
      <div className="relative shrink-0">
        <AnimatePresence>
          {speaking && (
            <motion.span
              key="ring"
              className="absolute inset-0 rounded-full"
              style={{ border: "2px solid var(--brand)" }}
              initial={{ scale: 0.9, opacity: 0.7 }}
              animate={{ scale: 1.25, opacity: 0 }}
              exit={{ opacity: 0 }}
              transition={{ repeat: Infinity, duration: 1.2, ease: "easeOut" }}
            />
          )}
        </AnimatePresence>
        <TalkingAvatar
          kind={p.kind}
          persona={p.persona}
          headset={p.headset}
          state={p.state}
          word={voice.word}
          lipSync={voice.lipSync}
          lookAt={lookAt}
          size={compact ? 40 : 60}
          label={`${p.name}: ${status || "on the call"}`}
        />
      </div>
      <div className="min-w-0">
        <div className="truncate text-sm font-semibold text-ink">{p.name}</div>
        {!compact && <div className="truncate text-[11px] text-muted">{p.subtitle}</div>}
        <div className={clsx("h-4 truncate text-[11px] font-medium", speaking ? "text-brand" : "text-muted")} title={compact ? p.subtitle : undefined}>
          {compact ? status || p.subtitle : status}
        </div>
      </div>
    </div>
  );
}

/**
 * Five small bars that bounce like a sound wave while someone speaks.
 */
function Wave({ active }: { active: boolean }) {
  return (
    <div className="flex h-5 items-center gap-[3px]" aria-hidden>
      {[0.6, 1, 0.75, 1, 0.6].map((peak, i) => (
        <motion.span
          key={i}
          className="w-[3px] rounded-full"
          style={{ background: active ? "var(--brand)" : "var(--hairline)" }}
          animate={active ? { height: [4, 18 * peak, 6, 14 * peak, 4] } : { height: 4 }}
          transition={active ? { repeat: Infinity, duration: 0.9, delay: i * 0.08 } : { duration: 0.2 }}
        />
      ))}
    </div>
  );
}
