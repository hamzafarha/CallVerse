/**
 * Animation helpers built on framer-motion: page transitions, lists that appear one item after the other,
 * count-up numbers, typing dots, a typewriter, a progress ring and a bar. They respect the system's "reduce
 * motion" setting (useReducedMotion), and main.tsx switches them all off (MotionGlobalConfig.skipAnimations)
 * when the URL contains ?snapshot (for screenshots).
 */
import { MotionGlobalConfig, animate, motion, useMotionValue, useReducedMotion, type Variants } from "framer-motion";
import { useEffect, useRef, useState, type CSSProperties, type MouseEvent, type ReactNode } from "react";

// Easing curve (cubic-bezier): fast start, soft landing. Shared by the animations below.
const EASE = [0.2, 0.7, 0.2, 1] as const;

/** Route transition: fade + slide (no blur: cheap on laptop GPUs). */
export function PageTransition({ children, id }: { children: ReactNode; id: string }) {
  return (
    <motion.div
      key={id}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6, transition: { duration: 0.15 } }}
      transition={{ duration: 0.35, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}

// Variants are named animation states ("hidden" -> "show"). The parent starts its children 0.07 s apart; each
// item fades in, slides up and grows slightly.
const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07, delayChildren: 0.05 } },
};
const item: Variants = {
  hidden: { opacity: 0, y: 16, scale: 0.98 },
  show: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.5, ease: EASE } },
};

/** Children marked with <StaggerItem> enter one after the other. */
export function Stagger({ children, className, style }: { children: ReactNode; className?: string; style?: CSSProperties }) {
  return (
    <motion.div className={className} style={style} variants={stagger} initial="hidden" animate="show">
      {children}
    </motion.div>
  );
}

/**
 * One child of <Stagger>: it uses the "item" variants above.
 */
export function StaggerItem({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div className={className} variants={item}>
      {children}
    </motion.div>
  );
}

/** Fade up when scrolled into view (once). */
export function Reveal({ children, delay = 0, className }: { children: ReactNode; delay?: number; className?: string }) {
  // Animations switched off: render a plain div.
  if (MotionGlobalConfig.skipAnimations) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.6, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}

/** Number that counts up (spring-like) when it appears or changes. */
export function AnimatedNumber({
  value,
  format = (v) => Math.round(v).toLocaleString("en-US"),
  duration = 1.1,
}: {
  value: number | null | undefined;
  format?: (v: number) => string;
  duration?: number;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  // reduce = the user asked the operating system for less motion.
  const reduce = useReducedMotion();
  // useMotionValue holds the moving number outside React state; setText shows it, formatted.
  const motionValue = useMotionValue(0);
  const [text, setText] = useState(() => (value == null ? "–" : format(reduce ? value : 0)));
  useEffect(() => {
    if (value == null || Number.isNaN(value)) {
      setText("–");
      return;
    }
    if (reduce || MotionGlobalConfig.skipAnimations) {
      setText(format(value));
      return;
    }
    // Animate from the current number to the new one; every frame updates the text.
    const controls = animate(motionValue, value, {
      duration,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setText(format(v)),
      onComplete: () => setText(format(value)),
    });
    // Cleanup: stop the animation when the value changes again or the component disappears.
    return () => controls.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return (
    <span ref={ref} className="tabular">
      {text}
    </span>
  );
}

/** Card wrapper whose background follows the cursor with a soft brand glow. */
export function Spotlight({ children, className = "" }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  // Save the mouse position inside the card as CSS variables (--spot-x, --spot-y); the .spotlight class in
  // index.css draws a soft radial glow at that point.
  const move = (event: MouseEvent<HTMLDivElement>) => {
    const box = ref.current?.getBoundingClientRect();
    if (!box || !ref.current) return;
    ref.current.style.setProperty("--spot-x", `${event.clientX - box.left}px`);
    ref.current.style.setProperty("--spot-y", `${event.clientY - box.top}px`);
  };
  return (
    <div ref={ref} onMouseMove={move} className={`spotlight ${className}`}>
      {children}
    </div>
  );
}

/** Three bouncing dots ("is typing…"). */
export function TypingDots({ color = "currentColor" }: { color?: string }) {
  return (
    <span className="inline-flex items-center gap-1" aria-label="typing">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="inline-block h-1.5 w-1.5 rounded-full"
          style={{ background: color }}
          animate={{ y: [0, -4, 0], opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.15, ease: "easeInOut" }}
        />
      ))}
    </span>
  );
}

/** Reveals text character by character (for replies that did not stream). */
export function Typewriter({ text, speed = 12, onDone }: { text: string; speed?: number; onDone?: () => void }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(reduce ? text.length : 0);
  useEffect(() => {
    if (reduce) return;
    setShown(0);
    // About 120 steps whatever the length, so a long text does not take forever.
    const step = Math.max(1, Math.round(text.length / 120));
    const timer = window.setInterval(() => {
      setShown((n) => {
        const next = Math.min(text.length, n + step);
        if (next >= text.length) {
          window.clearInterval(timer);
          onDone?.();
        }
        return next;
      });
    }, speed);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);
  return (
    <span className={shown < text.length ? "caret" : undefined}>
      {text.slice(0, shown)}
    </span>
  );
}

/** Circular progress ring with an animated sweep. `value` in [0, 1]. */
export function Ring({
  value,
  size = 64,
  stroke = 6,
  color = "var(--brand)",
  track = "var(--surface-3)",
  children,
}: {
  value: number;
  size?: number;
  stroke?: number;
  color?: string;
  track?: string;
  children?: ReactNode;
}) {
  // SVG trick: the circle outline is one long dash (strokeDasharray = circumference). The dash offset hides
  // the part not reached yet: value 0.25 draws a quarter of the ring.
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(1, value || 0));
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={track} strokeWidth={stroke} />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference * (1 - clamped) }}
          transition={{ duration: 1.3, ease: [0.16, 1, 0.3, 1] }}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">{children}</div>
    </div>
  );
}

/** Horizontal bar that grows to `value` in [0, 1]. */
export function Bar({ value, color = "var(--brand)", height = 6 }: { value: number; color?: string; height?: number }) {
  return (
    <div className="w-full overflow-hidden rounded-full bg-sunken" style={{ height }}>
      <motion.div
        className="h-full rounded-full"
        style={{ background: color }}
        initial={{ width: 0 }}
        animate={{ width: `${Math.max(0, Math.min(1, value || 0)) * 100}%` }}
        transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
      />
    </div>
  );
}

// Re-exported so the apps import motion helpers from one place.
export { AnimatePresence, motion } from "framer-motion";
