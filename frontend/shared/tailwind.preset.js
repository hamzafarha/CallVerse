/** Tailwind preset shared by the front office and the back office.
 * Colors are CSS variables (src/styles/tokens.css), so light/dark themes switch
 * without rebuilding and charts use the same palette as the UI. */
export default {
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        page: "var(--page)",
        surface: "var(--surface-1)",
        raised: "var(--surface-2)",
        sunken: "var(--surface-3)",
        ink: "var(--text-primary)",
        ink2: "var(--text-secondary)",
        muted: "var(--text-muted)",
        line: "var(--hairline)",
        brand: "var(--brand)",
        brand2: "var(--brand-2)",
        brand3: "var(--brand-3)",
        good: "var(--good)",
        warn: "var(--warning)",
        bad: "var(--critical)",
        layer: {
          data: "var(--layer-data)",
          sim: "var(--layer-sim)",
          agents: "var(--layer-agents)",
          eval: "var(--layer-eval)",
          serve: "var(--layer-serve)",
        },
      },
      fontFamily: {
        sans: ['"Inter Variable"', "system-ui", "-apple-system", '"Segoe UI"', "sans-serif"],
        display: ['"Space Grotesk Variable"', '"Inter Variable"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono Variable"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      borderRadius: { xl: "14px", "2xl": "18px", "3xl": "24px" },
      boxShadow: {
        soft: "0 1px 2px rgb(var(--shadow) / 0.06), 0 8px 24px -12px rgb(var(--shadow) / 0.18)",
        lift: "0 2px 6px rgb(var(--shadow) / 0.08), 0 24px 48px -20px rgb(var(--shadow) / 0.35)",
        glow: "0 0 0 1px var(--brand-soft), 0 8px 30px -6px var(--glow)",
      },
      keyframes: {
        "fade-up": { from: { opacity: "0", transform: "translateY(8px)" }, to: { opacity: "1", transform: "none" } },
        shimmer: { from: { backgroundPosition: "200% 0" }, to: { backgroundPosition: "-200% 0" } },
        "pulse-ring": {
          "0%": { boxShadow: "0 0 0 0 var(--ring-color, var(--glow))" },
          "70%": { boxShadow: "0 0 0 10px transparent" },
          "100%": { boxShadow: "0 0 0 0 transparent" },
        },
        float: { "0%,100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-6px)" } },
        "gradient-pan": { "0%,100%": { backgroundPosition: "0% 50%" }, "50%": { backgroundPosition: "100% 50%" } },
        blink: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0" } },
      },
      animation: {
        "fade-up": "fade-up .5s cubic-bezier(.2,.7,.2,1) both",
        shimmer: "shimmer 2.2s linear infinite",
        "pulse-ring": "pulse-ring 1.8s cubic-bezier(.4,0,.6,1) infinite",
        float: "float 5s ease-in-out infinite",
        "gradient-pan": "gradient-pan 8s ease infinite",
        blink: "blink 1s step-end infinite",
      },
    },
  },
  plugins: [],
};
