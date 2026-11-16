import animate from "tailwindcss-animate";
import type { Config } from "tailwindcss";

/** Colour token backed by an RGB triplet custom property (see src/index.css / src/lib/pixelTheme.ts). */
const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;
const pair = (name: string) => ({ DEFAULT: token(name), foreground: token(`${name}-foreground`) });

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: "1rem", screens: { "2xl": "1400px" } },
    // Pixel art: no rounded corners anywhere, and only hard (unblurred) offset shadows.
    borderRadius: {
      none: "0px",
      sm: "0px",
      DEFAULT: "0px",
      md: "0px",
      lg: "0px",
      xl: "0px",
      "2xl": "0px",
      full: "0px",
    },
    // Pixel borders are 2px by default (`border`, `divide-y`), 4px for heavy frames.
    borderWidth: { DEFAULT: "2px", 0: "0px", 2: "2px", 4: "4px", 8: "8px" },
    boxShadow: {
      none: "none",
      sm: "2px 2px 0 0 rgb(var(--hard-shadow) / 0.25)",
      DEFAULT: "4px 4px 0 0 rgb(var(--hard-shadow) / 0.25)",
      md: "4px 4px 0 0 rgb(var(--hard-shadow) / 0.25)",
      lg: "4px 4px 0 0 rgb(var(--hard-shadow) / 0.3)",
      xl: "8px 8px 0 0 rgb(var(--hard-shadow) / 0.3)",
      inner: "inset 2px 2px 0 0 rgb(var(--hard-shadow) / 0.18)",
    },
    extend: {
      colors: {
        border: token("border"),
        input: token("input"),
        ring: token("ring"),
        frame: token("frame"),
        background: token("background"),
        foreground: token("foreground"),
        primary: pair("primary"),
        secondary: pair("secondary"),
        destructive: pair("destructive"),
        success: pair("success"),
        warning: pair("warning"),
        info: pair("info"),
        muted: pair("muted"),
        accent: pair("accent"),
        popover: pair("popover"),
        card: pair("card"),
        header: pair("header"),
        sidebar: pair("sidebar"),
      },
      fontFamily: {
        // Nunito for all UI text (hibiscus-assets style guide); system monospace only for code/logs.
        sans: ["var(--font-body)"],
        mono: ["var(--font-mono)"],
      },
      animation: {
        // Stepped (8-frame) spinner instead of a smooth tween.
        spin: "spin 1s steps(8, end) infinite",
        pulse: "pulse 1.6s steps(2, end) infinite",
      },
    },
  },
  plugins: [animate],
} satisfies Config;
