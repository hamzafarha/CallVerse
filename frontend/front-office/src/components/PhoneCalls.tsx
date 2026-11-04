/**
 * The advisor desk's "Phone calls" panel: calls from customers' phones (page /phone), live.
 *
 * The list is read every 2 seconds from GET /api/phone/calls (orchestration/calls.py). "Watch" attaches the
 * desk to the call (it first receives everything said so far); the AI advisor keeps answering until you
 * choose "You answer". "Phone link" shows the address to open on a phone on the same Wi-Fi.
 */
import { Status, clock, clsx, getJson, humanize, motion, useApi } from "@callverse/shared";
import { Bot, Eye, Smartphone, User } from "lucide-react";
import { useEffect, useState } from "react";

const STATUS: Record<string, { label: string; color: string }> = {
  ringing: { label: "ringing", color: "var(--warning)" },
  talking: { label: "on the line", color: "var(--good)" },
  ended: { label: "ended", color: "var(--text-muted)" },
};

export function PhoneCalls({ activeId, onWatch }: { activeId?: string; onWatch: (call: any) => void }) {
  const [calls, setCalls] = useState<any[]>([]);
  const [help, setHelp] = useState(false);
  const info = useApi<any>(help ? "/api/phone/info" : null);
  // Read the list every 2 seconds (a new call appears within 2 s).
  useEffect(() => {
    let alive = true;
    const load = () =>
      getJson("/api/phone/calls")
        .then((list) => alive && setCalls(list))
        .catch(() => undefined);
    load();
    const timer = window.setInterval(load, 2000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);
  const live = calls.filter((c) => c.status !== "ended").length;

  return (
    <div className="max-h-[48%] shrink-0 overflow-y-auto border-b border-line px-3 pb-3">
      <div className="flex items-center justify-between px-1 py-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-ink">
          <Smartphone size={15} className="text-brand" /> Phone calls
          {live > 0 && <span className="live-dot" />}
        </div>
        <button className="text-[11px] font-medium text-brand hover:underline" onClick={() => setHelp(!help)}>
          {help ? "hide" : "phone link"}
        </button>
      </div>
      {/* Where a phone connects, and the two setup commands */}
      {help && (
        <div className="mb-2 space-y-1.5 rounded-xl bg-raised p-3 text-[11px] leading-relaxed text-ink2">
          <div>On a phone on the same Wi-Fi, open:</div>
          {(info.data?.links ?? []).map((link: string) => (
            <div key={link} className="break-all font-mono text-[12px] font-semibold text-ink">
              {link}
            </div>
          ))}
          {info.data && !info.data.certificate && (
            <div className="text-bad">No HTTPS certificate yet: run `callverse phone-cert`, then `npm run dev:phone`.</div>
          )}
          {info.data?.certificate && <div className="text-muted">The site must run with `npm run dev:phone` (https).</div>}
        </div>
      )}
      {calls.length === 0 ? (
        <div className="px-1 text-[11px] leading-relaxed text-muted">No call yet. When a customer presses Call on /phone, it appears here.</div>
      ) : (
        <div className="space-y-2">
          {calls.map((call) => {
            const status = STATUS[call.status] ?? STATUS.talking;
            const active = call.id === activeId;
            return (
              <motion.div
                key={call.id}
                layout
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                className={clsx("card p-3", active && "ring-gradient")}
              >
                <div className="flex items-center gap-2">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-white" style={{ background: status.color }}>
                    <Smartphone size={14} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px] font-semibold text-ink">{call.name}</div>
                    <div className="truncate text-[11px] text-muted">
                      {call.desk ? `${call.desk} · ${humanize(call.predicted_intent)}` : humanize(call.intent)}
                    </div>
                  </div>
                  <span className="font-mono text-[11px] tabular text-muted">{clock(call.seconds)}</span>
                </div>
                {call.last_message && <p className="mt-2 line-clamp-2 text-xs text-ink2">{call.last_message}</p>}
                <div className="mt-2 flex items-center gap-2 text-[10px]">
                  <span className={clsx("rounded-full px-1.5 py-0.5 font-semibold", call.status === "ringing" && "animate-pulse")} style={{ color: status.color, background: `color-mix(in srgb, ${status.color} 14%, transparent)` }}>
                    {status.label}
                  </span>
                  {call.status !== "ended" && (
                    <span className="inline-flex items-center gap-1 text-muted">
                      {call.autopilot ? <Bot size={11} /> : <User size={11} />} {call.autopilot ? "AI answering" : "human advisor"}
                    </span>
                  )}
                  {call.status === "ended" && call.quality != null && <Status ok={call.quality >= 3} label={`quality ${Number(call.quality).toFixed(1)}/5`} />}
                  <button className={clsx("btn ml-auto px-2 py-1 text-[11px]", active ? "btn-ghost" : "btn-primary")} disabled={active} onClick={() => onWatch(call)}>
                    <Eye size={12} /> {active ? "Watching" : call.status === "ended" ? "Open" : "Watch"}
                  </button>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
