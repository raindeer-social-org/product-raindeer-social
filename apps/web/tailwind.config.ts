import type { Config } from "tailwindcss";

// Design tokens sourced 1:1 from "Raindeer Social Startup Onboarding/Raindeer
// Social.dc.html" (the product's canonical design mockup). This is the one
// visual language for the whole app — the earlier n8n-style dark "ink" shell
// is superseded; dark is reserved only for the Content Arena screen, which
// keeps its own literal hex values inline since it's visually a separate
// world from the rest of the app (see app/arena/page.tsx once built).
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Primary blue scale — 600 (#1B4DFF) is the mockup's exact primary;
        // the rest of the ramp is interpolated so utilities like
        // bg-brand-50/border-brand-200 keep working across the app.
        brand: {
          50: "#F0F4FF",
          100: "#E1EAFF",
          200: "#C7D7FF",
          300: "#A3BCFF",
          400: "#7194FF",
          500: "#3D6BFF",
          600: "#1B4DFF",
          700: "#0A2FCC",
          800: "#0A29A6",
          900: "#0B2A6B",
        },
        // Neutral ink/slate scale for text and chrome, matching the
        // mockup's exact greys rather than Tailwind's default slate.
        ink: {
          950: "#0A1633",
          900: "#12203F",
          800: "#22304F",
          700: "#33436B",
          600: "#4A5678",
          500: "#5B6784",
          400: "#6A7691",
          300: "#8B96B2",
          200: "#98A2BC",
          100: "#C7D2EC",
          50: "#E3E8F5",
        },
        // Borders/backgrounds used throughout the mockup that don't fit a
        // simple numeric ramp — kept as named tokens for exact fidelity.
        canvas: "#F6F8FE",
        line: {
          DEFAULT: "#DFE5F3",
          soft: "#E3E8F5",
          faint: "#E7EBF6",
        },
        // Per-agent identity colors — used for avatars, badges, node
        // headers, and anywhere an agent's output needs to read as "theirs"
        // at a glance. `from`/`to` are the two stops of that agent's
        // gradient in the mockup.
        agent: {
          aarav: { from: "#1B4DFF", to: "#8FC4FF", solid: "#1B4DFF" },
          ved: { from: "#0B2A6B", to: "#3C7BFF", solid: "#0B2A6B" },
          keshav: { from: "#6B32C9", to: "#B58BFF", solid: "#6B32C9" },
          kavi: { from: "#0E7A4E", to: "#5AD1A6", solid: "#0E7A4E" },
          neer: { from: "#B46A00", to: "#FFC46B", solid: "#B46A00" },
        },
        success: { DEFAULT: "#0E7A4E", bg: "#E7F7EF" },
        warning: { DEFAULT: "#B46A00", bg: "#FFF3E2" },
        danger: { DEFAULT: "#C9295A", bg: "#FDECEF" },
        violet: { DEFAULT: "#6B32C9", bg: "#F3EBFF" },
        // The Content Arena's own dark theme — namespaced so it never
        // collides with the light app shell's tokens above.
        arenadark: {
          bg: "#080D1E",
          panel: "#0C1330",
          panel2: "#0F1731",
          panel3: "#101838",
          border: "#1B2440",
          border2: "#22305C",
          border3: "#253358",
          text: "#EAF0FF",
          text2: "#C6D2F2",
          text3: "#93A2CC",
          muted: "#5B6A96",
          muted2: "#7C8AB4",
          running: "#6BE3B0",
        },
      },
      fontFamily: {
        sans: ["var(--font-jakarta)", "system-ui", "sans-serif"],
        serif: ["var(--font-instrument-serif)", "serif"],
        mono: ["var(--font-jetbrains-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(0 0 0 / 0.03), 0 1px 3px 0 rgb(0 0 0 / 0.06)",
        "card-hover": "0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.05)",
        popover: "0 10px 15px -3px rgb(0 0 0 / 0.08), 0 4px 6px -4px rgb(0 0 0 / 0.08)",
        // Colored "glow" shadow the mockup puts under every primary button.
        glow: "0 8px 20px -8px rgba(27,77,255,.7)",
        modal: "0 12px 34px -26px rgba(10,22,51,.5)",
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
        // --- mockup-native keyframes, kept under their original rd- names
        // so screens built against the mockup can reference them directly ---
        "rd-blink": { "0%,60%,100%": { opacity: ".25" }, "30%": { opacity: "1" } },
        "rd-spin": { to: { transform: "rotate(360deg)" } },
        "rd-pulse": {
          "0%,100%": { boxShadow: "0 0 0 0 rgba(27,77,255,.35)" },
          "50%": { boxShadow: "0 0 0 10px rgba(27,77,255,0)" },
        },
        "rd-dash": { to: { strokeDashoffset: "-32" } },
        "rd-aurora": { "0%": { transform: "rotate(0deg) scale(1.4)" }, "100%": { transform: "rotate(360deg) scale(1.4)" } },
        "rd-wave": { "0%,100%": { transform: "scaleY(.35)" }, "50%": { transform: "scaleY(1)" } },
        "rd-rise": { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "none" } },
      },
      animation: {
        "fade-in": "fade-in 0.15s ease-out",
        "slide-up": "slide-up 0.2s ease-out",
        "rd-blink": "rd-blink 1.3s infinite",
        "rd-spin": "rd-spin 1s linear infinite",
        "rd-pulse": "rd-pulse 2.6s infinite",
        "rd-dash": "rd-dash 1.4s linear infinite",
        "rd-aurora": "rd-aurora 7s linear infinite",
        "rd-wave": "rd-wave 1.1s ease-in-out infinite",
        "rd-rise": "rd-rise 0.4s ease both",
      },
    },
  },
  plugins: [],
};

export default config;
