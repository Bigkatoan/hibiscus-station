/**
 * Hibiscus look for Blockly (station-programs.md §5): palette colours from the design system
 * (`hibiscus/sprites.gen.ts` PALETTE), Nunito, square corners (a renderer with no corner radius),
 * day = parchment workspace with wood toolbox, night = flat indigo frames.
 * Block colours keep cream text (#fff6dc) at WCAG AA in both themes.
 */
import * as Blockly from "blockly/core";
import { PALETTE } from "@/hibiscus/sprites.gen";

/** Block colour per style; also used for the toolbox category stripes. */
export const BLOCK_COLOURS = {
  hb_start_blocks: PALETTE.n,
  hb_motion_blocks: PALETTE.b,
  hb_ai_blocks: "#6a4aa3",
  hb_control_blocks: PALETTE.f,
  hb_conditions_blocks: "#8a4a0c",
  hb_operator_blocks: PALETTE.d,
  hb_data_blocks: PALETTE.k,
  hb_output_blocks: PALETTE.m,
} as const;

/** Built-in Blockly styles mapped onto the same categories as the catalogue. */
const BUILTIN_STYLES: Record<string, keyof typeof BLOCK_COLOURS> = {
  logic_blocks: "hb_conditions_blocks",
  loop_blocks: "hb_control_blocks",
  math_blocks: "hb_data_blocks",
  text_blocks: "hb_data_blocks",
  variable_blocks: "hb_data_blocks",
  variable_dynamic_blocks: "hb_data_blocks",
  hat_blocks: "hb_start_blocks",
  procedure_blocks: "hb_control_blocks",
  list_blocks: "hb_data_blocks",
  colour_blocks: "hb_data_blocks",
};

export const TOOLBOX_CATEGORIES = ["motion", "ai", "control", "conditions", "data", "output"] as const;
export type ToolboxCategory = (typeof TOOLBOX_CATEGORIES)[number];

const CATEGORY_COLOUR: Record<ToolboxCategory, string> = {
  motion: BLOCK_COLOURS.hb_motion_blocks,
  ai: BLOCK_COLOURS.hb_ai_blocks,
  control: BLOCK_COLOURS.hb_control_blocks,
  conditions: BLOCK_COLOURS.hb_conditions_blocks,
  data: BLOCK_COLOURS.hb_data_blocks,
  output: BLOCK_COLOURS.hb_output_blocks,
};

/** Darken (#rrggbb, factor < 1) for the secondary/tertiary block colours. */
export function shade(hex: string, factor: number): string {
  const n = Number.parseInt(hex.slice(1), 16);
  const ch = (s: number) =>
    Math.max(0, Math.min(255, Math.round(((n >> s) & 255) * factor)))
      .toString(16)
      .padStart(2, "0");
  return `#${ch(16)}${ch(8)}${ch(0)}`;
}

function blockStyles(): Record<string, Blockly.Theme.BlockStyle> {
  const style = (c: string): Blockly.Theme.BlockStyle => ({
    colourPrimary: c,
    colourSecondary: shade(c, 1.25),
    colourTertiary: shade(c, 0.7),
    hat: "cap",
  });
  const out: Record<string, Blockly.Theme.BlockStyle> = {};
  for (const [name, c] of Object.entries(BLOCK_COLOURS)) out[name] = style(c);
  for (const [name, to] of Object.entries(BUILTIN_STYLES)) out[name] = style(BLOCK_COLOURS[to]);
  return out;
}

function categoryStyles(): Record<string, Blockly.Theme.CategoryStyle> {
  return Object.fromEntries(
    Object.entries(CATEGORY_COLOUR).map(([k, c]) => [`hb_${k}_category`, { colour: c }]),
  );
}

const FONT: Blockly.Theme.FontStyle = {
  family: "Nunito, ui-sans-serif, system-ui, sans-serif",
  weight: "700",
  size: 12,
};

export const THEME_NAMES = { light: "hibiscus-light", dark: "hibiscus-dark" } as const;

let themes: Record<"light" | "dark", Blockly.Theme> | null = null;

export function hibiscusTheme(mode: "light" | "dark"): Blockly.Theme {
  themes ??= {
    light: Blockly.Theme.defineTheme(THEME_NAMES.light, {
      name: THEME_NAMES.light,
      base: Blockly.Themes.Classic,
      blockStyles: blockStyles(),
      categoryStyles: categoryStyles(),
      componentStyles: {
        workspaceBackgroundColour: "#f3dfb2",
        toolboxBackgroundColour: "#c99a62",
        toolboxForegroundColour: "#3b2027",
        flyoutBackgroundColour: "#ecd5a4",
        flyoutForegroundColour: "#3b2027",
        flyoutOpacity: 1,
        scrollbarColour: "#9c6b45",
        scrollbarOpacity: 0.8,
        insertionMarkerColour: "#3b2027",
        insertionMarkerOpacity: 0.3,
        cursorColour: "#2f6b3a",
        selectedGlowColour: "#5ef1e3",
        selectedGlowOpacity: 0.6,
      },
      fontStyle: FONT,
      startHats: true,
    }),
    dark: Blockly.Theme.defineTheme(THEME_NAMES.dark, {
      name: THEME_NAMES.dark,
      base: Blockly.Themes.Classic,
      blockStyles: blockStyles(),
      categoryStyles: categoryStyles(),
      componentStyles: {
        workspaceBackgroundColour: "#161a2e",
        toolboxBackgroundColour: "#1b2038",
        toolboxForegroundColour: "#f4ecd6",
        flyoutBackgroundColour: "#222842",
        flyoutForegroundColour: "#f4ecd6",
        flyoutOpacity: 1,
        scrollbarColour: "#3d4566",
        scrollbarOpacity: 0.9,
        insertionMarkerColour: "#f4ecd6",
        insertionMarkerOpacity: 0.3,
        cursorColour: "#9bd35a",
        selectedGlowColour: "#5ef1e3",
        selectedGlowOpacity: 0.6,
      },
      fontStyle: FONT,
      startHats: true,
    }),
  };
  return themes[mode];
}

// ------------------------------------------------------------------ square-cornered renderer
export const RENDERER = "hibiscus";

class HibiscusConstants extends Blockly.blockRendering.ConstantProvider {
  constructor() {
    super();
    this.CORNER_RADIUS = 0;
  }
}

class HibiscusRenderer extends Blockly.thrasos.Renderer {
  protected override makeConstants_(): Blockly.blockRendering.ConstantProvider {
    return new HibiscusConstants();
  }
}

let rendererRegistered = false;
export function registerRenderer(): void {
  if (rendererRegistered) return;
  rendererRegistered = true;
  Blockly.blockRendering.register(RENDERER, HibiscusRenderer);
}
