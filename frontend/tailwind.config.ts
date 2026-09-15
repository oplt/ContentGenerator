import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        // Universal Sans stand-in: geometric UI sans (DESIGN.md §3)
        sans: ["Manrope", "Arial", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      colors: {
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
        overlay: "hsl(var(--overlay) / <alpha-value>)",
        "electric-blue": "#3E6AE1",
        "carbon-dark": "#171A20",
        graphite: "#393C41",
        pewter: "#5C5E62",
        "silver-fog": "#8E8E8E",
        "light-ash": "#F4F4F4",
        "cloud-gray": "#EEEEEE",
        "chart-1": "hsl(var(--chart-1))",
        "chart-2": "hsl(var(--chart-2))",
        "chart-3": "hsl(var(--chart-3))",
      },
      borderRadius: {
        card: "var(--radius-card)",
        lg: "var(--radius-lg)",
        md: "var(--radius-md)",
        sm: "var(--radius-sm)",
        xl: "var(--radius-lg)",
        "2xl": "var(--radius-lg)",
      },
      boxShadow: {
        card: "var(--shadow-card)",
        soft: "var(--shadow-card)",
        overlay: "var(--shadow-overlay)",
      },
      transitionDuration: {
        ui: "330ms",
      },
      fontSize: {
        "hero": ["2.5rem", { lineHeight: "1.2", fontWeight: "500" }],
        "heading-1": ["2rem", { lineHeight: "1.2", fontWeight: "500" }],
        "heading-2": ["1.5rem", { lineHeight: "1.25", fontWeight: "500" }],
        "heading-3": ["1.0625rem", { lineHeight: "1.2", fontWeight: "500" }],
      },
    },
  },
  plugins: [animate],
} satisfies Config;
