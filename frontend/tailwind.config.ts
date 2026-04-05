import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Manrope", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "monospace"],
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
      },
      borderRadius: {
        lg: "1rem",
        md: "0.75rem",
        sm: "0.5rem",
      },
      boxShadow: {
        soft: "0 22px 60px rgba(6, 24, 44, 0.08)",
      },
      backgroundImage: {
        aurora:
          "radial-gradient(circle at top left, rgba(6,182,212,0.18), transparent 28%), radial-gradient(circle at top right, rgba(251,191,36,0.18), transparent 24%), linear-gradient(180deg, rgba(15,23,42,0.96), rgba(2,6,23,1))",
      },
    },
  },
  plugins: [animate],
} satisfies Config;
