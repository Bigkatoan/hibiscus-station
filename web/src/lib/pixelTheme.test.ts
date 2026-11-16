import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  ASSET_TOKEN_MAP,
  BUTTON_COLOURS,
  contrastRatio,
  hexToRgbTriplet,
  TEXT_PAIRS,
  themeCssVariables,
  tokenHex,
  TOKEN_NAMES,
  UI_PAIRS,
  type ThemeName,
  type TokenName,
} from "./pixelTheme";

const css = readFileSync(resolve(__dirname, "../index.css"), "utf8");
const assetTokens = readFileSync(resolve(__dirname, "../hibiscus/tokens.css"), "utf8");

function block(source: string, selector: string): Record<string, string> {
  const start = source.indexOf(`${selector} {`);
  expect(start, selector).toBeGreaterThan(-1);
  const body = source.slice(start, source.indexOf("}", start));
  return Object.fromEntries(
    [...body.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((m) => [m[1] ?? "", (m[2] ?? "").trim()]),
  );
}

const THEMES: [ThemeName, string, string][] = [
  ["light", ":root", ":root"],
  ["dark", ".dark", ":root[data-theme='dark']"],
];

describe("Hibiscus theme tokens", () => {
  it.each(THEMES)("%s: index.css declares exactly the typed tokens", (theme, selector) => {
    const declared = block(css, selector);
    for (const [name, value] of Object.entries(themeCssVariables(theme))) {
      expect(declared[name], name).toBe(value);
    }
  });

  it.each(THEMES)("%s: tokens match the synced hibiscus-assets tokens.css", (theme, _sel, assetSelector) => {
    // The night block only overrides what changes; the rest is inherited from :root.
    const asset = { ...block(assetTokens, ":root"), ...block(assetTokens, assetSelector) };
    for (const [app, variable] of Object.entries(ASSET_TOKEN_MAP)) {
      expect(asset[variable]?.toLowerCase(), `${app} = ${variable}`).toBe(tokenHex(theme, app as TokenName));
    }
  });

  it("every token is a hex colour", () => {
    for (const theme of ["light", "dark"] as const) {
      for (const t of TOKEN_NAMES) expect(tokenHex(theme, t)).toMatch(/^#[0-9a-f]{6}$/);
    }
  });

  it.each(["light", "dark"] as const)("%s: text pairs meet WCAG 2.1 AA (4.5:1)", (theme) => {
    for (const [fg, bg] of TEXT_PAIRS) {
      expect(
        contrastRatio(tokenHex(theme, fg), tokenHex(theme, bg)),
        `${fg} on ${bg}`,
      ).toBeGreaterThanOrEqual(4.5);
    }
  });

  it.each(["light", "dark"] as const)("%s: UI pairs meet 3:1 (fields, chart lines)", (theme) => {
    for (const [fg, bg] of UI_PAIRS) {
      expect(
        contrastRatio(tokenHex(theme, fg), tokenHex(theme, bg)),
        `${fg} on ${bg}`,
      ).toBeGreaterThanOrEqual(3);
    }
  });

  it.each(["light", "dark"] as const)("%s: button labels stay readable on their fills", (theme) => {
    const colours = BUTTON_COLOURS[theme];
    for (const name of ["primary", "secondary", "danger"] as const) {
      const [bg, fg] = colours[name];
      expect(contrastRatio(bg, fg), name).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("focus glow is visible on the night sky and its dark ring on parchment", () => {
    expect(contrastRatio(tokenHex("dark", "ring"), tokenHex("dark", "background"))).toBeGreaterThanOrEqual(3);
    expect(contrastRatio(tokenHex("light", "frame"), tokenHex("light", "background"))).toBeGreaterThanOrEqual(
      3,
    );
  });

  it("converts and measures like WCAG", () => {
    expect(hexToRgbTriplet("#3b2027")).toBe("59 32 39");
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 5);
  });

  it("no rounded corners or blurred shadows in the Tailwind theme", async () => {
    const { default: config } = await import("../../tailwind.config");
    const radius = config.theme.borderRadius as Record<string, string>;
    expect(Object.values(radius).every((v) => v === "0px")).toBe(true);
    const shadows = Object.values(config.theme.boxShadow as Record<string, string>);
    // "x y blur spread": every shadow is hard (blur 0) and offsets are whole art pixels (2 px).
    for (const s of shadows) {
      if (s === "none") continue;
      const m = /^(inset )?(-?\d+)px (-?\d+)px 0 /.exec(s);
      expect(m, s).not.toBeNull();
      expect(Number(m?.[2]) % 2, s).toBe(0);
      expect(Number(m?.[3]) % 2, s).toBe(0);
    }
  });

  it("fonts are self-hosted Nunito with the Vietnamese subset, no pixel fonts", () => {
    const fonts = readFileSync(resolve(__dirname, "../hibiscus/fonts.css"), "utf8");
    expect(fonts).not.toMatch(/googleapis|gstatic/);
    expect(fonts).toContain("/fonts/nunito-vietnamese.woff2");
    expect(css).not.toMatch(/Tiny5|VT323/);
  });
});
