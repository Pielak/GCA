import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // === GCA Design System "Observatory" ===
        // Surface layers (do mais profundo ao mais elevado)
        surface: {
          void: "#06060e",      // fundo absoluto, atrás de tudo
          deep: "#0a0a16",      // sidebar, painéis laterais
          base: "#0f0f1e",      // fundo principal das páginas
          raised: "#161628",    // cards, containers
          overlay: "#1c1c34",   // modais, dropdowns, popovers
          float: "#232340",     // elementos flutuantes, tooltips
        },
        // Brand — violeta como identidade primária
        brand: {
          50: "#ede5ff",
          100: "#d4c4ff",
          200: "#b99aff",
          300: "#9d6fff",
          400: "#8550f6",      // hover
          500: "#7038e0",      // primário
          600: "#5c2cb8",      // pressed
          700: "#47218f",
          800: "#331766",
          900: "#1e0d3d",
          glow: "rgba(112, 56, 224, 0.15)", // sombra/glow sutil
        },
        // Accent — ciano para ações secundárias e destaques
        accent: {
          50: "#e0feff",
          100: "#b3faff",
          200: "#6ef3ff",
          300: "#33e8f7",
          400: "#0dd4e6",      // hover
          500: "#00b8cc",      // primário
          600: "#009aab",
          700: "#007a88",
          glow: "rgba(0, 184, 204, 0.12)",
        },
        // Status — cores semânticas
        status: {
          success: "#22c55e",
          warning: "#f59e0b",
          error: "#ef4444",
          info: "#3b82f6",
        },
        // Texto — hierarquia clara
        ink: {
          primary: "#e8e6f0",    // títulos, texto principal
          secondary: "#9895a8",  // texto auxiliar
          muted: "#5e5b6e",      // placeholders, disabled
          inverse: "#0a0a16",    // texto sobre fundo claro
        },
        // Bordas
        edge: {
          subtle: "rgba(255, 255, 255, 0.06)",
          DEFAULT: "rgba(255, 255, 255, 0.10)",
          strong: "rgba(255, 255, 255, 0.16)",
          brand: "rgba(112, 56, 224, 0.30)",
          accent: "rgba(0, 184, 204, 0.25)",
        },
        // Retrocompat (manter páginas existentes funcionando)
        violet: {
          50: "#f5f3ff",
          100: "#ede9fe",
          300: "#9d6fff",
          400: "#8550f6",
          500: "#8b5cf6",
          600: "#7c3aed",
          700: "#6d28d9",
          900: "#2e1065",
        },
        emerald: {
          400: "#34d399",
          500: "#10b981",
          600: "#059669",
        },
        dark: {
          DEFAULT: "#0a0a16",
          100: "#0f0f1e",
          200: "#161628",
        },
      },
      fontFamily: {
        sans: ["Plus Jakarta Sans", "system-ui", "sans-serif"],
        display: ["Outfit", "Plus Jakarta Sans", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      fontSize: {
        "display-xl": ["3rem", { lineHeight: "1.1", letterSpacing: "-0.025em", fontWeight: "700" }],
        "display-lg": ["2.25rem", { lineHeight: "1.15", letterSpacing: "-0.02em", fontWeight: "700" }],
        "display-md": ["1.75rem", { lineHeight: "1.2", letterSpacing: "-0.015em", fontWeight: "600" }],
        "display-sm": ["1.25rem", { lineHeight: "1.3", letterSpacing: "-0.01em", fontWeight: "600" }],
      },
      boxShadow: {
        "glow-brand": "0 0 20px rgba(112, 56, 224, 0.20), 0 0 60px rgba(112, 56, 224, 0.08)",
        "glow-accent": "0 0 20px rgba(0, 184, 204, 0.18), 0 0 60px rgba(0, 184, 204, 0.06)",
        "glow-sm": "0 0 10px rgba(112, 56, 224, 0.12)",
        "elevated": "0 8px 32px rgba(0, 0, 0, 0.40), 0 2px 8px rgba(0, 0, 0, 0.30)",
        "card": "0 2px 12px rgba(0, 0, 0, 0.25), 0 0 1px rgba(255, 255, 255, 0.05)",
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "gradient-brand": "linear-gradient(135deg, #7038e0 0%, #8550f6 50%, #00b8cc 100%)",
        "gradient-surface": "linear-gradient(180deg, #0f0f1e 0%, #0a0a16 100%)",
        "noise": "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.03'/%3E%3C/svg%3E\")",
      },
      borderRadius: {
        "xl": "12px",
        "2xl": "16px",
        "3xl": "20px",
      },
      animation: {
        "fade-in": "fadeIn 0.3s ease-out",
        "fade-up": "fadeUp 0.4s ease-out",
        "slide-in": "slideIn 0.3s ease-out",
        "pulse-glow": "pulseGlow 3s ease-in-out infinite",
        "float": "float 6s ease-in-out infinite",
        "shimmer": "shimmer 2s linear infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideIn: {
          "0%": { opacity: "0", transform: "translateX(-8px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        pulseGlow: {
          "0%, 100%": { opacity: "0.4" },
          "50%": { opacity: "0.8" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-8px)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
