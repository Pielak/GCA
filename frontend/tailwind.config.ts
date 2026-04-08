import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // GPD brand colors
        violet: {
          50: "#f5f3ff",
          100: "#ede9fe",
          500: "#8b5cf6",
          600: "#7c3aed",  // brand primary
          700: "#6d28d9",
          900: "#2e1065",
        },
        emerald: {
          400: "#34d399",
          500: "#10b981",  // brand action
          600: "#059669",
        },
        dark: {
          DEFAULT: "#0d0d18",  // sidebar + login bg
          100: "#1a1a2e",
          200: "#16213e",
        },
      },
      fontFamily: {
        sans: ["Plus Jakarta Sans", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
