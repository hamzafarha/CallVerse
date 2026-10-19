import { AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react";
import type { ReactNode } from "react";

export function PageHeader({
  title,
  subtitle,
  tag,
  color = "var(--brand)",
  children,
}: {
  title: string;
  subtitle?: string;
  tag?: string;
  color?: string;
  children?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        {tag && (
          <span
            className="mb-2 inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold text-white"
            style={{ background: color }}
          >
            {tag}
          </span>
        )}
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-ink2">{subtitle}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}

export function Card({
  title,
  subtitle,
  action,
  children,
  className = "",
}: {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card p-5 ${className}`}>
      {(title || action) && (
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

/** Stat tile: one headline number, an optional comparison line. */
export function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "good" | "bad" | "neutral";
}) {
  const toneColor =
    tone === "good" ? "var(--good-text)" : tone === "bad" ? "var(--critical)" : "var(--text-secondary)";
  return (
    <div className="card p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-ink">{value}</div>
      {hint && (
        <div className="mt-1 text-xs" style={{ color: toneColor }}>
          {hint}
        </div>
      )}
    </div>
  );
}

/** Status badge: icon + label, never color alone. */
export function Status({ ok, label }: { ok: boolean | null | undefined; label?: string }) {
  if (ok === null || ok === undefined)
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted">
        <AlertTriangle size={14} style={{ color: "var(--warning)" }} /> {label ?? "not run"}
      </span>
    );
  return ok ? (
    <span className="inline-flex items-center gap-1 text-xs font-medium" style={{ color: "var(--good-text)" }}>
      <CheckCircle2 size={14} style={{ color: "var(--good)" }} /> {label ?? "pass"}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-xs font-medium" style={{ color: "var(--critical)" }}>
      <XCircle size={14} /> {label ?? "check"}
    </span>
  );
}

export function Loading({ text = "Loading" }: { text?: string }) {
  return (
    <div className="flex items-center gap-2 p-6 text-sm text-muted">
      <Loader2 className="animate-spin" size={16} /> {text}…
    </div>
  );
}

export function ErrorBox({ error }: { error: string }) {
  return (
    <div className="card border-l-4 p-4 text-sm" style={{ borderLeftColor: "var(--critical)" }}>
      <div className="font-medium text-ink">The API returned an error</div>
      <div className="mt-1 break-all text-ink2">{error}</div>
      <div className="mt-2 text-xs text-muted">
        Is the backend running? <code>callverse serve</code> (see docs/RUN_GUIDE.md).
      </div>
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink2">
      {items.map((item) => (
        <span key={item.label} className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-0.5 w-4"
            style={{
              background: item.dashed ? "transparent" : item.color,
              borderTop: item.dashed ? `2px dashed ${item.color}` : undefined,
            }}
          />
          {item.label}
        </span>
      ))}
    </div>
  );
}

export function Pill({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full border border-line px-2 py-0.5 text-xs text-ink2">
      {children}
    </span>
  );
}

/** Chart tooltip in the page's own styling (values in ink, a swatch for identity). */
export function ChartTooltip({ active, payload, label, format }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="card px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 font-medium text-ink">{label}</div>
      {payload.map((entry: any) => (
        <div key={entry.dataKey} className="flex items-center gap-2 text-ink2">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: entry.color }} />
          <span>{entry.name}</span>
          <span className="ml-auto tabular font-medium text-ink">
            {format ? format(entry.value, entry.dataKey) : entry.value}
          </span>
        </div>
      ))}
    </div>
  );
}
