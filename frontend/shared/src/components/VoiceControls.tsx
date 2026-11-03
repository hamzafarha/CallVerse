/**
 * Voice mode controls (Live chat and Advisor desk): an on/off switch, a Stop button while an agent speaks,
 * and a small menu to choose the voices and the speed. The speaking itself happens in lib/voice.ts, with the
 * browser's built-in speech synthesis (no server, no cost).
 */
import { AnimatePresence, motion } from "framer-motion";
import { AudioLines, ChevronDown, Square, Volume2, VolumeX } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Voice, VoiceRole } from "../lib/voice";
import { clsx } from "./ui";

// Labels of the two voices in the menu.
const ROLE_LABEL: Record<VoiceRole, string> = { advisor: "Advisor agent voice", customer: "Customer voice" };

/** Voice mode switch, a Stop button while an agent speaks, and a menu to pick the voices. */
export function VoiceControls({ voice, roles = ["advisor", "customer"] }: { voice: Voice; roles?: VoiceRole[] }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  // While the menu is open, a click outside it or the Escape key closes it.
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !box.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  // Some browsers have no speech synthesis: show a disabled button.
  if (!voice.supported) {
    return (
      <button className="btn btn-ghost py-1.5 text-xs" disabled title="This browser has no speech synthesis">
        <VolumeX size={14} /> Voice
      </button>
    );
  }
  // The voice currently used for each role.
  const current: Record<VoiceRole, SpeechSynthesisVoice | undefined> = { advisor: voice.advisorVoice, customer: voice.customerVoice };
  return (
    <div ref={box} className="relative flex items-center gap-1">
      <button
        className={clsx("btn py-1.5 text-xs", voice.enabled ? "btn-primary" : "btn-ghost")}
        aria-pressed={voice.enabled}
        title={
          voice.voices.length > 0 && !voice.hasEnglish
            ? "No English voice in this browser: see the voice settings"
            : voice.enabled
              ? "Voice mode on: the agents' messages are read aloud"
              : "Voice mode off"
        }
        onClick={() => voice.setEnabled(!voice.enabled)}
      >
        {voice.enabled ? <Volume2 size={14} /> : <VolumeX size={14} />} Voice
      </button>
      {/* Stop button, only while an agent is speaking. */}
      <AnimatePresence>
        {voice.speaking !== null && (
          <motion.button
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="btn btn-ghost py-1.5 text-xs text-brand"
            title="Stop speaking"
            onClick={voice.stop}
          >
            <AudioLines size={14} className="animate-pulse" /> <Square size={10} /> Stop
          </motion.button>
        )}
      </AnimatePresence>
      {/* Opens the voice settings menu. */}
      <button className="btn btn-ghost btn-icon h-8 w-8" title="Voice settings" aria-expanded={open} onClick={() => setOpen(!open)}>
        <ChevronDown size={14} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            className="card absolute right-0 top-full z-50 mt-2 w-72 space-y-3 p-4 text-xs"
          >
            <div className="font-semibold text-ink">Voice settings</div>
            <p className="text-muted">Only the agents speak; what you type is never read back. Voices come from this browser.</p>
            {voice.voices.length > 0 && !voice.hasEnglish && (
              <p className="rounded-lg p-2 text-ink" style={{ background: "color-mix(in srgb, var(--warning) 14%, transparent)" }}>
                No English voice in this browser, so the agents will have an accent. Add one in Windows Settings → Time &
                language → Speech, or use Chrome or Edge (they offer online English voices).
              </p>
            )}
            {/* One voice picker per role. */}
            {roles.map((role) => (
              <label key={role} className="block">
                <span className="label">{ROLE_LABEL[role]}</span>
                <select
                  className="field mt-1 py-1.5 text-xs"
                  value={current[role]?.voiceURI ?? ""}
                  onChange={(e) => voice.setVoice(role, e.target.value)}
                >
                  {voice.voices.map((v) => (
                    <option key={v.voiceURI} value={v.voiceURI}>
                      {v.name} ({v.lang})
                    </option>
                  ))}
                </select>
              </label>
            ))}
            {/* Speaking speed, from 0.7x to 1.5x. */}
            <label className="block">
              <span className="label">Speed ×{voice.rate.toFixed(1)}</span>
              <input
                type="range"
                min={0.7}
                max={1.5}
                step={0.1}
                value={voice.rate}
                onChange={(e) => voice.setRate(Number(e.target.value))}
                className="mt-1 w-full accent-[var(--brand)]"
              />
            </label>
            <button
              className="btn btn-ghost w-full py-1.5 text-xs"
              onClick={() => voice.replay("test", "Hello, this is how I sound in voice mode.", roles[0])}
            >
              <Volume2 size={13} /> Test the {roles[0] === "advisor" ? "advisor" : "customer"} voice
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
