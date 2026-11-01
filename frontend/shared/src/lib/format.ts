/** Number formatting and the fixed color assignment of every entity. */

export const GROUPS = ["wismo", "cancel_refund", "post_delivery", "order_admin"] as const;

export const GROUP_LABEL: Record<string, string> = {
  wismo: "Where is my order",
  cancel_refund: "Cancel / refund",
  post_delivery: "After delivery",
  order_admin: "Order admin",
};

// Color follows the entity, never its rank: fixed slots, never cycled.
export const GROUP_COLOR: Record<string, string> = {
  wismo: "var(--series-1)",
  cancel_refund: "var(--series-2)",
  post_delivery: "var(--series-3)",
  order_admin: "var(--series-4)",
};

export const ROUTER_COLOR: Record<string, string> = {
  fifo: "var(--series-1)",
  skill_score: "var(--series-2)",
  ppo: "var(--series-3)",
};

export const ROUTER_LABEL: Record<string, string> = {
  fifo: "FIFO (baseline)",
  skill_score: "Skill score (backup)",
  ppo: "MaskablePPO (main)",
};

export const PLAN_LABEL: Record<string, string> = {
  cpsat: "CP-SAT (main)",
  rules_erlang: "Erlang C + rules (backup)",
  fixed: "Fixed, peak-sized (baseline)",
  fixed_tuned: "Fixed, tuned (sensitivity)",
  erlang_hourly: "Erlang C hourly (reference)",
};

export const MODEL_COLOR: Record<string, string> = {
  actual: "var(--text-primary)",
  lightgbm: "var(--series-1)",
  seasonal_naive: "var(--series-2)",
  weekday_mean_4w: "var(--series-3)",
  sarima: "var(--series-4)",
  prophet: "var(--series-5)",
};

export function num(value: unknown, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "–";
  return Number(value).toLocaleString("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  });
}

export function pct(value: unknown, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "–";
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

export function eur(value: unknown): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "–";
  const digits = Math.abs(Number(value)) < 100 ? 2 : 0;
  return `€${Number(value).toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits })}`;
}

export function signed(value: unknown, digits = 1, suffix = "%"): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "–";
  const v = Number(value);
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}${suffix}`;
}

/** Format a KPI by its name (rates as %, seconds, euros). */
export function kpiValue(kpi: string, value: unknown): string {
  if (["service_level", "abandon_rate", "occupancy", "idle_share"].includes(kpi)) return pct(value);
  if (kpi.endsWith("_eur")) return eur(value);
  if (kpi.endsWith("_seconds")) return `${num(value, 1)} s`;
  return num(value, 1);
}

export const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export const PERSONA_COLOR: Record<string, string> = {
  impatient: "var(--critical)",
  normal: "var(--series-1)",
  patient: "var(--series-3)",
};

/** "track_order" -> "Track order". */
export function humanize(value: unknown): string {
  const text = String(value ?? "").replace(/_/g, " ").trim();
  return text ? text[0].toUpperCase() + text.slice(1) : "–";
}

export function dateLabel(value: unknown, withTime = false): string {
  if (!value) return "–";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return "–";
  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

/** 125 -> "2:05". */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Status of an order at the contact date, as a customer reads it. */
export const ORDER_STATUS: Record<string, { label: string; color: string }> = {
  created: { label: "Order received", color: "var(--series-1)" },
  approved: { label: "Payment approved", color: "var(--series-1)" },
  invoiced: { label: "Being prepared", color: "var(--series-4)" },
  processing: { label: "Being prepared", color: "var(--series-4)" },
  shipped: { label: "On its way", color: "var(--series-7)" },
  delivered: { label: "Delivered", color: "var(--series-3)" },
  canceled: { label: "Canceled", color: "var(--critical)" },
  unavailable: { label: "Unavailable", color: "var(--critical)" },
};
