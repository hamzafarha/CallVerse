/**
 * CallVerse Centre (back office, /centre): the whole contact centre on one screen, without the sidebar, so it
 * looks like its own app on a projector.
 *
 * Press "A customer walks in": the Client agent plays a real historical customer, and the page shows the real
 * chat as people in an office. Every other chat of the server walks in too: people writing on the customer
 * portal, phone calls, the advisor desk and the Agent theater. The customer comes in, explains the problem at the reception (the Workforce
 * agent routes it), walks to the chosen advisor's desk (the Advisor agent answers, its tools pop up), the
 * supervisor comes if the chat is escalated, the quality lead shows the Quality agent's score, and the KPI wall
 * counts the chat. Every move comes from an event of the server (components/centre/director.ts). Click a desk
 * to see that advisor's past chats and how the Quality agent scored each one.
 *
 * Voice: "Voices on" reads every bubble aloud, each person with their own voice (components/centre/voices.ts);
 * "Talk as a customer" lets a visitor speak into the microphone as a real customer (VisitorPanel.tsx).
 *
 * Crowd: the digital twin's simulated customers of a real day walk in, queue, are served or give up
 * (components/centre/crowd.tsx), beside the real chats.
 */
import { LogoMark, Segmented, ThemeToggle, postJson, useApi, useTheme } from "@callverse/shared";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, Cpu, DoorOpen, Mic, Volume2, VolumeX } from "lucide-react";
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
import { CROWD_PRESETS, CrowdLegend, CrowdLayer, TwinBoard, useCrowd } from "../components/centre/crowd";
import { hhmm } from "../components/LiveFloor";
import { dayLabel } from "../components/SimpleTwin";

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
  const { scene, connected, stories, speed, setSpeed, voices, announce } = useCentre(refresh);
  const [engine, setEngine] = useEngine();
  const [sending, setSending] = useState(false);
  const [history, setHistory] = useState<string | null>(null);
  const [visitor, setVisitor] = useState(false);
  // The twin crowd: simulated customers of a real day, replayed beside the real chats (components/centre/crowd).
  const [crowdId, setCrowdId] = useState("off");
  const preset = CROWD_PRESETS.find((p) => p.id === crowdId) ?? null;
  const crowd = useCrowd(preset, speed);
  useEffect(() => {
    if (preset && crowd.span && crowd.floor)
      announce(`Twin crowd: simulated customers of ${dayLabel(crowd.floor.date)} from ${hhmm(crowd.span.from)} (no AI). Real chats keep walking in on top.`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [crowd.span]);
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

  // A random customer from the history walks in; the server runs the chat and streams it on /ws/centre.
  const send = async () => {
    setSending(true);
    try {
      await postJson("/api/centre/arrivals", { mode, seed: Math.floor(Math.random() * 1000) });
      window.setTimeout(() => setSending(false), 15000); // in case the story never starts
    } catch (error) {
      setSending(false);
      const text = String((error as Error)?.message ?? error);
      if (text.startsWith("409")) toast.info("A customer is already being served: wait until the story ends.");
      else toast.error(`The customer could not come in: ${text}`);
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
          <label className="flex items-center gap-1.5 text-xs text-muted" title="Simulated customers of a real day, from the digital twin (no AI)">
            Crowd
            <select className="field h-9 w-auto py-0 pr-8 text-sm" value={crowdId} onChange={(event) => setCrowdId(event.target.value)} aria-label="Twin crowd">
              <option value="off">Off</option>
              {CROWD_PRESETS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
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
          <button className="btn btn-primary" onClick={send} disabled={busy || !connected}>
            <DoorOpen size={16} /> {busy ? "A customer is being served…" : "A customer walks in"}
          </button>
          <ThemeToggle dark={dark} toggle={toggle} />
        </div>
      </header>

      {/* The floor. */}
      <div className="flex min-h-0 flex-1 flex-col p-3">
        <Stage>
          <Room />
          <KpiWall totals={wall.data?.totals ?? null} />
          {preset && <TwinBoard crowd={crowd} preset={preset} />}
          {preset && crowd.view && <CrowdLayer view={crowd.view} />}
          <Manager />
          <ReceptionUnit pose={scene.receptionPose} thinking={!!scene.thinking.reception} />
          {scene.slots.map((advisorId, slot) => (
            <DeskUnit
              key={slot}
              slot={slot}
              advisorId={advisorId}
              stats={stats[advisorId] ?? null}
              busy={(scene.serving[slot] ?? []).length > 0 || (!!preset && !!crowd.view?.busy.has(slot))}
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
        {preset && (
          <div className="flex justify-center text-xs text-ink2">
            <CrowdLegend />
          </div>
        )}
      </footer>

      <AdvisorHistory advisorId={history} desk={history ? scene.slots.indexOf(history) : null} onClose={closeHistory} />
      <AnimatePresence>{visitor && <VisitorPanel mode={mode} onClose={() => setVisitor(false)} />}</AnimatePresence>
    </div>
  );
}
