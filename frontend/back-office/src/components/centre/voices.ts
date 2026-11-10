/**
 * The voices of the contact centre page: every person on the floor speaks with their own voice.
 *
 * It uses the browser's speech engine (Web Speech API: no server, no download), like the voice mode of the
 * front office (shared lib/voice.ts, whose text cleaning and cutting it reuses). Voices are dealt like cards,
 * by role and by id, never chosen from a name: the staff always keep the same voice, each advisor gets a voice
 * from the desk number, and each customer one from their id, with a pace that follows the persona (impatient
 * customers speak faster, patient ones slower).
 *
 * say() returns when the sentence has been said, so the director keeps a bubble on screen until its voice
 * ends (subtitles and voice stay together). The speech engine reads one sentence at a time: when several
 * customers are on the floor, their sentences simply wait their turn.
 */
import { VOICE_SUPPORTED, speechChunks, speechText } from "@callverse/shared";
import { advisorNumber, hashOf, type Role } from "./people";

export interface Speaker {
  role: Role;
  id: string; // the person's id: "advisor-03", a customer id, or the role for the staff
  persona?: string; // customers: impatient, normal or patient
}

const PERSONA: Record<string, { rate: number; pitch: number }> = {
  impatient: { rate: 1.15, pitch: 1.04 },
  normal: { rate: 1, pitch: 1 },
  patient: { rate: 0.92, pitch: 0.97 },
};

// The staff's voices: the first cards of the deck, so they never change.
const STAFF_CARD: Partial<Record<Role, number>> = { reception: 0, quality: 1, supervisor: 2, manager: 3 };
const STAFF_PROSODY: Partial<Record<Role, { rate: number; pitch: number }>> = {
  reception: { rate: 1.05, pitch: 1.06 },
  supervisor: { rate: 0.95, pitch: 0.9 },
  quality: { rate: 1, pitch: 1 },
};

/** The best voices first: Edge's natural voices, then Google's, then the computer's own. */
function quality(voice: SpeechSynthesisVoice): number {
  const name = voice.name.toLowerCase();
  if (name.includes("natural")) return 0;
  if (name.includes("online") || name.includes("google")) return 1;
  return 2;
}

export class VoiceCast {
  enabled = false;
  private deck: SpeechSynthesisVoice[] = [];
  private chosen = new Map<string, { voice?: SpeechSynthesisVoice; rate: number; pitch: number }>();
  private alive: SpeechSynthesisUtterance[] = []; // Chrome drops the events of utterances it garbage-collects

  constructor() {
    if (!VOICE_SUPPORTED) return;
    const load = () => {
      const all = window.speechSynthesis.getVoices();
      const english = all.filter((v) => v.lang?.toLowerCase().startsWith("en"));
      this.deck = (english.length ? english : all).slice().sort((a, b) => quality(a) - quality(b) || a.name.localeCompare(b.name));
      this.chosen.clear();
    };
    load();
    window.speechSynthesis.addEventListener("voiceschanged", load);
  }

  get supported() {
    return VOICE_SUPPORTED;
  }

  get count() {
    return this.deck.length;
  }

  /** The voice of one person (chosen once, then always the same). `avoid`: a voice already used by the
   * person they talk to (a customer should not sound like the advisor). */
  private voiceOf(speaker: Speaker, avoid?: string) {
    const key = `${speaker.role}:${speaker.id}`;
    const known = this.chosen.get(key);
    if (known) return known;
    const deck = this.deck;
    let voice: SpeechSynthesisVoice | undefined;
    let { rate, pitch } = STAFF_PROSODY[speaker.role] ?? { rate: 1, pitch: 1 };
    if (deck.length) {
      if (speaker.role in STAFF_CARD) voice = deck[(STAFF_CARD[speaker.role] ?? 0) % deck.length];
      else if (speaker.role === "advisor") {
        voice = deck[(4 + advisorNumber(speaker.id)) % deck.length];
        pitch = [1, 0.95, 1.05, 0.98][advisorNumber(speaker.id) % 4];
      } else {
        const h = hashOf(speaker.id);
        voice = deck[h % deck.length];
        if (deck.length > 1 && voice.voiceURI === avoid) voice = deck[(h + 1) % deck.length];
        const persona = PERSONA[speaker.persona ?? "normal"] ?? PERSONA.normal;
        rate = persona.rate;
        pitch = persona.pitch * (0.94 + ((h >>> 8) % 13) / 100); // a little different for each customer
      }
    }
    const chosen = { voice, rate, pitch };
    this.chosen.set(key, chosen);
    return chosen;
  }

  /** The voice URI of a person, if they already spoke (used to keep a customer apart from the advisor). */
  voiceUri(speaker: Speaker): string | undefined {
    return this.chosen.get(`${speaker.role}:${speaker.id}`)?.voice?.voiceURI;
  }

  /** Say a text with the person's voice; returns when it has been said (at once when the voices are off).
   * `speed`: the page's playback speed (2x speaks a little faster). */
  say(text: string, speaker: Speaker, speed = 1, avoid?: string): Promise<void> {
    const clean = speechText(text);
    if (!this.enabled || !VOICE_SUPPORTED || !clean) return Promise.resolve();
    const { voice, rate, pitch } = this.voiceOf(speaker, avoid);
    const chunks = speechChunks(clean);
    const pace = Math.min(2, rate * (speed > 1 ? 1.25 : 1));
    return new Promise((resolve) => {
      let finished = false;
      const finish = () => {
        if (finished) return;
        finished = true;
        window.clearTimeout(guard);
        resolve();
      };
      // Safety: a speech engine sometimes never says "end": stop waiting after a generous delay.
      const guard = window.setTimeout(finish, 3000 + (clean.length * 95) / pace);
      window.speechSynthesis.resume(); // Chrome can stay paused after the tab was hidden
      chunks.forEach((chunk, index) => {
        const utterance = new SpeechSynthesisUtterance(chunk);
        if (voice) {
          utterance.voice = voice;
          utterance.lang = voice.lang;
        }
        utterance.rate = pace;
        utterance.pitch = pitch;
        if (index === chunks.length - 1) {
          utterance.onend = utterance.onerror = () => {
            this.alive = this.alive.filter((u) => u !== utterance);
            finish();
          };
        }
        this.alive.push(utterance);
        window.speechSynthesis.speak(utterance);
      });
    });
  }

  /** Silence now (the voices were switched off, or the page closes). Waiting sentences end at once. */
  stop() {
    if (VOICE_SUPPORTED) window.speechSynthesis.cancel();
    this.alive = [];
  }
}
