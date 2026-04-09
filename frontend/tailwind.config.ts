import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Manrope", "Arial", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "monospace"],
      },
      colors: {
        // ── shadcn-compatible semantic tokens ─────────────────────────────
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: "hsl(var(--card))",
        "card-foreground": "hsl(var(--card-foreground))",
        muted: "hsl(var(--muted))",
        "muted-foreground": "hsl(var(--muted-foreground))",
        primary: "hsl(var(--primary))",
        "primary-foreground": "hsl(var(--primary-foreground))",
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        accent: "hsl(var(--accent))",
        "accent-foreground": "hsl(var(--accent-foreground))",
        destructive: "hsl(var(--destructive))",
        "destructive-foreground": "hsl(var(--destructive-foreground))",
        success: "hsl(var(--success))",
        warning: "hsl(var(--warning))",
        // ── Modal overlay ──────────────────────────────────────────────────
        overlay: "hsl(var(--overlay) / <alpha-value>)",
        // ── Warm palette — direct access for brand moments ─────────────────
        "mistral-orange": "#fa520f",
        "mistral-flame":  "#fb6424",
        "block-orange":   "#ff8105",
        "sunshine-900":   "#ff8a00",
        "sunshine-700":   "#ffa110",
        "sunshine-500":   "#ffb83e",
        "sunshine-300":   "#ffd06a",
        "block-gold":     "#ffe295",
        "bright-yellow":  "#ffd900",
        "warm-ivory":     "#fffaeb",
        "mistral-black":  "#1f1f1f",
        // ── Chart palette ──────────────────────────────────────────────────
        "chart-1": "hsl(var(--chart-1))",
        "chart-2": "hsl(var(--chart-2))",
        "chart-3": "hsl(var(--chart-3))",
      },

      // ── Near-zero architectural corners (DESIGN.md §5) ─────────────────
      // "Near-zero: the dominant radius — sharp, architectural corners"
      borderRadius: {
        card: "var(--radius-card)",   // 2px
        lg:   "var(--radius-lg)",     // 2px
        md:   "var(--radius-md)",     // 2px
        sm:   "var(--radius-sm)",     // 2px
        // xl keeps a slightly larger value for pill/tag shapes if needed
        xl:   "var(--radius-lg)",     // 2px
        "2xl": "var(--radius-lg)",    // 2px — collapse all rounded to near-zero
      },

      // ── Warm amber shadow system (DESIGN.md §6) ─────────────────────────
      boxShadow: {
        card:    "var(--shadow-card)",
        soft:    "var(--shadow-card)",   // legacy alias
        overlay: "var(--shadow-overlay)",
      },

      // ── Auth hero — warm gradient replacing cool aurora ──────────────────
      backgroundImage: {
        aurora:
          "linear-gradient(160deg, #fffaeb 0%, #fff0c2 20%, #ffa110 50%, #fa520f 70%, #1f1f1f 100%)",
      },

      // ── Type scale following DESIGN.md §3 ───────────────────────────────
      fontSize: {
        display: ["5.125rem", { lineHeight: "1.0",  letterSpacing: "-2.05px" }], // 82px
        "heading-1": ["3.5rem",  { lineHeight: "0.95", letterSpacing: "0" }],    // 56px
        "heading-2": ["3rem",    { lineHeight: "0.95", letterSpacing: "0" }],    // 48px
        "heading-3": ["2rem",    { lineHeight: "1.15", letterSpacing: "0" }],    // 32px
        "heading-4": ["1.5rem",  { lineHeight: "1.33", letterSpacing: "0" }],    // 24px
      },
    },
  },
  plugins: [animate],
} satisfies Config;
