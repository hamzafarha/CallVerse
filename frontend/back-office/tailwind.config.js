// Tailwind configuration. The shared preset holds the design tokens (colors, fonts, shadows); `content` lists
// the files Tailwind scans, so the final CSS keeps only the classes really used.
import preset from "../shared/tailwind.preset.js";

/** @type {import('tailwindcss').Config} */
export default {
  presets: [preset],
  content: ["./index.html", "./src/**/*.{ts,tsx}", "../shared/src/**/*.{ts,tsx}"],
};
