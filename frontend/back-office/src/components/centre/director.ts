/**
 * The director of the contact centre page: it turns the REAL events of each chat into moves on the floor.
 *
 * The server sends every step of every running chat on /ws/centre (orchestration/centre.py): the centre's own
 * AI customers, people writing on the customer portal, phone calls, the advisor desk and the Agent theater.
 * The director reads each chat's events one by one, like a film script, and shows each one:
 *
 *   ready            -> the customer walks in through the door, to the reception
 *   message          -> a speech bubble with the real words (customer or advisor)
 *   stage: workforce -> the receptionist reads the request ("...")
 *   routing          -> the receptionist's card (problem, desk, advisors on duty, expected wait); the
 *                       receptionist points to the desk and the customer walks there
 *   stage: advisor   -> "..." above the advisor, and a badge for each tool (order lookup, rules engine...)
 *   escalate_to_human-> the supervisor walks over
 *   autopilot        -> a person takes over the chat at the desk (or gives it back to the AI)
 *   stage: quality   -> the quality lead walks to the desk
 *   review           -> the quality lead shows the Quality score; the customer leaves with the rating given
 *   done             -> everyone goes back to their place; the KPI wall counts the chat
 *
 * Several customers can be on the floor at once. Like in a real centre, they take turns: one customer at a
 * time at the reception counter (the others wait in the waiting area), an advisor handles up to two chats at
 * once (like real chat agents; a third customer waits), and the supervisor and the quality lead go to one
 * desk at a time.
 *
 * Nothing is invented: every move comes from an event. Only the PACE is changed: the offline agents can finish
 * a whole chat in less than a second, so each step stays on screen long enough to be read (like subtitles),
 * and the events that arrive meanwhile wait in a queue.
 *
 * With the voices on (voices.ts), each bubble is also read aloud by its person, and it stays until the voice
 * ends. Besides the real messages, three short announcements give real events a voice: the receptionist
 * names the desk, the supervisor says which desk they join, and the quality lead reads the score. Words that a
 * person already said out loud (a message typed by voice) are not read again.
 */
import { CALLER_LABEL, TOOL_LABEL, humanize, wsUrl } from "@callverse/shared";
import { useEffect, useRef, useState } from "react";
import {
  AISLE_X,
  type Bubble,
  DESK_CAPACITY,
  DESK_COUNT,
  DOOR,
  LOBBY,
  PERSON_H,
  QUALITY_HOME,
  RECEPTION,
  RECEPTION_FRONT,
  STAFF_AISLE_X,
  SUPERVISOR_HOME,
  type Point,
  type ToolPop,
  WAITING_SPOTS,
  type Walker,
  deskCentre,
  deskFront,
  deskSupport,
} from "./floor";
import { STAFF_LOOK, advisorName, lookFor, type Look, type Pose } from "./people";
import { VoiceCast, type Speaker } from "./voices";

/** One message of /ws/centre: which chat, where it comes from, its step number, and the agents' event. */
export interface FeedMessage {
  chat: string;
  channel: string; // "centre", "web" (portal), "phone", "agents" (theater or advisor desk)
  seq: number;
  event: Record<string, any>;
}

/** Everything drawn on the floor at one moment. */
export interface Scene {
  walkers: Record<string, Walker>;
  bubbles: Record<string, Bubble>; // one per speaker (key = owner)
  deskTools: Record<number, ToolPop[]>; // the advisor's tool badges, by desk
  walkerTools: Record<string, ToolPop[]>; // the customer's tool badges (its phone), by chat
  thinking: Record<string, boolean>; // "reception", "desk-3", "quality", or a chat id (customer typing)
  receptionPose: Pose;
  slots: string[]; // the advisor sitting at each desk ("advisor-00"...)
  serving: Record<number, string[]>; // desk -> the chats it serves now (at most two)
  caption: { key: number; text: string };
  earlier: { key: number; text: string }[]; // the two captions before (several stories can run at once)
}

type Staff = "supervisor" | "quality";

const WALK_SPEED = 260; // stage pixels per second
const ADVISOR_HEAD = 104; // from a desk's top to above the advisor's head

/** How long a text stays on screen: about 24 characters a second, between 2.6 and 9 seconds. */
const readMs = (text: string) => Math.min(9000, Math.max(2600, 1400 + text.length * 42));

/** A long message is cut at the end of a sentence when possible, else at a word (the full text is in the
 * advisor's history). The voice reads the same words as the bubble. */
function shorten(text: string, max = 280): string {
  const clean = String(text ?? "").trim();
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max);
  const sentence = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("! "), cut.lastIndexOf("? "));
  if (sentence > max * 0.5) return `${cut.slice(0, sentence + 1)} …`;
  return `${cut.slice(0, cut.lastIndexOf(" ") > max * 0.6 ? cut.lastIndexOf(" ") : max)}…`;
}

/** What the voice reads: the bubble's words, without the "…" of a cut message. */
const spoken = (bubbleText: string) => bubbleText.replace(/\s*…$/, "");

/** Who plays the customer, by where the chat comes from. */
const WHO: Record<string, string> = {
  centre: "Client agent (AI customer)",
  agents: "Client agent (AI customer)",
  web: "real customer · web chat",
  phone: "real customer · phone call",
  visitor: "visitor at the centre (speaking)",
};

const CUSTOMER_TOOL: Record<string, string> = {
  view_my_order_page: "checks the order page on the phone",
  check_my_waiting_time: "looks at how long the chat has lasted",
  send_evidence: "sends photos from the phone",
};

export function emptyScene(): Scene {
  const staff = (id: Staff, at: Point, name: string): Walker => ({
    id,
    role: id,
    name,
    look: STAFF_LOOK[id],
    x: at.x,
    y: at.y,
    ms: 0,
    walking: false,
    visible: true,
    pose: "stand",
  });
  return {
    walkers: { supervisor: staff("supervisor", SUPERVISOR_HOME, "Supervisor"), quality: staff("quality", QUALITY_HOME, "Quality lead") },
    bubbles: {},
    deskTools: {},
    walkerTools: {},
    thinking: {},
    receptionPose: "stand",
    slots: Array.from({ length: DESK_COUNT }, (_, i) => `advisor-${String(i).padStart(2, "0")}`),
    serving: {},
    caption: { key: 0, text: "The centre is open. Press “A customer walks in”, or chat from the customer portal or a phone." },
    earlier: [],
  };
}

/** The events of one chat, waiting to be shown (the director takes them one at a time). */
class ChatQueue {
  private items: Record<string, any>[] = [];
  private waiting: ((event: Record<string, any> | null) => void) | null = null;
  private closed = false;

  push(event: Record<string, any>) {
    if (this.waiting) {
      const wake = this.waiting;
      this.waiting = null;
      wake(event);
    } else this.items.push(event);
  }

  close() {
    this.closed = true;
    this.waiting?.(null);
    this.waiting = null;
  }

  next(): Promise<Record<string, any> | null> {
    if (this.items.length) return Promise.resolve(this.items.shift()!);
    if (this.closed) return Promise.resolve(null);
    return new Promise((resolve) => (this.waiting = resolve));
  }
}

/** A line of chats waiting for a place or a person (the reception counter, the quality lead): first come,
 * first served. */
class Turns {
  private line: string[] = [];
  join(chat: string) {
    if (!this.line.includes(chat)) this.line.push(chat);
  }
  leave(chat: string) {
    this.line = this.line.filter((c) => c !== chat);
  }
  isFirst(chat: string) {
    return this.line[0] === chat;
  }
  get empty() {
    return this.line.length === 0;
  }
}

class Stopped extends Error {}

/** What the director remembers about one customer's story. */
interface Story {
  chat: string;
  channel: string;
  name: string;
  who: string;
  look: Look;
  persona?: string; // impatient, normal or patient: the pace of the customer's voice
  slot: number | null; // the desk, once routed
  place: number | null; // 0 or 1: where the customer stands in front of the desk
  advisor: string | null;
  at: "door" | "waiting" | "reception" | "desk" | "gone";
  escalated: boolean;
}

let uid = 0;
const nextKey = () => `k${++uid}`;

export class Director {
  speed = 1;
  private scene = emptyScene();
  private queues = new Map<string, ChatQueue>();
  private nextSeq = new Map<string, number>();
  private finished = new Set<string>();
  private stories = new Map<string, string>(); // chat -> channel, while its story plays
  private lastUsed: Record<number, number> = {};
  private places: Record<number, (string | null)[]> = {}; // desk -> who stands at place 0 and place 1
  private seats: (string | null)[] = WAITING_SPOTS.map(() => null);
  private reception = new Turns();
  private turns: Record<Staff, Turns> = { supervisor: new Turns(), quality: new Turns() };
  private stopped = false;

  constructor(
    private render: (scene: Scene) => void,
    private hooks: { onReview: () => void; onStories: (count: { centre: number; all: number }) => void },
    private cast: VoiceCast = new VoiceCast(),
  ) {}

  /** One message from /ws/centre: queue it in its chat (a new chat starts a new story). */
  receive(message: FeedMessage) {
    const { chat, seq, event } = message;
    if (this.stopped || this.finished.has(chat)) return;
    if (seq < (this.nextSeq.get(chat) ?? 0)) return; // already shown (the feed replays after a reconnection)
    this.nextSeq.set(chat, seq + 1);
    let queue = this.queues.get(chat);
    if (!queue) {
      queue = new ChatQueue();
      this.queues.set(chat, queue);
      void this.play(chat, message.channel, queue);
    }
    queue.push(event);
  }

  /** A line in the caption from the page itself (for example when the twin crowd starts). */
  announce(text: string) {
    this.caption(text);
  }

  /** The page closes: every story stops, and the voices go quiet. */
  stop() {
    this.stopped = true;
    for (const queue of this.queues.values()) queue.close();
    this.cast.stop();
  }

  // ------------------------------------------------------------------ scene edits
  private commit(change: Partial<Scene>) {
    this.scene = { ...this.scene, ...change };
    this.render(this.scene);
  }

  private patchWalker(id: string, patch: Partial<Walker>) {
    const walker = this.scene.walkers[id];
    if (walker) this.commit({ walkers: { ...this.scene.walkers, [id]: { ...walker, ...patch } } });
  }

  private say(bubble: Omit<Bubble, "key" | "z">) {
    // A new message greys the older messages of the same chat (cards and scores stay as they are), and it is
    // drawn on top of every other bubble (z = creation order).
    const bubbles: Record<string, Bubble> = {};
    for (const [owner, other] of Object.entries(this.scene.bubbles))
      bubbles[owner] = bubble.kind === "say" && other.kind === "say" && other.chat === bubble.chat ? { ...other, dim: true } : other;
    bubbles[bubble.owner] = { ...bubble, key: nextKey(), z: ++uid };
    this.commit({ bubbles });
  }

  private unsay(owner: string, chat?: string) {
    const bubble = this.scene.bubbles[owner];
    if (!bubble || (chat && bubble.chat !== chat)) return; // with a chat: only if it is still that chat's
    const { [owner]: _gone, ...bubbles } = this.scene.bubbles;
    this.commit({ bubbles });
  }

  private think(key: string, on: boolean) {
    if (!!this.scene.thinking[key] !== on) this.commit({ thinking: { ...this.scene.thinking, [key]: on } });
  }

  private caption(text: string) {
    const earlier = [this.scene.caption, ...this.scene.earlier].slice(0, 2);
    // "Paula S.." -> "Paula S." (a name that ends with an initial at the end of a sentence)
    this.commit({ caption: { key: this.scene.caption.key + 1, text: text.replace(/\.\.(\s|$)/g, ".$1") }, earlier });
  }

  private deskTool(slot: number, pop: Omit<ToolPop, "key">) {
    const pops = [...(this.scene.deskTools[slot] ?? []), { ...pop, key: nextKey() }].slice(-3);
    this.commit({ deskTools: { ...this.scene.deskTools, [slot]: pops } });
  }

  /** Wait (shorter at a higher speed). Throws when the page closed, which ends the story. */
  private async pause(ms: number) {
    await new Promise((resolve) => setTimeout(resolve, ms / this.speed));
    if (this.stopped) throw new Stopped();
  }

  /** Keep a bubble on screen long enough to read it and, with the voices on, until its person has said it
   * (a speaker icon shows on the bubble meanwhile). */
  private async hold(ms: number, voice?: { owner: string; text: string; speaker: Speaker; avoid?: string }) {
    if (!voice || !this.cast.enabled) return this.pause(ms);
    this.speaking(voice.owner, true);
    try {
      await Promise.all([this.pause(ms), this.cast.say(voice.text, voice.speaker, this.speed, voice.avoid)]);
    } finally {
      this.speaking(voice.owner, false);
    }
    if (this.stopped) throw new Stopped();
  }

  private speaking(owner: string, on: boolean) {
    const bubble = this.scene.bubbles[owner];
    if (bubble && !!bubble.speaking !== on) this.commit({ bubbles: { ...this.scene.bubbles, [owner]: { ...bubble, speaking: on } } });
  }

  /** Wait until a condition is true (checked a few times a second). */
  private async until(condition: () => boolean) {
    while (!condition()) await this.pause(350);
  }

  /** Walk through the points one after the other (the floor's walkways), at a steady speed. */
  private async walk(id: string, points: Point[]) {
    for (const point of points) {
      const walker = this.scene.walkers[id];
      if (!walker) return;
      const ms = (Math.hypot(point.x - walker.x, point.y - walker.y) / WALK_SPEED) * 1000;
      if (ms < 20) continue;
      this.patchWalker(id, { x: point.x, y: point.y, ms: ms / this.speed, walking: true });
      await this.pause(ms);
    }
    this.patchWalker(id, { walking: false });
  }

  // ------------------------------------------------------------- places and turns
  /** A place in the waiting area (the chairs first, then standing in line). */
  private seat(chat: string): Point {
    let i = this.seats.indexOf(chat);
    if (i < 0) {
      i = this.seats.indexOf(null);
      if (i < 0) return WAITING_SPOTS[WAITING_SPOTS.length - 1]; // a full waiting area: stand at the end
      this.seats[i] = chat;
    }
    return WAITING_SPOTS[i];
  }

  private unseat(chat: string) {
    const i = this.seats.indexOf(chat);
    if (i >= 0) this.seats[i] = null;
  }

  /** How many other chats the desk serves now. */
  private othersAt(slot: number, chat: string) {
    return (this.places[slot] ?? []).filter((c) => c && c !== chat).length;
  }

  /** Take a place in front of the desk (0 = left, 1 = right). */
  private standAt(slot: number, chat: string): number {
    const places = this.places[slot] ?? Array.from({ length: DESK_CAPACITY }, () => null);
    let place = places.indexOf(chat);
    if (place < 0) place = Math.max(0, places.indexOf(null));
    places[place] = chat;
    this.places[slot] = places;
    this.commit({ serving: { ...this.scene.serving, [slot]: places.filter((c): c is string => !!c) } });
    return place;
  }

  /** Leave the desk; when nobody is left, its badges, bubble and "..." go too. */
  private leaveDesk(slot: number, chat: string) {
    const places = (this.places[slot] ?? []).map((c) => (c === chat ? null : c));
    this.places[slot] = places;
    const left = places.filter((c): c is string => !!c);
    this.commit({ serving: { ...this.scene.serving, [slot]: left } });
    if (!left.length) {
      const { [slot]: _tools, ...deskTools } = this.scene.deskTools;
      this.commit({ deskTools });
      this.unsay(`desk-${slot}`);
      this.think(`desk-${slot}`, false);
    }
  }

  /** The desk of an advisor. A new advisor id takes the free desk used the longest time ago ("hot desk"). */
  private deskOf(advisor: string): number {
    let slot = this.scene.slots.indexOf(advisor);
    if (slot < 0) {
      const free = this.scene.slots.map((_, i) => i).filter((i) => !(this.scene.serving[i] ?? []).length);
      slot = free.sort((a, b) => (this.lastUsed[a] ?? 0) - (this.lastUsed[b] ?? 0))[0] ?? 0;
      const slots = [...this.scene.slots];
      slots[slot] = advisor;
      this.commit({ slots });
    }
    this.lastUsed[slot] = Date.now();
    return slot;
  }

  private isHome(id: Staff) {
    const home = id === "supervisor" ? SUPERVISOR_HOME : QUALITY_HOME;
    const walker = this.scene.walkers[id];
    return walker.x === home.x && walker.y === home.y;
  }

  /** A member of staff goes to a desk (behind it, next to the advisor), along the staff walkway. */
  private async staffTo(id: Staff, slot: number) {
    const spot = deskSupport(slot);
    const from = this.scene.walkers[id];
    await this.walk(id, [{ x: STAFF_AISLE_X, y: from.y }, { x: STAFF_AISLE_X, y: spot.y }, spot]);
  }

  private async staffHome(id: Staff) {
    if (this.isHome(id)) return;
    const home = id === "supervisor" ? SUPERVISOR_HOME : QUALITY_HOME;
    const from = this.scene.walkers[id];
    this.unsay(id);
    this.patchWalker(id, { pose: "stand" });
    await this.walk(id, [{ x: STAFF_AISLE_X, y: from.y }, { x: STAFF_AISLE_X, y: home.y }, home]);
  }

  /** The member of staff is free again: back to the office, unless another desk is waiting for them. */
  private releaseStaff(id: Staff, chat: string) {
    this.turns[id].leave(chat);
    if (this.turns[id].empty) void this.staffHome(id).catch(() => undefined);
  }

  private notify() {
    const all = this.stories.size;
    const centre = [...this.stories.values()].filter((channel) => channel === "centre").length;
    this.hooks.onStories({ centre, all });
  }

  // ------------------------------------------------------------------- the story
  private async play(chat: string, channel: string, queue: ChatQueue) {
    const story: Story = {
      chat,
      channel,
      name: "Customer",
      who: WHO[channel] ?? "customer",
      look: lookFor(chat),
      slot: null,
      place: null,
      advisor: null,
      at: "door",
      escalated: false,
    };
    this.stories.set(chat, channel);
    this.notify();
    try {
      for (;;) {
        const event = await queue.next();
        if (!event) break;
        await this.step(story, event);
        if (event.type === "done") break;
      }
    } catch (error) {
      if (!(error instanceof Stopped)) console.error("centre story", error);
    } finally {
      // Whatever happened, this chat gives back every place and turn it held.
      this.reception.leave(chat);
      this.unseat(chat);
      if (story.slot !== null) this.leaveDesk(story.slot, chat);
      if (!this.stopped) for (const id of ["supervisor", "quality"] as Staff[]) if (this.turns[id].isFirst(chat)) this.releaseStaff(id, chat);
      for (const id of ["supervisor", "quality"] as Staff[]) this.turns[id].leave(chat);
      this.finished.add(chat);
      this.queues.delete(chat);
      this.stories.delete(chat);
      if (!this.stopped) this.notify();
    }
  }

  private async step(s: Story, e: Record<string, any>) {
    switch (e.type) {
      case "ready":
        return this.arrive(s, e);
      case "message":
        return e.message?.speaker === "advisor" ? this.advisorSays(s, e.message) : this.customerSays(s, e.message);
      case "stage":
        return this.stage(s, e);
      case "routing":
        return this.route(s, e.routing ?? {});
      case "autopilot":
        return this.takeOver(s, !!e.on);
      case "review":
        return this.review(s, e);
      case "error":
        return this.problem(s, String(e.message ?? "unknown error"));
      case "done":
        return this.leave(s, !!e.reviewed);
      default:
        return; // advisor_state, suggestion: nothing to draw
    }
  }

  /** "ready": the customer comes in through the door and goes to the reception (or waits for it). */
  private async arrive(s: Story, e: Record<string, any>) {
    s.name = e.name || "Customer";
    s.look = lookFor(e.profile?.customer_unique_id || e.profile?.contact_id || s.chat);
    s.persona = e.profile?.persona;
    if (e.customer === "human" && s.channel !== "phone") s.who = WHO.web;
    const walker: Walker = { id: s.chat, role: "customer", name: s.name, look: s.look, ...DOOR, ms: 0, walking: false, visible: false, pose: "stand" };
    this.commit({ walkers: { ...this.scene.walkers, [s.chat]: walker } });
    await this.pause(80);
    this.patchWalker(s.chat, { visible: true });
    const engine = e.llm
      ? `The agents think with ${e.provider === "openrouter" ? "OpenRouter" : "local"} LLMs.`
      : "The agents use their offline backups (no LLM).";
    this.caption(`${s.name} walks in (${s.who}). ${engine}`);
    await this.walk(s.chat, [LOBBY]);
    // One customer at a time at the counter: the others wait in the waiting area.
    this.reception.join(s.chat);
    if (!this.reception.isFirst(s.chat)) {
      s.at = "waiting";
      this.caption(`${s.name} waits in the waiting area: the receptionist is busy with another customer.`);
      await this.walk(s.chat, [this.seat(s.chat)]);
      await this.until(() => this.reception.isFirst(s.chat));
      this.unseat(s.chat);
    }
    await this.walk(s.chat, [RECEPTION_FRONT]);
    s.at = "reception";
  }

  /** A customer's message: a speech bubble beside the customer, kept on screen long enough to read. */
  private async customerSays(s: Story, message: Record<string, any>) {
    if (!message) return;
    this.think(s.chat, false);
    const at = this.scene.walkers[s.chat] ?? { ...RECEPTION_FRONT };
    const files = (message.meta?.attachments ?? []).length;
    const words = shorten(message.text);
    const text = words + (files ? `  📎 ${files} file${files === 1 ? "" : "s"} attached` : "");
    const saidAloud = message.meta?.input === "voice"; // the person already said it: not read again
    const voice = saidAloud ? " · spoken" : "";
    this.say({
      owner: s.chat,
      chat: s.chat,
      role: "customer",
      look: s.look,
      placement: s.at === "desk" && s.place === 1 ? "right" : "left",
      x: at.x,
      y: at.y - PERSON_H,
      kind: "say",
      title: `${s.name} · ${s.who}${voice}`,
      text,
    });
    this.caption(s.at === "desk" ? `${s.name} answers ${advisorName(s.advisor ?? "")}.` : `${s.name} explains the problem at the reception.`);
    // A visitor knows what they just said: their bubble does not hold the story for reading.
    const reading = s.channel === "visitor" ? 900 : readMs(message.text ?? "");
    const speaker: Speaker = { role: "customer", id: s.chat, persona: s.persona };
    const avoid = s.advisor ? this.cast.voiceUri({ role: "advisor", id: s.advisor }) : undefined;
    await this.hold(reading, saidAloud ? undefined : { owner: s.chat, text: spoken(words), speaker, avoid });
  }

  /** An advisor's reply: a speech bubble above the advisor at the desk. */
  private async advisorSays(s: Story, message: Record<string, any>) {
    if (!message || s.slot === null) return;
    const slot = s.slot;
    const name = advisorName(s.advisor ?? "");
    const human = message.meta?.mode === "human";
    const tools = (message.meta?.tools ?? []).length;
    const c = deskCentre(slot);
    const words = shorten(message.text);
    this.think(`desk-${slot}`, false);
    this.say({
      owner: `desk-${slot}`,
      chat: s.chat,
      role: "advisor",
      look: lookFor(s.advisor ?? ""),
      placement: "above",
      x: c.x,
      y: c.y - ADVISOR_HEAD,
      kind: "say",
      title: `${name} · ${human ? "a person at the desk" : "Advisor agent (AI)"} · to ${s.name}`,
      text: words,
    });
    this.caption(`${name} answers ${s.name}${tools ? ` after ${tools} tool call${tools === 1 ? "" : "s"}` : ""}.`);
    // A person at the desk who typed: still read aloud (the room cannot hear the keyboard).
    await this.hold(readMs(message.text ?? ""), {
      owner: `desk-${slot}`,
      text: spoken(words),
      speaker: { role: "advisor", id: s.advisor ?? "advisor-00" },
    });
  }

  /** "stage": what an agent is doing right now (reading, a tool, typing, reviewing). */
  private async stage(s: Story, e: Record<string, any>) {
    if (e.agent === "workforce") {
      this.think("reception", true);
      this.caption(`The receptionist (Workforce agent) reads ${s.name}'s request…`);
      await this.pause(1000);
      return;
    }
    if (e.agent === "client") {
      if (e.step !== "tool") return this.think(s.chat, true); // typing
      const pops = [...(this.scene.walkerTools[s.chat] ?? []), { key: nextKey(), name: e.name, ok: e.ok !== false, caller: e.caller }].slice(-2);
      this.commit({ walkerTools: { ...this.scene.walkerTools, [s.chat]: pops } });
      this.caption(`${s.name} ${CUSTOMER_TOOL[e.name] ?? `uses ${TOOL_LABEL[e.name] ?? e.name}`}.`);
      await this.pause(1300);
      return;
    }
    if (e.agent === "quality") return this.qualityWalksOver(s);
    if (s.slot === null) return;
    const slot = s.slot;
    const name = advisorName(s.advisor ?? "");
    if (e.step === "start") {
      const { [slot]: _old, ...deskTools } = this.scene.deskTools; // a new turn: new tool badges
      this.commit({ deskTools });
      this.think(`desk-${slot}`, true);
    } else if (e.step === "generation") {
      this.think(`desk-${slot}`, true);
    } else if (e.step === "retrieval") {
      this.deskTool(slot, { name: "search_knowledge_base", ok: true, caller: "code" });
      this.caption(`${name} searches the help centre (knowledge base).`);
      await this.pause(900);
    } else if (e.step === "tool") {
      const ok = e.ok !== false;
      this.deskTool(slot, { name: e.name, ok, caller: e.caller });
      this.caption(`${name} uses a tool: ${TOOL_LABEL[e.name] ?? e.name} ${ok ? "✓" : "✗"} (${CALLER_LABEL[e.caller] ?? "tool call"}).`);
      await this.pause(1100);
      if (e.name === "escalate_to_human" && ok && !s.escalated) {
        s.escalated = true;
        await this.supervisorWalksOver(s, e.summary);
      }
    }
  }

  /** "routing": the Workforce agent's decision, then the customer walks to the chosen desk. */
  private async route(s: Story, routing: Record<string, any>) {
    const advisor = String(routing.assigned_desk ?? "advisor-00");
    const slot = this.deskOf(advisor);
    s.slot = slot;
    s.advisor = advisor;
    const name = advisorName(advisor);
    this.think("reception", false);
    const confidence = routing.confidence != null ? ` · ${Math.round(routing.confidence * 100)}% sure` : "";
    const wait =
      routing.is_live === false
        ? "The centre is closed at this hour: the chat waits for the morning."
        : `${routing.agents_on_duty ?? "?"} advisors on duty · expected wait ${Math.round(routing.expected_wait_seconds ?? 0)} s`;
    this.say({
      owner: "reception",
      chat: s.chat,
      role: "reception",
      look: STAFF_LOOK.reception,
      placement: "above",
      x: RECEPTION.x,
      y: RECEPTION.y - 150,
      kind: "card",
      title: "Routing · Workforce agent",
      lines: [`${humanize(routing.predicted_intent)}${confidence}`, `→ Desk ${slot + 1} · ${name}, the fastest advisor on this problem`, wait],
    });
    this.commit({ receptionPose: "point" });
    this.caption(`The Workforce agent sends ${s.name} to desk ${slot + 1}, ${name}: ${humanize(routing.predicted_intent).toLowerCase()}.`);
    await this.hold(3600, {
      owner: "reception",
      text: `${humanize(routing.predicted_intent)}. ${s.name}, please go to desk ${slot + 1}, with ${name}.`,
      speaker: { role: "reception", id: "reception" },
    });
    // The counter is free for the next customer as soon as this one walks away.
    this.unsay(s.chat);
    this.reception.leave(s.chat);
    // An advisor handles two chats at most: a third customer waits in the waiting area.
    if (this.othersAt(slot, s.chat) >= DESK_CAPACITY) {
      s.at = "waiting";
      this.caption(`${name} already handles ${DESK_CAPACITY} chats: ${s.name} waits in the waiting area.`);
      await this.walk(s.chat, [this.seat(s.chat)]);
      this.relaxReception(s.chat);
      await this.until(() => this.othersAt(slot, s.chat) < DESK_CAPACITY);
      this.unseat(s.chat);
    }
    s.place = this.standAt(slot, s.chat);
    const front = deskFront(slot, s.place);
    const from = this.scene.walkers[s.chat] ?? RECEPTION_FRONT;
    await this.walk(s.chat, [{ x: AISLE_X, y: from.y }, { x: AISLE_X, y: front.y }, front]);
    s.at = "desk";
    this.relaxReception(s.chat);
  }

  /** The receptionist stops pointing and the routing card goes (if no other customer is being routed). */
  private relaxReception(chat: string) {
    if (this.scene.bubbles.reception?.chat !== chat) return;
    this.unsay("reception");
    this.commit({ receptionPose: "stand" });
  }

  /** "autopilot": a person at the desk takes over the chat, or gives it back to the AI. */
  private async takeOver(s: Story, aiAnswers: boolean) {
    if (s.slot === null) return;
    this.caption(aiAnswers ? `The AI answers ${s.name} again at desk ${s.slot + 1}.` : `A person takes over ${s.name}'s chat at desk ${s.slot + 1}.`);
    await this.pause(1500);
  }

  /** escalate_to_human: the supervisor leaves the office and joins the desk. */
  private async supervisorWalksOver(s: Story, summary?: string) {
    if (s.slot === null) return;
    this.turns.supervisor.join(s.chat);
    await this.until(() => this.turns.supervisor.isFirst(s.chat));
    this.caption(`The case is escalated: the supervisor walks over to desk ${s.slot + 1}.`);
    await this.staffTo("supervisor", s.slot);
    const at = this.scene.walkers.supervisor;
    this.say({
      owner: "supervisor",
      chat: s.chat,
      role: "supervisor",
      look: STAFF_LOOK.supervisor,
      placement: "left",
      x: at.x,
      y: at.y - PERSON_H,
      kind: "card",
      title: "Supervisor · escalation",
      lines: [`The Advisor agent handed ${s.name}'s chat to a person.`, ...(summary ? [shorten(summary, 120)] : [])],
    });
    await this.hold(2800, {
      owner: "supervisor",
      text: `Supervisor joining desk ${s.slot + 1}.`,
      speaker: { role: "supervisor", id: "supervisor" },
    });
  }

  /** "stage: quality": the chat is over; the quality lead comes to the desk to review it. */
  private async qualityWalksOver(s: Story) {
    if (s.slot === null) return;
    this.think(s.chat, false);
    if (this.turns.supervisor.isFirst(s.chat)) this.releaseStaff("supervisor", s.chat);
    this.turns.quality.join(s.chat);
    if (!this.turns.quality.isFirst(s.chat)) {
      this.caption(`${s.name}'s chat is over: it waits for the quality lead, who is reviewing another chat.`);
      await this.until(() => this.turns.quality.isFirst(s.chat));
    }
    this.caption(`${s.name}'s chat is over. The quality lead (Quality agent) reviews it…`);
    await this.staffTo("quality", s.slot);
    this.think("quality", true);
  }

  /** "review": the Quality score; the customer leaves with the rating they gave; the KPI wall updates. */
  private async review(s: Story, e: Record<string, any>) {
    const card = e.scorecard ?? {};
    const csat: number | null = e.kpis?.csat ?? null;
    const overall = Number(card.overall ?? 0);
    const quality = this.scene.walkers.quality;
    this.think("quality", false);
    this.patchWalker("quality", { pose: "raise" });
    this.say({
      owner: "quality",
      chat: s.chat,
      role: "quality",
      look: STAFF_LOOK.quality,
      placement: "left",
      x: quality.x,
      y: quality.y - PERSON_H,
      kind: "score",
      title: `Quality score of ${s.name}'s chat · Quality agent (${card.judge === "llm" ? "LLM judge" : "rule-based checklist"})`,
      score: { overall, scores: card.scores ?? {}, resolved: card.resolved, correct: card.correct },
      text: card.rationale ? shorten(card.rationale, 150) : undefined,
    });
    const stars = csat ? `${"★".repeat(csat)}${"☆".repeat(Math.max(0, 5 - csat))}` : "";
    const me = this.scene.walkers[s.chat];
    this.say({
      owner: s.chat,
      chat: s.chat,
      role: "customer",
      look: s.look,
      placement: s.place === 1 ? "right" : "left",
      x: me?.x ?? 0,
      y: (me?.y ?? 0) - PERSON_H,
      kind: "card",
      tone: csat == null ? "info" : csat >= 4 ? "good" : csat <= 2 ? "bad" : "info",
      title: `${s.name} rates the chat`,
      lines: [csat ? `${stars}  ${csat}/5` : "No rating given"],
    });
    this.caption(
      `Quality score ${overall.toFixed(1)}/5 · ${card.resolved ? "resolved" : "not resolved"}${e.kpis?.fcr ? " at the first contact" : ""} · ${s.name} gave ${csat ?? "–"}/5. The KPI wall counts this chat.`,
    );
    this.hooks.onReview();
    await this.hold(2600, {
      owner: "quality",
      text: `Quality score for ${s.name}: ${overall.toFixed(1)} out of 5. ${card.resolved ? "Resolved." : "Not resolved."}`,
      speaker: { role: "quality", id: "quality" },
    });
    // The customer walks out while the score card stays up a little longer.
    const leaving = this.exit(s).catch((error) => {
      if (!(error instanceof Stopped)) throw error;
    });
    await this.pause(3200);
    await leaving;
    this.patchWalker("quality", { pose: "stand" });
    this.unsay("quality", s.chat);
    this.releaseStaff("quality", s.chat);
  }

  /** "error": shown in red at the desk (or the reception), then the story goes on to "done". */
  private async problem(s: Story, message: string) {
    const at = s.slot !== null ? deskCentre(s.slot) : null;
    this.say({
      owner: at ? `desk-${s.slot}` : "reception",
      chat: s.chat,
      role: at ? "advisor" : "reception",
      look: at ? lookFor(s.advisor ?? "") : STAFF_LOOK.reception,
      placement: "above",
      x: at ? at.x : RECEPTION.x,
      y: at ? at.y - ADVISOR_HEAD : RECEPTION.y - 150,
      kind: "card",
      tone: "bad",
      title: `Something went wrong in ${s.name}'s chat`,
      lines: [shorten(message, 160)],
    });
    this.caption(`Error: ${shorten(message, 120)}`);
    await this.pause(3800);
  }

  /** The customer walks out through the door; the desk (or the waiting area) is free again. */
  private async exit(s: Story) {
    if (s.at === "gone") return;
    let path: Point[] = [LOBBY, DOOR];
    if (s.at === "desk" && s.slot !== null) {
      const front = deskFront(s.slot, s.place ?? 0);
      path = [{ x: AISLE_X, y: front.y }, { x: AISLE_X, y: RECEPTION_FRONT.y }, LOBBY, DOOR];
    }
    s.at = "gone";
    this.unsay(s.chat);
    this.think(s.chat, false);
    this.reception.leave(s.chat);
    this.relaxReception(s.chat);
    this.unseat(s.chat);
    const { [s.chat]: _tools, ...walkerTools } = this.scene.walkerTools;
    this.commit({ walkerTools });
    if (s.slot !== null) this.leaveDesk(s.slot, s.chat);
    await this.walk(s.chat, path);
    this.patchWalker(s.chat, { visible: false });
    await this.pause(450);
    const { [s.chat]: _gone, ...walkers } = this.scene.walkers;
    this.commit({ walkers });
  }

  /** "done": the end of the story (a finished chat, or a customer who closed the tab or hung up). */
  private async leave(s: Story, reviewed: boolean) {
    const left = s.at !== "gone"; // still on the floor: the chat stopped before the review
    if (left) await this.exit(s);
    if (this.turns.quality.isFirst(s.chat)) this.releaseStaff("quality", s.chat);
    if (this.turns.supervisor.isFirst(s.chat)) this.releaseStaff("supervisor", s.chat);
    this.think("reception", false);
    if (reviewed) this.caption(`${s.name} has left. The chat is saved in ${advisorName(s.advisor ?? "")}'s history: click the desk to see it.`);
    else this.caption(left && s.channel !== "centre" ? `${s.name} has left before the end of the chat.` : `${s.name} has left.`);
  }
}

const VOICES_KEY = "callverse-centre-voices";

/**
 * React side: opens /ws/centre (and opens it again if the connection drops), feeds the director, and returns
 * the scene to draw, the connection state, how many stories are playing, the speed (1x or 2x) and the voices
 * switch (remembered in this browser; off by default, because browsers only play sound after a click).
 */
export function useCentre(onReview: () => void) {
  const [scene, setScene] = useState<Scene>(emptyScene);
  const [connected, setConnected] = useState(false);
  const [stories, setStories] = useState({ centre: 0, all: 0 });
  const [speed, setSpeed] = useState(1);
  const [voicesOn, setVoicesOn] = useState(() => {
    try {
      return localStorage.getItem(VOICES_KEY) === "on";
    } catch {
      return false;
    }
  });
  const director = useRef<Director | null>(null);
  const cast = useRef<VoiceCast | null>(null);
  if (!cast.current) cast.current = new VoiceCast();
  const review = useRef(onReview);
  review.current = onReview;

  useEffect(() => {
    const voices = cast.current!;
    voices.enabled = voicesOn;
    if (!voicesOn) voices.stop();
    try {
      localStorage.setItem(VOICES_KEY, voicesOn ? "on" : "off");
    } catch {
      /* not remembered */
    }
  }, [voicesOn]);

  useEffect(() => {
    const instance = new Director(setScene, { onReview: () => review.current(), onStories: setStories }, cast.current!);
    director.current = instance;
    let socket: WebSocket | null = null;
    let retry: number | undefined;
    let closed = false;
    const connect = () => {
      socket = new WebSocket(wsUrl("/ws/centre"));
      socket.onopen = () => setConnected(true);
      socket.onmessage = (message) => {
        try {
          instance.receive(JSON.parse(message.data));
        } catch (error) {
          console.error("centre feed", error);
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (!closed) retry = window.setTimeout(connect, 2000);
      };
    };
    connect();
    return () => {
      closed = true;
      window.clearTimeout(retry);
      socket?.close();
      instance.stop();
    };
  }, []);

  useEffect(() => {
    if (director.current) director.current.speed = speed;
  }, [speed]);

  const voices = { on: voicesOn && cast.current.supported, set: setVoicesOn, supported: cast.current.supported };
  const announce = (text: string) => director.current?.announce(text);
  return { scene, connected, stories, speed, setSpeed, voices, announce };
}
