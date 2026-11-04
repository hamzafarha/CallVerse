/**
 * The microphone button next to "Send": click, talk, pause. While it listens it turns red and pulses; the
 * words heard so far appear in the text box (see lib/speech.ts).
 */
import { motion } from "framer-motion";
import { Mic, MicOff } from "lucide-react";
import type { SpeechInput } from "../lib/speech";
import { clsx } from "./ui";

export function MicButton({ speech, disabled = false, className = "h-[46px] w-[46px]" }: { speech: SpeechInput; disabled?: boolean; className?: string }) {
  const reason = speech.unavailable;
  const title = reason ?? (speech.listening ? "Listening… click to stop" : "Speak instead of typing");
  return (
    <motion.button
      type="button"
      whileTap={{ scale: 0.92 }}
      disabled={!!reason || (disabled && !speech.listening)}
      onClick={speech.toggle}
      title={title}
      aria-label={title}
      aria-pressed={speech.listening}
      className={clsx("btn shrink-0 px-0", speech.listening ? "animate-pulse-ring text-white" : "btn-ghost", className)}
      style={speech.listening ? { background: "var(--critical)", ["--ring-color" as any]: "var(--critical)" } : undefined}
    >
      {reason ? <MicOff size={18} /> : <Mic size={18} />}
    </motion.button>
  );
}

/** One line under the text box while the microphone is open. */
export function ListeningHint({ speech, language }: { speech: SpeechInput; language?: string }) {
  if (!speech.listening) return null;
  return (
    <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className="mt-2 flex items-center gap-2 text-xs text-muted">
      <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--critical)]" />
      Listening{language ? ` in ${language}` : ""}… {speech.autoSend ? "pause when you are done: it sends by itself." : "pause when you are done, then press Send."}
    </motion.div>
  );
}
