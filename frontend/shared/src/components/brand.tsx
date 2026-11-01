import { motion } from "framer-motion";
import { Moon, Sun } from "lucide-react";

/** CallVerse mark: a speech bubble whose tail is an orbiting agent. */
export function LogoMark({ size = 36, animated = true }: { size?: number; animated?: boolean }) {
  return (
    <div
      className="relative flex shrink-0 items-center justify-center rounded-[30%] shadow-glow"
      style={{ width: size, height: size, background: "linear-gradient(135deg, var(--brand), var(--brand-2))" }}
    >
      <svg viewBox="0 0 32 32" width={size * 0.66} height={size * 0.66} fill="none">
        <path
          d="M7 9.5C7 8.12 8.12 7 9.5 7h13C23.88 7 25 8.12 25 9.5v8c0 1.38-1.12 2.5-2.5 2.5H15l-5 4v-4h-.5A2.5 2.5 0 0 1 7 17.5v-8Z"
          fill="white"
          fillOpacity={0.95}
        />
        <circle cx="12" cy="13.5" r="1.5" fill="var(--brand)" />
        <circle cx="16" cy="13.5" r="1.5" fill="var(--brand)" />
        <circle cx="20" cy="13.5" r="1.5" fill="var(--brand)" />
      </svg>
      {animated && (
        <motion.span
          className="absolute inset-0"
          animate={{ rotate: 360 }}
          transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
        >
          <span
            className="absolute -right-0.5 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-white"
            style={{ boxShadow: "0 0 8px 2px var(--brand-2)" }}
          />
        </motion.span>
      )}
    </div>
  );
}

export function Logo({ product, tagline }: { product?: string; tagline?: string }) {
  return (
    <div className="flex items-center gap-3">
      <LogoMark />
      <div className="leading-tight">
        <div className="font-display text-[17px] font-bold tracking-tight text-ink">
          CallVerse{product && <span className="gradient-text"> {product}</span>}
        </div>
        {tagline && <div className="text-[11px] text-muted">{tagline}</div>}
      </div>
    </div>
  );
}

/** Slow-moving blurred color fields + dot grid, behind everything. */
export function Aurora({ intensity = 1 }: { intensity?: number }) {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden" aria-hidden>
      <div
        className="absolute -left-[10%] -top-[20%] h-[55vmax] w-[55vmax] rounded-full blur-3xl"
        style={{ background: "var(--aurora-1)", opacity: intensity, animation: "aurora 26s ease-in-out infinite" }}
      />
      <div
        className="absolute -right-[15%] top-[10%] h-[45vmax] w-[45vmax] rounded-full blur-3xl"
        style={{ background: "var(--aurora-2)", opacity: intensity, animation: "aurora 32s ease-in-out infinite reverse" }}
      />
      <div
        className="absolute bottom-[-25%] left-[30%] h-[40vmax] w-[40vmax] rounded-full blur-3xl"
        style={{ background: "var(--aurora-3)", opacity: intensity, animation: "aurora 38s ease-in-out infinite" }}
      />
      <div
        className="bg-dots absolute inset-0"
        style={{ maskImage: "radial-gradient(ellipse at 50% 0%, #000 20%, transparent 70%)" }}
      />
    </div>
  );
}

export function ThemeToggle({ dark, toggle }: { dark: boolean; toggle: () => void }) {
  return (
    <button onClick={toggle} className="btn btn-ghost btn-icon relative overflow-hidden" aria-label="Toggle theme">
      <motion.span
        key={dark ? "sun" : "moon"}
        initial={{ y: 14, opacity: 0, rotate: -40 }}
        animate={{ y: 0, opacity: 1, rotate: 0 }}
        transition={{ type: "spring", bounce: 0.4, duration: 0.5 }}
      >
        {dark ? <Sun size={16} /> : <Moon size={16} />}
      </motion.span>
    </button>
  );
}
