/**
 * CallVerse Centre (back office, /centre): the whole contact centre on one screen, without the sidebar, so it
 * looks like its own app on a projector ("Full screen", or the F key, hides the browser too).
 *
 * Press "A customer walks in" and choose who: a random customer from the history, an existing customer (the
 * portal's demo customers and the new customers created before), or a new customer (a problem, a first
 * message, and a real Olist order or a new one). The Client agent plays that customer, and the page shows the
 * real chat as people in an office. Every other chat of the server walks in too: people writing on the
 * customer portal, phone calls, the advisor desk and the Agent theater.
 *
 * The customer comes in, explains the problem at the reception (the Workforce agent routes it), walks to the
 * chosen advisor's desk (the Advisor agent answers; its tools pop up while it works, then show inside its
 * answer), the supervisor comes if the chat is escalated, the quality lead shows the Quality agent's score,
 * and the KPI wall counts the chat. Every move comes from an event of the server (components/centre/
 * director.ts). Click a desk to see that advisor's past chats and how the Quality agent scored each one.
 *
 * Voice: "Voices on" reads every bubble aloud, each person with their own voice (components/centre/voices.ts);
 * "Talk as a customer" lets a visitor speak into the microphone as a real customer (VisitorPanel.tsx).
 */
import { LogoMark, Segmented, ThemeToggle, postJson, useApi, useTheme } from "@callverse/shared";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, Cpu, DoorOpen, Maximize2, Mic, Minimize2, Volume2, VolumeX } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Toaster, toast } from "sonner";
import { AdvisorHistory } from "../components/centre/AdvisorHistory";
import { useCentre } from "../components/centre/director";
import {
  BubbleView,
  type DeskStats,
  DeskUnit,
  KpiWall,
  Manager,
  ReceptionUnit,
  Room,
  STAGE_H,
  STAGE_W,
  WalkerView,
} from "../components/centre/floor";
import { CentreStyles, Portrait, ROLE, STAFF_LOOK, lookFor, type Look, type Role } from "../components/centre/people";
import { VisitorPanel } from "../components/centre/VisitorPanel";
import { WalkInDialog } from "../components/centre/WalkInDialog";

type Engine = "auto" | "template";

/** LLMs or offline backups, remembered in this browser (rehearse offline, present with the LLMs). */
function useEngine() {
  const [engine, setEngine] = useState<Engine>(() => {
    try {
      return localStorage.getItem("callverse-centre-engine") === "template" ? "template" : "auto";
    } catch {
      return "auto";
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem("callverse-centre-engine", engine);
    } catch {
      /* not remembered */
    }
  }, [engine]);
  return [engine, setEngine] as const;
}

/** Full screen (the browser's own mode: no tabs, no address bar), switched by the button or the F key. */
function useFullScreen() {
  const [full, setFull] = useState(() => typeof document !== "undefined" && !!document.fullscreenElement);
  useEffect(() => {
    const update = () => setFull(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", update);
    return () => document.removeEventListener("fullscreenchange", update);
  }, []);
  const toggle = useCallback(() => {
    const change = document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
    change.catch(() => toast.error("This browser did not allow full screen here."));
  }, []);
  // The F key, except while typing (a name, a message...).
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = target && (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable);
      if (!typing && !event.ctrlKey && !event.metaKey && !event.altKey && event.key.toLowerCase() === "f") toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);
  return { full, toggle, supported: typeof document !== "undefined" && !!document.fullscreenEnabled };
}

/** The 1600 x 900 stage, scaled to fill the space it has (keeping its shape) and centred. */
function Stage({ children }: { children: ReactNode }) {
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  useLayoutEffect(() => {
    const element = box.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setSize({ w: entry.contentRect.width, h: entry.contentRect.height }));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const scale = size.w && size.h ? Math.min(size.w / STAGE_W, size.h / STAGE_H) : 0;
  return (
    <div ref={box} className="relative min-h-0 flex-1 overflow-hidden">
      <div
        className="absolute overflow-hidden rounded-[28px] border border-line shadow-lift"
        style={{
          width: STAGE_W,
          height: STAGE_H,
          left: (size.w - STAGE_W * scale) / 2,
          top: (size.h - STAGE_H * scale) / 2,
          transform: `scale(${scale})`,
          transformOrigin: "0 0",
          visibility: scale ? "visible" : "hidden",
        }}
      >
        {children}
      </div>
    </div>
  );
}

// The six roles and the real agent behind each one (shown under the floor).
const LEGEND: { role: Role; look: Look }[] = [
  { role: "customer", look: lookFor("legend-customer") },
  { role: "reception", look: STAFF_LOOK.reception },
  { role: "advisor", look: lookFor("advisor-02") },
  { role: "supervisor", look: STAFF_LOOK.supervisor },
  { role: "quality", look: STAFF_LOOK.quality },
  { role: "manager", look: STAFF_LOOK.manager },
];

export default function CentrePage() {
  // Same theme as the rest of the back office (dark by default).
  const { dark, toggle, theme } = useTheme("dark", "callverse-theme-back");
  const status = useApi<any>("/api/agents/status");
  // The KPI wall and the desks' scores, read again after every Quality review.
  const [tick, setTick] = useState(0);
  const wall = useApi<any>(`/api/centre/advisors?t=${tick}`);
  const refresh = useCallback(() => setTick((t) => t + 1), []);
  const { scene, connected, stories, speed, setSpeed, voices } = useCentre(refresh);
  const [engine, setEngine] = useEngine();
  const screen = useFullScreen();
  const [sending, setSending] = useState(false);
  const [choosing, setChoosing] = useState(false);
  const [history, setHistory] = useState<string | null>(null);
  const [visitor, setVisitor] = useState(false);
  // A visitor hears the advisor's answers: talking switches the voices on.
  const talk = () => {
    voices.set(true);
    setVisitor(true);
  };
  const closeHistory = useCallback(() => setHistory(null), []);

  useEffect(() => {
    const before = document.title;
    document.title = "CallVerse Centre";
    return () => {
      document.title = before;
    };
  }, []);
  // After a customer was sent in, keep the button busy until its story starts on the floor.
  useEffect(() => {
    if (stories.centre > 0) setSending(false);
  }, [stories.centre]);

  const llm = status.data?.llm_available;
  const mode: Engine = llm === false ? "template" : engine;
  const busy = sending || stories.centre > 0;
  const stats: Record<string, DeskStats> = Object.fromEntries((wall.data?.advisors ?? []).map((a: any) => [a.id, { chats: a.chats, quality: a.quality }]));

  // The chosen customer walks in (null: a random one from the history); the server runs the chat and streams
  // it on /ws/centre. Returns false when the server refused, so the chooser stays open.
  const walkIn = async (contactId: string | null): Promise<boolean> => {
    setSending(true);
    try {
      await postJson("/api/centre/arrivals", { contact_id: contactId, mode, seed: Math.floor(Math.random() * 1000) });
      window.setTimeout(() => setSending(false), 15000); // in case the story never starts
      return true;
    } catch (error) {
      setSending(false);
      const text = String((error as Error)?.message ?? error);
      if (text.startsWith("409")) toast.info("A customer is already being served: wait until the story ends.");
      else toast.error(`The customer could not come in: ${text}`);
      return false;
    }
  };

  return (
    <div className="flex h-screen flex-col bg-page text-ink">
      <CentreStyles />
      <Toaster position="bottom-right" theme={theme} richColors closeButton />
      {/* Top bar: back to the control room, the name, the live state, and the controls. */}
      <header className="flex flex-wrap items-center gap-3 border-b border-line bg-surface px-4 py-2.5">
        <Link to="/" className="btn btn-ghost btn-icon" title="Back to the control room" aria-label="Back to the control room">
          <ArrowLeft size={18} />
        </Link>
        <LogoMark size={34} />
        <div className="leading-tight">
          <div className="font-display text-lg font-bold text-ink">
            CallVerse <span className="gradient-text">Centre</span>
          </div>
          <div className="text-[11px] text-muted">Every move on the floor is a real event of the agents</div>
        </div>
        <span className="ml-2 inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-xs text-ink2" title="Connection to the server's live feed (/ws/centre)">
          {connected ? <span className="live-dot" /> : <span className="h-2 w-2 rounded-full bg-[var(--warning)]" />}
          {connected ? "Live" : "Connecting…"}
        </span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Segmented
            id="centre-engine"
            size="sm"
            value={mode}
            onChange={setEngine}
            options={[
              { value: "auto", label: <><Cpu size={12} /> LLMs</>, disabled: llm === false },
              { value: "template", label: "Offline backups" },
            ]}
          />
          <Segmented
            id="centre-speed"
            size="sm"
            value={String(speed)}
            onChange={(value) => setSpeed(Number(value))}
            options={[
              { value: "1", label: "1×" },
              { value: "2", label: "2×" },
            ]}
          />
          <button
            className="btn btn-ghost"
            onClick={() => voices.set(!voices.on)}
            disabled={!voices.supported}
            aria-pressed={voices.on}
            title={voices.supported ? "Read every bubble aloud, each person with their own voice" : "This browser cannot speak (no speech engine)"}
          >
            {voices.on ? <Volume2 size={16} /> : <VolumeX size={16} />} {voices.on ? "Voices on" : "Voices off"}
          </button>
          <button className="btn btn-soft" onClick={talk} disabled={visitor || !connected} title="Speak into the microphone as a real customer">
            <Mic size={16} /> Talk as a customer
          </button>
          <button className="btn btn-primary" onClick={() => setChoosing(true)} disabled={busy || !connected}>
            <DoorOpen size={16} /> {busy ? "A customer is being served…" : "A customer walks in"}
          </button>
          {screen.supported && (
            <button
              className="btn btn-ghost btn-icon"
              onClick={screen.toggle}
              aria-pressed={screen.full}
              title={screen.full ? "Leave full screen (F)" : "Full screen (F)"}
              aria-label={screen.full ? "Leave full screen" : "Full screen"}
            >
              {screen.full ? <Minimize2 size={17} /> : <Maximize2 size={17} />}
            </button>
          )}
          <ThemeToggle dark={dark} toggle={toggle} />
        </div>
      </header>

      {/* The floor. */}
      <div className="flex min-h-0 flex-1 flex-col p-3">
        <Stage>
          <Room />
          <KpiWall totals={wall.data?.totals ?? null} />
          <Manager />
          <ReceptionUnit pose={scene.receptionPose} thinking={!!scene.thinking.reception} />
          {scene.slots.map((advisorId, slot) => (
            <DeskUnit
              key={slot}
              slot={slot}
              advisorId={advisorId}
              stats={stats[advisorId] ?? null}
              busy={(scene.serving[slot] ?? []).length > 0}
              thinking={!!scene.thinking[`desk-${slot}`]}
              tools={scene.deskTools[slot] ?? []}
              onOpen={setHistory}
            />
          ))}
          {Object.values(scene.walkers).map((walker) => (
            <WalkerView key={walker.id} walker={walker} tools={scene.walkerTools[walker.id] ?? []} thinking={!!scene.thinking[walker.id]} />
          ))}
          <AnimatePresence>
            {Object.values(scene.bubbles).map((bubble) => (
              <BubbleView key={bubble.key} bubble={bubble} />
            ))}
          </AnimatePresence>
        </Stage>
      </div>

      {/* What is happening (the newest sentence, with the two before it in grey: several customers can be on
         the floor at once), and who is who. */}
      <footer className="space-y-2 border-t border-line bg-surface px-5 py-3">
        <div className="flex flex-col items-center gap-0.5">
          {[...scene.earlier].reverse().map((line) => (
            <p key={line.key} className="text-center text-[13px] leading-snug text-muted">
              {line.text}
            </p>
          ))}
        </div>
        <div className="flex min-h-[28px] items-center justify-center" role="status" aria-live="polite">
          <AnimatePresence mode="wait">
            <motion.p
              key={scene.caption.key}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.2 }}
              className="text-center text-[17px] leading-snug text-ink"
            >
              {scene.caption.text}
            </motion.p>
          </AnimatePresence>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-xs text-ink2">
          {LEGEND.map(({ role, look }) => (
            <span key={role} className="inline-flex items-center gap-1.5">
              <Portrait role={role} look={look} size={22} /> <b className="text-ink">{ROLE[role].title}</b> {ROLE[role].agent}
            </span>
          ))}
        </div>
      </footer>

      <AdvisorHistory advisorId={history} desk={history ? scene.slots.indexOf(history) : null} onClose={closeHistory} />
      <AnimatePresence>{visitor && <VisitorPanel mode={mode} onClose={() => setVisitor(false)} />}</AnimatePresence>
      <WalkInDialog open={choosing} onClose={() => setChoosing(false)} onWalkIn={walkIn} />
    </div>
  );
}
