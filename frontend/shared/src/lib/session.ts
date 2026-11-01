import { useCallback, useEffect, useRef, useState } from "react";
import { wsUrl } from "./api";

/** Client of `/ws/session`: one live conversation where a human plays one side.
 *
 * The backend streams every step of the agents: `ready`, `message`, `token`
 * (advisor text as it is generated), `stage` (routing, retrieval, tool calls,
 * generation, quality review), `routing`, `suggestion` (copilot draft),
 * `review` and `done`. */

export type Speaker = "customer" | "advisor";
export type AgentName = "client" | "workforce" | "advisor" | "quality";

export interface ChatMessage {
  speaker: Speaker;
  text: string;
  meta?: Record<string, any>;
}

export interface StageEvent {
  agent: AgentName;
  step: string;
  kind?: string;
  at: number;
  [key: string]: any;
}

export interface LiveState {
  status: "idle" | "connecting" | "running" | "done" | "error";
  ready: { profile: any; llm: boolean; model?: string | null; retriever?: string } | null;
  messages: ChatMessage[];
  streaming: { kind: string; text: string } | null;
  stages: StageEvent[];
  activeAgent: AgentName | null;
  visited: AgentName[];
  routing: any | null;
  suggestion: ChatMessage | null;
  advisor: any | null;
  review: { scorecard: any; reference: any; kpis: any } | null;
  error: string | null;
  startedAt: number | null;
}

export interface StartOptions {
  contact_id?: string | null;
  customer: "human" | "agent";
  advisor: "human" | "agent";
  mode?: "auto" | "llm" | "template";
  variant?: "rag_policy" | "rag";
  seed?: number;
}

const INITIAL: LiveState = {
  status: "idle",
  ready: null,
  messages: [],
  streaming: null,
  stages: [],
  activeAgent: null,
  visited: [],
  routing: null,
  suggestion: null,
  advisor: null,
  review: null,
  error: null,
  startedAt: null,
};

function reduce(state: LiveState, event: any): LiveState {
  const now = Date.now();
  switch (event.type) {
    case "ready":
      return { ...state, status: "running", ready: event };
    case "message": {
      const message = event.message as ChatMessage;
      return {
        ...state,
        messages: [...state.messages, message],
        streaming: message.speaker === "advisor" ? null : state.streaming,
        activeAgent: null,
        suggestion: message.speaker === "customer" ? null : state.suggestion,
      };
    }
    case "token": {
      const current = state.streaming ?? { kind: event.kind, text: "" };
      return { ...state, streaming: { kind: event.kind, text: current.text + event.text } };
    }
    case "stage": {
      const stage: StageEvent = { ...event, at: now };
      const agent = stage.agent;
      let streaming = state.streaming;
      if (agent === "advisor" && stage.step === "start") streaming = { kind: stage.kind ?? "reply", text: "" };
      if (agent === "advisor" && stage.step === "generation" && stage.round > 0)
        streaming = { kind: stage.kind ?? "reply", text: "" }; // new LLM round after tool results
      return {
        ...state,
        stages: [...state.stages, stage],
        activeAgent: agent,
        visited: state.visited.includes(agent) ? state.visited : [...state.visited, agent],
        streaming,
      };
    }
    case "routing":
      return { ...state, routing: event.routing };
    case "suggestion":
      return { ...state, suggestion: event.message, advisor: event.advisor, streaming: null, activeAgent: null };
    case "advisor_state":
      return { ...state, advisor: event.advisor };
    case "review":
      return { ...state, review: event, activeAgent: null };
    case "done":
      return { ...state, status: "done", activeAgent: null, streaming: null };
    case "error":
      return { ...state, error: event.message, activeAgent: null, streaming: null };
    default:
      return state;
  }
}

export function useLiveSession() {
  const [state, setState] = useState<LiveState>(INITIAL);
  const socket = useRef<WebSocket | null>(null);

  const close = useCallback(() => {
    socket.current?.close();
    socket.current = null;
  }, []);
  useEffect(() => close, [close]);

  const start = useCallback(
    (options: StartOptions) => {
      close();
      setState({ ...INITIAL, status: "connecting", startedAt: Date.now() });
      const ws = new WebSocket(wsUrl("/ws/session"));
      socket.current = ws;
      ws.onopen = () => ws.send(JSON.stringify({ type: "start", mode: "auto", seed: 0, ...options }));
      ws.onmessage = (message) => setState((s) => reduce(s, JSON.parse(message.data)));
      ws.onerror = () =>
        setState((s) => ({ ...s, status: "error", error: "Connection lost: is `callverse serve` running?" }));
      ws.onclose = () =>
        setState((s) => (s.status === "done" || s.status === "error" ? s : { ...s, status: "done" }));
    },
    [close],
  );

  const send = useCallback((payload: Record<string, unknown>) => {
    if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify(payload));
  }, []);

  const busy = state.status === "connecting" || state.activeAgent !== null;
  return {
    state,
    busy,
    start,
    reset: () => {
      close();
      setState(INITIAL);
    },
    sendCustomer: (text: string) => send({ type: "customer_message", text }),
    sendAdvisor: (text: string) => send({ type: "advisor_message", text }),
    suggest: () => send({ type: "suggest" }),
    autopilot: (on: boolean) => send({ type: "autopilot", on }),
    end: (csat?: number) => send({ type: "end", csat }),
  };
}
