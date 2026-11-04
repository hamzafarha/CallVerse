/**
 * Speech to text: the customer (or the human advisor) talks instead of typing.
 *
 * It uses the browser's own speech recognition (Web Speech API): Chrome and Edge send the audio to their
 * speech service, Safari to Apple's. Nothing runs on our server and nothing is installed. The microphone
 * only works on a secure page (https, or http://localhost), which is why the phone version uses https.
 *
 * How a turn works: start() opens the microphone; while you talk, `interim` holds the words heard so far;
 * when you pause, the browser closes the turn and `onFinal(text)` receives the whole sentence.
 */
import { useCallback, useEffect, useRef, useState } from "react";

// The browser's recognition object is not in TypeScript's standard types: these are the parts we use.
interface RecognitionAlternative {
  transcript: string;
}
interface RecognitionResult {
  isFinal: boolean;
  0: RecognitionAlternative;
}
interface RecognitionEvent {
  results: ArrayLike<RecognitionResult>;
}
interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type RecognitionClass = new () => Recognition;

/** Chrome, Edge and Safari name it webkitSpeechRecognition; the standard name is SpeechRecognition. */
function recognitionClass(): RecognitionClass | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionClass; webkitSpeechRecognition?: RecognitionClass };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export const SPEECH_INPUT_SUPPORTED = recognitionClass() !== null;

/** Languages offered in the voice menu (the agents always answer in English). */
export const SPEECH_LANGUAGES = [
  { value: "en-US", label: "English (US)" },
  { value: "en-GB", label: "English (UK)" },
  { value: "fr-FR", label: "Français" },
];

// The browser's error codes, in plain words.
const ERRORS: Record<string, string> = {
  "not-allowed": "Microphone blocked: allow it for this site (icon in the address bar), then try again.",
  "service-not-allowed": "This browser does not allow speech recognition here.",
  "no-speech": "I did not hear anything. Click the microphone and speak again.",
  "audio-capture": "No microphone found on this device.",
  network: "Speech recognition needs the internet: the browser sends the audio to its speech service.",
  "language-not-supported": "This language is not available for speech recognition in this browser.",
};

/** Why the microphone cannot work on this page, or null when it can. */
export function speechUnavailableReason(): string | null {
  if (!SPEECH_INPUT_SUPPORTED) return "This browser has no speech recognition: use Chrome, Edge or Safari.";
  if (typeof window !== "undefined" && !window.isSecureContext)
    return "The microphone needs a secure page (https, or localhost on this computer).";
  return null;
}

interface SpeechSettings {
  lang: string;
  autoSend: boolean; // send the sentence as soon as you stop talking
  handsFree: boolean; // listen again by itself after each answer (a phone-call feel)
}

const STORE = "callverse.speech";
const DEFAULTS: SpeechSettings = { lang: "en-US", autoSend: true, handsFree: false };

/** Settings saved in the browser. */
function loadSettings(): SpeechSettings {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(STORE) ?? "{}") };
  } catch {
    return DEFAULTS;
  }
}

/** One microphone for one page. `onFinal` receives each finished sentence. */
export function useSpeechInput(onFinal: (text: string) => void) {
  const [settings, setSettings] = useState<SpeechSettings>(loadSettings);
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recognition = useRef<Recognition | null>(null);
  const heard = useRef({ final: "", partial: "" });
  const discard = useRef(false);
  // Always call the latest onFinal (the page re-renders, the microphone keeps running).
  const callback = useRef(onFinal);
  callback.current = onFinal;

  useEffect(() => {
    try {
      localStorage.setItem(STORE, JSON.stringify(settings));
    } catch {
      /* private mode: settings only last for this visit */
    }
  }, [settings]);
  // Leaving the page closes the microphone.
  useEffect(() => () => recognition.current?.abort(), []);

  const start = useCallback(() => {
    const Recognizer = recognitionClass();
    const reason = speechUnavailableReason();
    if (!Recognizer || reason) {
      setError(reason);
      return;
    }
    recognition.current?.abort();
    const r = new Recognizer();
    r.lang = settings.lang;
    r.continuous = false; // one sentence per turn: the browser stops after a short pause
    r.interimResults = true; // words appear while you talk
    r.maxAlternatives = 1;
    heard.current = { final: "", partial: "" };
    discard.current = false;
    setInterim("");
    setError(null);
    r.onstart = () => setListening(true);
    r.onresult = (event) => {
      let final = "";
      let partial = "";
      for (let i = 0; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) final += result[0].transcript;
        else partial += result[0].transcript;
      }
      heard.current = { final, partial };
      setInterim(`${final} ${partial}`.trim());
    };
    r.onerror = (event) => {
      if (event.error !== "aborted") setError(ERRORS[event.error] ?? `Speech recognition error: ${event.error}`);
    };
    // The turn is over: hand the sentence to the page (unless it was cancelled).
    r.onend = () => {
      if (recognition.current === r) recognition.current = null;
      setListening(false);
      setInterim("");
      const said = (heard.current.final || heard.current.partial).trim();
      if (said && !discard.current) callback.current(said);
    };
    recognition.current = r;
    try {
      r.start();
    } catch {
      setError("The microphone is already in use.");
    }
  }, [settings.lang]);

  /** Stop listening now and keep what was heard. */
  const stop = useCallback(() => recognition.current?.stop(), []);
  /** Stop listening and throw away what was heard. */
  const cancel = useCallback(() => {
    discard.current = true;
    recognition.current?.abort();
  }, []);

  return {
    supported: SPEECH_INPUT_SUPPORTED,
    unavailable: speechUnavailableReason(),
    listening,
    interim,
    error,
    clearError: () => setError(null),
    start,
    stop,
    cancel,
    toggle: () => (recognition.current ? stop() : start()),
    lang: settings.lang,
    autoSend: settings.autoSend,
    handsFree: settings.handsFree,
    setLang: (lang: string) => setSettings((s) => ({ ...s, lang })),
    setAutoSend: (autoSend: boolean) => setSettings((s) => ({ ...s, autoSend })),
    setHandsFree: (handsFree: boolean) => setSettings((s) => ({ ...s, handsFree })),
  };
}

export type SpeechInput = ReturnType<typeof useSpeechInput>;
