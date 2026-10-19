/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        page: "var(--page)",
        surface: "var(--surface-1)",
        raised: "var(--surface-2)",
        ink: "var(--text-primary)",
        ink2: "var(--text-secondary)",
        muted: "var(--text-muted)",
        line: "var(--hairline)",
        brand: "var(--brand)",
        layer: {
          data: "var(--layer-data)",
          sim: "var(--layer-sim)",
          agents: "var(--layer-agents)",
          eval: "var(--layer-eval)",
          serve: "var(--layer-serve)",
        },
      },
      fontFamily: { sans: ['system-ui', '-apple-system', '"Segoe UI"', "sans-serif"] },
    },
  },
  plugins: [],
};
