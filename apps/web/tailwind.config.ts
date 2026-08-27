import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f5f3ff",
          100: "#ede9fe",
          200: "#ddd6fe",
          300: "#c4b5fd",
          400: "#a78bfa",
          500: "#8b5cf6",
          600: "#7c3aed",
          700: "#6d28d9",
          800: "#5b21b6",
          900: "#4c1d95",
        },
        // Dark, near-black "chrome" scale for the app shell (sidebar, the
        // command palette panel) — this is what gives the app its
        // n8n-style "workflow tool" feel. Page *content* (cards, forms,
        // tables) intentionally stays on the light `slate` scale so it
        // remains as readable as before; only the surrounding shell uses
        // `ink`.
        ink: {
          950: "#0b0b10",
          900: "#131318",
          800: "#1b1b22",
          700: "#26262f",
          600: "#34343f",
          500: "#4b4b59",
          400: "#71717e",
          300: "#9a9aa6",
          200: "#c4c4cc",
          100: "#e6e6ea",
        },
        // Coral/amber "signal" accent used sparingly against the dark
        // chrome (active nav item, palette trigger, keyboard hints) —
        // distinct from `brand`, which stays the primary action color
        // used throughout page content.
        accent: {
          50: "#fff3f0",
          100: "#ffe4dc",
          200: "#ffc4b3",
          300: "#ff9d84",
          400: "#ff7a5c",
          500: "#f9603f",
          600: "#e6472a",
          700: "#c13620",
          800: "#992a19",
          900: "#7a2415",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        // Technical/monospace accent used for shell chrome — nav section
        // labels, keyboard-shortcut hints, agent-id tags — not for body
        // copy or form content.
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(0 0 0 / 0.03), 0 1px 3px 0 rgb(0 0 0 / 0.06)",
        "card-hover": "0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.05)",
        popover: "0 10px 15px -3px rgb(0 0 0 / 0.08), 0 4px 6px -4px rgb(0 0 0 / 0.08)",
        // Denser, flatter shadow for elements sitting on the dark shell.
        chrome: "0 8px 24px -8px rgb(0 0 0 / 0.5)",
      },
      borderRadius: {
        xl2: "1rem",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-dot": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.15s ease-out",
        "slide-up": "slide-up 0.2s ease-out",
        "pulse-dot": "pulse-dot 1.8s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
