/**
 * Hibiscus theme: semantic shadcn/Tailwind tokens with the hibiscus-assets colours
 * (`src/hibiscus/tokens.css`, synced — never edit it here) for day (light) and night (dark).
 *
 * `src/index.css` declares the same values as RGB triplets (`--primary: 47 107 58;`) for Tailwind's
 * `rgb(var(--x) / <alpha-value>)` colours; `pixelTheme.test.ts` keeps index.css, this file and the
 * synced tokens.css in sync and checks every text/background pair against WCAG 2.1 AA.
 */

export const TOKEN_NAMES = [
  "background",
  "foreground",
  "card",
  "card-foreground",
  "popover",
  "popover-foreground",
  "primary",
  "primary-foreground",
  "secondary",
  "secondary-foreground",
  "muted",
  "muted-foreground",
  "accent",
  "accent-foreground",
  "destructive",
  "destructive-foreground",
  "success",
  "success-foreground",
  "warning",
  "warning-foreground",
  "info",
  "info-foreground",
  "border",
  "input",
  "ring",
  "frame",
  "header",
  "header-foreground",
  "sidebar",
  "sidebar-foreground",
  "chart-1",
  "chart-2",
  "chart-3",
  "chart-4",
  "chart-5",
  "chart-6",
  "chart-7",
  "chart-8",
] as const;

export type TokenName = (typeof TOKEN_NAMES)[number];
export type ThemeName = "light" | "dark";

/** Day = parchment garden (wood frames), night = indigo sky (flat indigo frames, hard shadows). */
export const THEME_TOKENS: Record<ThemeName, Record<TokenName, string>> = {
  light: {
    background: "#f3dfb2",
    foreground: "#3b2027",
    card: "#fff6dc",
    "card-foreground": "#3b2027",
    popover: "#fff6dc",
    "popover-foreground": "#3b2027",
    primary: "#2f6b3a",
    "primary-foreground": "#fff6dc",
    secondary: "#c99a62",
    "secondary-foreground": "#3b2027",
    muted: "#f3dfb2",
    "muted-foreground": "#6b4433",
    accent: "#ecd5a4",
    "accent-foreground": "#3b2027",
    destructive: "#8c1c3a",
    "destructive-foreground": "#fff6dc",
    success: "#2f6b3a",
    "success-foreground": "#fff6dc",
    warning: "#8a4a0c",
    "warning-foreground": "#fff6dc",
    info: "#2f6f9f",
    "info-foreground": "#fff6dc",
    border: "#c99a62",
    input: "#3b2027",
    ring: "#5ef1e3",
    frame: "#3b2027",
    header: "#6b4433",
    "header-foreground": "#fff6dc",
    sidebar: "#c99a62",
    "sidebar-foreground": "#3b2027",
    "chart-1": "#2f6f9f",
    "chart-2": "#d7263d",
    "chart-3": "#2f6b3a",
    "chart-4": "#7b5bb5",
    "chart-5": "#6b4433",
    "chart-6": "#8c1c3a",
    "chart-7": "#4a5368",
    "chart-8": "#f08a24",
  },
  dark: {
    background: "#161a2e",
    foreground: "#f4ecd6",
    card: "#222842",
    "card-foreground": "#f4ecd6",
    popover: "#222842",
    "popover-foreground": "#f4ecd6",
    primary: "#9bd35a",
    "primary-foreground": "#161a2e",
    secondary: "#3a4370",
    "secondary-foreground": "#f4ecd6",
    muted: "#2b3253",
    "muted-foreground": "#aeb9d0",
    accent: "#2b3253",
    "accent-foreground": "#f4ecd6",
    destructive: "#ff9eb5",
    "destructive-foreground": "#161a2e",
    success: "#9bd35a",
    "success-foreground": "#161a2e",
    warning: "#ffc531",
    "warning-foreground": "#161a2e",
    info: "#6fb7e8",
    "info-foreground": "#161a2e",
    border: "#3d4566",
    input: "#8b9bb4",
    ring: "#5ef1e3",
    frame: "#0c0e1f",
    header: "#11142a",
    "header-foreground": "#f4ecd6",
    sidebar: "#1b2038",
    "sidebar-foreground": "#f4ecd6",
    "chart-1": "#6fb7e8",
    "chart-2": "#ff9eb5",
    "chart-3": "#9bd35a",
    "chart-4": "#b39ce6",
    "chart-5": "#ffc531",
    "chart-6": "#5ef1e3",
    "chart-7": "#c7d3e3",
    "chart-8": "#f08a24",
  },
};

/** App token → the hibiscus-assets tokens.css variable it must equal (same value in both themes). */
export const ASSET_TOKEN_MAP: Partial<Record<TokenName, string>> = {
  background: "--bg",
  foreground: "--text",
  card: "--surface",
  "muted-foreground": "--muted",
  border: "--border",
  frame: "--frame",
  primary: "--accent",
  success: "--ok",
  warning: "--warn",
  destructive: "--danger",
  info: "--info",
  ring: "--ring",
  header: "--header-bg",
  "header-foreground": "--header-text",
  sidebar: "--sidebar-bg",
};

/** Fixed label colours on the pixel buttons (sprite centre in day, flat fill at night). */
export const BUTTON_COLOURS = {
  light: {
    primary: ["#5fa04e", "#3b2027"],
    secondary: ["#c99a62", "#3b2027"],
    danger: ["#8c1c3a", "#fff6dc"],
  },
  dark: {
    primary: ["#5fa04e", "#161a2e"],
    secondary: ["#3a4370", "#f4ecd6"],
    danger: ["#a3214a", "#fff6dc"],
  },
} as const;

/** Text-on-surface pairs that must reach WCAG 2.1 AA for normal text (4.5:1) in both themes. */
export const TEXT_PAIRS: readonly [TokenName, TokenName][] = [
  ["foreground", "background"],
  ["foreground", "muted"],
  ["foreground", "accent"],
  ["card-foreground", "card"],
  ["popover-foreground", "popover"],
  ["muted-foreground", "background"],
  ["muted-foreground", "card"],
  ["muted-foreground", "muted"],
  ["primary", "muted"],
  ["primary", "background"],
  ["primary", "card"],
  ["primary-foreground", "primary"],
  ["secondary-foreground", "secondary"],
  ["accent-foreground", "accent"],
  ["destructive", "background"],
  ["destructive", "card"],
  ["destructive-foreground", "destructive"],
  ["success", "card"],
  ["success-foreground", "success"],
  ["warning", "card"],
  ["warning-foreground", "warning"],
  ["info", "card"],
  ["info-foreground", "info"],
  ["header-foreground", "header"],
  ["sidebar-foreground", "sidebar"],
];

/** Non-text UI (form-field borders, chart lines, focus ring) needs 3:1 against its surface. */
export const UI_PAIRS: readonly [TokenName, TokenName][] = [
  ["input", "card"],
  ["input", "background"],
  ["chart-1", "card"],
  ["chart-2", "card"],
  ["chart-3", "card"],
  ["chart-4", "card"],
  ["chart-5", "card"],
  ["chart-6", "card"],
  ["chart-7", "card"],
];

export function tokenHex(theme: ThemeName, token: TokenName): string {
  return THEME_TOKENS[theme][token];
}

export function hexToRgbTriplet(hex: string): string {
  const n = Number.parseInt(hex.replace("#", ""), 16);
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
}

function channel(v: number): number {
  const s = v / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

export function relativeLuminance(hex: string): number {
  const [r = 0, g = 0, b = 0] = hexToRgbTriplet(hex).split(" ").map(Number);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** CSS custom-property block for a theme (what index.css must contain). */
export function themeCssVariables(theme: ThemeName): Record<string, string> {
  return Object.fromEntries(TOKEN_NAMES.map((t) => [`--${t}`, hexToRgbTriplet(tokenHex(theme, t))]));
}
