import { clsx, dateLabel, motion } from "@callverse/shared";
import { AlertTriangle, Check, CreditCard, Home, ShoppingBag, Truck, XCircle } from "lucide-react";

const ICONS = [ShoppingBag, CreditCard, Truck, Home, XCircle];

export interface TimelineStep {
  label: string;
  state: "done" | "current" | "upcoming" | "late";
  at?: string | null;
  due?: string | null;
}

/** Order journey at the contact date; steps animate in one after another. */
export function OrderTimeline({ steps, compact = false }: { steps: TimelineStep[]; compact?: boolean }) {
  const doneCount = steps.filter((s) => s.state === "done").length;
  const progress = steps.length > 1 ? Math.max(0, doneCount - 1) / (steps.length - 1) : 0;
  return (
    <div className="relative">
      <div className={clsx("absolute h-1 rounded-full bg-sunken", compact ? "left-4 right-4 top-4" : "left-6 right-6 top-6")} />
      <motion.div
        className={clsx("absolute h-1 rounded-full gradient-brand", compact ? "left-4 top-4" : "left-6 top-6")}
        initial={{ width: 0 }}
        animate={{ width: `calc((100% - ${compact ? 2 : 3}rem) * ${progress})` }}
        transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
      />
      <div className="relative flex justify-between">
        {steps.map((step, i) => {
          const Icon = step.state === "late" ? AlertTriangle : ICONS[Math.min(i, ICONS.length - 1)];
          const color =
            step.state === "done" ? "var(--brand)" : step.state === "late" ? "var(--critical)" : step.state === "current" ? "var(--brand-2)" : "var(--surface-3)";
          return (
            <motion.div
              key={step.label}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 + i * 0.18 }}
              className={clsx("flex flex-col items-center text-center", compact ? "w-16" : "w-24")}
            >
              <div
                className={clsx(
                  "relative flex items-center justify-center rounded-full border-4 border-[var(--surface-1)]",
                  compact ? "h-9 w-9" : "h-12 w-12",
                  (step.state === "current" || step.state === "late") && "animate-pulse-ring",
                )}
                style={{ background: color, color: step.state === "upcoming" ? "var(--text-muted)" : "white", ["--ring-color" as any]: color }}
              >
                {step.state === "done" ? <Check size={compact ? 14 : 18} strokeWidth={3} /> : <Icon size={compact ? 14 : 18} />}
              </div>
              <div className={clsx("mt-2 font-medium leading-tight text-ink", compact ? "text-[10px]" : "text-xs")}>{step.label}</div>
              {!compact && (
                <div className={clsx("mt-0.5 text-[11px]", step.state === "late" ? "font-semibold text-bad" : "text-muted")}>
                  {step.at ? dateLabel(step.at) : step.due ? `${step.state === "late" ? "was due" : "by"} ${dateLabel(step.due)}` : ""}
                </div>
              )}
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
