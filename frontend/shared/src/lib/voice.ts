import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage } from "./session";

/** Voice mode: the agents' messages are read aloud with the browser's speech engine
 * (Web Speech API, no download, no server). The Advisor agent and the customer each
 * get their own English voice; only finished messages are spoken, never a draft that
 * the fact check may still reject, and never what the human typed. */

export type VoiceRole = "advisor" | "customer";

export const VOICE_SUPPORTED =
  typeof window !== "undefined" && "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;

/** How a customer persona sounds: impatient customers speak faster, patient ones slower. */
const PERSONA_PROSODY: Record<string, { rate: number; pitch: number }> = {
  impatient: { rate: 1.15, pitch: 1.05 },
  normal: { rate: 1, pitch: 1 },
  patient: { rate: 0.92, pitch: 0.97 },
};

// Preferred voices by name (Edge, Chrome, Windows, macOS); the user can change them.
const ADVISOR_HINTS = ["aria", "jenny", "natural", "google us english", "zira", "samantha"];
const CUSTOMER_HINTS = ["guy", "davis", "google uk english male", "david", "mark", "daniel", "alex"];

/** Text as it should be heard: no 32-character order numbers, amounts and acronyms read out. */
export function speechText(text: string): string {
  return text
    .replace(/\b[0-9a-f]{32}\b/gi, (id) => `ending in ${id.slice(-4).split("").join(" ")}`)
    .replace(/R\$\s?(\d[\d.,]*)/g, "$1 reais")
    .replace(/\bCPF\b/g, "C P F")
    .replace(/[*_`#>]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** Short pieces of at most `max` characters, cut at sentence ends: Chrome stops reading
 * a single long utterance after about 15 seconds. */
export function speechChunks(text: string, max = 220): string[] {
  const sentences = text.match(/[^.!?]+[.!?]*\s*/g) ?? [text];
  const chunks: string[] = [];
  let current = "";
  for (const sentence of sentences) {
    if (current && (current + sentence).length > max) {
      chunks.push(current.trim());
      current = "";
    }
    if (sentence.length > max) {
      chunks.push(...(sentence.match(new RegExp(`.{1,${max}}(\\s|$)`, "g")) ?? [sentence]).map((s) => s.trim()));
      continue;
    }
    current += sentence;
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks.filter(Boolean);
}

/**
 * The English voices of this browser (all voices if none is English).
 */
function englishVoices(): SpeechSynthesisVoice[] {
  const all = window.speechSynthesis.getVoices();
  const english = all.filter((v) => v.lang?.toLowerCase().startsWith("en"));
  return english.length ? english : all;
}

/**
 * The first voice whose name contains a hint (never the other role's voice).
 */
function pickVoice(voices: SpeechSynthesisVoice[], hints: string[], avoid?: string): SpeechSynthesisVoice | undefined {
  for (const hint of hints) {
    const voice = voices.find((v) => v.name.toLowerCase().includes(hint) && v.voiceURI !== avoid);
    if (voice) return voice;
  }
  return voices.find((v) => v.voiceURI !== avoid) ?? voices[0];
}

interface VoiceSettings {
  enabled: boolean;
  rate: number;
  advisor?: string; // voiceURI chosen by the user
  customer?: string;
}

const STORE = "callverse.voice";

/**
 * Voice settings saved in the browser (voice mode is off by default).
 */
function loadSettings(): VoiceSettings {
  try {
    return { enabled: false, rate: 1, ...JSON.parse(localStorage.getItem(STORE) ?? "{}") };
  } catch {
    return { enabled: false, rate: 1 };
  }
}

/** Speech engine of one page: settings, voices, queue and the message being spoken. */
export function useVoice() {
  const [settings, setSettings] = useState<VoiceSettings>(loadSettings);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [speaking, setSpeaking] = useState<string | null>(null);
  const [speakingRole, setSpeakingRole] = useState<VoiceRole | null>(null);
  // Lip sync: +1 for every spoken word. Voices that report no word boundaries
  // (some online voices) get a steady talking motion instead ("loop").
  const [word, setWord] = useState(0);
  const [lipSync, setLipSync] = useState<"words" | "loop">("loop");
  const currentKey = useRef<string | null>(null);
  const alive = useRef<SpeechSynthesisUtterance[]>([]); // Chrome drops events of collected utterances

  useEffect(() => {
    if (!VOICE_SUPPORTED) return;
    const update = () => setVoices(englishVoices());
    update();
    window.speechSynthesis.addEventListener("voiceschanged", update);
    return () => {
      window.speechSynthesis.removeEventListener("voiceschanged", update);
      window.speechSynthesis.cancel();
    };
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem(STORE, JSON.stringify(settings));
    } catch {
      /* private mode: settings only last for this visit */
    }
  }, [settings]);

  // The user's chosen voices, or good defaults; the customer never gets the advisor's voice.
  const advisorVoice = voices.find((v) => v.voiceURI === settings.advisor) ?? pickVoice(voices, ADVISOR_HINTS);
  const customerVoice =
    voices.find((v) => v.voiceURI === settings.customer) ?? pickVoice(voices, CUSTOMER_HINTS, advisorVoice?.voiceURI);

  const stop = useCallback(() => {
    if (VOICE_SUPPORTED) window.speechSynthesis.cancel();
    alive.current = [];
    currentKey.current = null;
    setSpeaking(null);
    setSpeakingRole(null);
  }, []);

  /** Queue a message; `key` identifies it for the "speaking" indicator. */
  const speak = useCallback(
    (key: string, text: string, role: VoiceRole, persona?: string) => {
      if (!VOICE_SUPPORTED) return;
      const voice = role === "advisor" ? advisorVoice : customerVoice;
      const prosody = role === "customer" ? PERSONA_PROSODY[persona ?? "normal"] ?? PERSONA_PROSODY.normal : PERSONA_PROSODY.normal;
      // Clean the text for speech, then cut it into short pieces.
      const chunks = speechChunks(speechText(text));
      window.speechSynthesis.resume(); // Chrome can stay paused after the tab was hidden
      chunks.forEach((chunk, index) => {
        const utterance = new SpeechSynthesisUtterance(chunk);
        if (voice) {
          utterance.voice = voice;
          utterance.lang = voice.lang;
        }
        utterance.rate = Math.min(2, prosody.rate * settings.rate);
        utterance.pitch = prosody.pitch;
        if (index === 0) {
          utterance.onstart = () => {
            currentKey.current = key;
            setSpeaking(key);
            setSpeakingRole(role);
            setLipSync("loop");
          };
        }
        // Each spoken word moves the avatar's mouth (lip sync).
        utterance.onboundary = (event) => {
          if (!event.name || event.name === "word") {
            setLipSync("words");
            setWord((n) => n + 1);
          }
        };
        if (index === chunks.length - 1) {
          utterance.onend = utterance.onerror = () => {
            alive.current = alive.current.filter((u) => u !== utterance);
            setSpeaking((current) => (current === key ? null : current));
            if (currentKey.current === key) {
              currentKey.current = null;
              setSpeakingRole(null);
            }
          };
        }
        alive.current.push(utterance);
        window.speechSynthesis.speak(utterance);
      });
    },
    [advisorVoice, customerVoice, settings.rate],
  );

  /** Read one message now (the Listen button): whatever was playing stops. */
  const replay = useCallback(
    (key: string, text: string, role: VoiceRole, persona?: string) => {
      stop();
      speak(key, text, role, persona);
    },
    [stop, speak],
  );

  const setEnabled = useCallback(
    (enabled: boolean) => {
      setSettings((s) => ({ ...s, enabled }));
      if (!enabled) stop();
    },
    [stop],
  );

  return {
    supported: VOICE_SUPPORTED,
    // false: this browser only has voices for other languages (English would sound wrong)
    hasEnglish: voices.some((v) => v.lang?.toLowerCase().startsWith("en")),
    enabled: VOICE_SUPPORTED && settings.enabled,
    rate: settings.rate,
    voices,
    advisorVoice,
    customerVoice,
    speaking,
    speakingRole,
    word,
    lipSync,
    speak,
    replay,
    stop,
    setEnabled,
    setRate: (rate: number) => setSettings((s) => ({ ...s, rate })),
    setVoice: (role: VoiceRole, voiceURI: string) => setSettings((s) => ({ ...s, [role]: voiceURI })),
  };
}

export type Voice = ReturnType<typeof useVoice>;

/** Who speaks a message, or null to stay silent (for example what the human typed). */
export type SpeakerOf = (message: ChatMessage) => { role: VoiceRole; persona?: string } | null;

/** Reads every new message aloud while voice mode is on. Messages that arrived while it
 * was off are not read back when it is switched on. */
export function useAutoSpeak(messages: ChatMessage[], voice: Voice, speakerOf: SpeakerOf) {
  const spoken = useRef(messages.length);
  const who = useRef(speakerOf);
  who.current = speakerOf;
  useEffect(() => {
    if (spoken.current > messages.length) spoken.current = messages.length; // a new chat started
    if (!voice.enabled) {
      spoken.current = messages.length;
      return;
    }
    // Speak only the messages that are new since the last time.
    for (let i = spoken.current; i < messages.length; i++) {
      const speaker = who.current(messages[i]);
      if (speaker) voice.speak(String(i), messages[i].text, speaker.role, speaker.persona);
    }
    spoken.current = messages.length;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, voice.enabled]);
}
