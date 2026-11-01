import clsx from "clsx";
import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Inbox, Loader2, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { AnimatedNumber } from "./motion";

export { clsx };

export function PageHeader({
  title,
  subtitle,
  tag,
  color = "var(--brand)",
  icon,
  children,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  tag?: string;
  color?: string;
  icon?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-3xl">
        {tag && (
          <motion.span
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            className="mb-3 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.12em]"
            style={{ color, borderColor: `color-mix(in srgb, ${color} 35%, transparent)`, background: `color-mix(in srgb, ${color} 10%, transparent)` }}
          >
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
            {tag}
          </motion.span>
        )}
        <h1 className="flex items-center gap-3 text-3xl font-semibold tracking-tight text-ink md:text-[2.15rem]">
          {icon}
          {title}
        </h1>
        {subtitle && <p className="mt-2 text-[15px] leading-relaxed text-ink2">{subtitle}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}

export function Card({
  title,
  subtitle,
  action,
  icon,
  children,
  className = "",
  bodyClassName = "",
  hover = false,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  hover?: boolean;
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.2, 0.7, 0.2, 1] }}
      className={clsx("card p-5 md:p-6", hover && "card-hover", className)}
    >
      {(title || action) && (
        <div className="mb-5 flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            {icon && (
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-raised text-brand">{icon}</div>
            )}
            <div>
              {title && <h2 className="text-[15px] font-semibold text-ink">{title}</h2>}
              {subtitle && <p className="mt-0.5 text-xs leading-relaxed text-muted">{subtitle}</p>}
            </div>
          </div>
          {action}
        </div>
      )}
      <div className={bodyClassName}>{children}</div>
    </motion.section>
  );
}

/** Stat tile: one headline number, an optional comparison line. Numbers count up. */
export function Stat({
  label,
  value,
  numeric,
  format,
  hint,
  tone,
  icon,
  accent = "var(--brand)",
}: {
  label: ReactNode;
  value?: ReactNode;
  numeric?: number | null;
  format?: (v: number) => string;
  hint?: ReactNode;
  tone?: "good" | "bad" | "neutral";
  icon?: ReactNode;
  accent?: string;
}) {
  const toneColor =
    tone === "good" ? "var(--good-text)" : tone === "bad" ? "var(--critical)" : "var(--text-muted)";
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="card card-hover group overflow-hidden p-5"
    >
      <div
        className="pointer-events-none absolute -right-10 -top-10 h-28 w-28 rounded-full opacity-[0.12] blur-2xl transition-opacity group-hover:opacity-25"
        style={{ background: accent }}
      />
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">{label}</div>
        {icon && <div style={{ color: accent }}>{icon}</div>}
      </div>
      <div className="mt-2 font-display text-[1.75rem] font-semibold leading-tight text-ink">
        {numeric !== undefined ? <AnimatedNumber value={numeric} format={format} /> : value}
      </div>
      {hint && (
        <div className="mt-1.5 text-xs leading-snug" style={{ color: toneColor }}>
          {hint}
        </div>
      )}
    </motion.div>
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
      <Loader2 className="animate-spin text-brand" size={16} /> {text}…
    </div>
  );
}

/** Placeholder blocks while data loads. */
export function Skeleton({ className = "h-4 w-full" }: { className?: string }) {
  return <div className={clsx("skeleton", className)} />;
}

export function PageSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-2/5" />
      <Skeleton className="h-5 w-3/5" />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
      <Skeleton className="h-72" />
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

export function EmptyState({ title, text, icon }: { title: string; text?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-line px-6 py-12 text-center">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-raised text-muted">
        {icon ?? <Inbox size={20} />}
      </div>
      <div className="font-medium text-ink">{title}</div>
      {text && <div className="mt-1 max-w-sm text-sm text-muted">{text}</div>}
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

export function Pill({ children, color }: { children: ReactNode; color?: string }) {
  return (
    <span
      className="chip"
      style={color ? { color, borderColor: `color-mix(in srgb, ${color} 30%, transparent)`, background: `color-mix(in srgb, ${color} 9%, transparent)` } : undefined}
    >
      {children}
    </span>
  );
}

/** Segmented control (tabs-like toggle) with an animated selection. */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  id,
  size = "md",
}: {
  value: T;
  options: { value: T; label: ReactNode; disabled?: boolean }[];
  onChange: (value: T) => void;
  id: string;
  size?: "sm" | "md";
}) {
  return (
    <div className="inline-flex rounded-xl border border-line bg-raised p-1">
      {options.map((option) => (
        <button
          key={option.value}
          disabled={option.disabled}
          onClick={() => onChange(option.value)}
          className={clsx(
            "relative rounded-lg font-medium transition-colors disabled:opacity-40",
            size === "sm" ? "px-2.5 py-1 text-xs" : "px-3.5 py-1.5 text-sm",
            value === option.value ? "text-ink" : "text-muted hover:text-ink2",
          )}
        >
          {value === option.value && (
            <motion.span
              layoutId={`seg-${id}`}
              className="absolute inset-0 rounded-lg bg-surface shadow-soft"
              transition={{ type: "spring", bounce: 0.2, duration: 0.5 }}
            />
          )}
          <span className="relative z-10 inline-flex items-center gap-1.5">{option.label}</span>
        </button>
      ))}
    </div>
  );
}

/** Customer avatar: initials on a gradient picked from the name. */
export function Avatar({ name, size = 40 }: { name: string; size?: number }) {
  const initials = name
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  const hue = [...name].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);
  return (
    <div
      className="flex shrink-0 items-center justify-center rounded-full font-semibold text-white shadow-soft"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.36,
        background: `linear-gradient(135deg, hsl(${hue} 75% 58%), hsl(${(hue + 50) % 360} 80% 48%))`,
      }}
    >
      {initials}
    </div>
  );
}

/** Chart tooltip in the page's own styling (values in ink, a swatch for identity). */
export function ChartTooltip({ active, payload, label, format }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="glass rounded-xl px-3 py-2 text-xs shadow-lift">
      <div className="mb-1 font-medium text-ink">{label}</div>
      {payload.map((entry: any) => (
        <div key={entry.dataKey} className="flex items-center gap-2 text-ink2">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: entry.color }} />
          <span>{entry.name}</span>
          <span className="ml-auto pl-3 tabular font-medium text-ink">
            {format ? format(entry.value, entry.dataKey) : entry.value}
          </span>
        </div>
      ))}
    </div>
  );
}
