/**
 * The toolbox: exactly the six categories of station-programs.md §5 (Motion, AI, Control,
 * Conditions, Data, Output), filled from the block catalogue. The start block sits at the top of
 * Control; the operator blocks (button, key, ask) are §4 condition sources and sit in Conditions.
 * Default inputs are real blocks, not shadows, so the saved JSON has one shape for the compiler.
 */
import type { BlockCatalog, BlockSpec } from "../../api/types";
import { TOOLBOX_CATEGORIES, type ToolboxCategory } from "./theme";

export const VARIABLES_CALLBACK = "HB_VARIABLES";

export function categoryOf(spec: BlockSpec): ToolboxCategory {
  if (spec.category === "start") return "control";
  if (spec.category === "operator") return "conditions";
  return spec.category;
}

const num = (n: number) => ({ block: { type: "math_number", fields: { NUM: n } } });
const txt = (s: string) => ({ block: { type: "text", fields: { TEXT: s } } });

/** Starting inputs and mutator state for blocks dragged out of the toolbox. */
const PRESETS: Record<string, Record<string, unknown>> = {
  controls_if: {},
  controls_repeat_ext: { inputs: { TIMES: num(3) } },
  hb_wait: { inputs: { SECONDS: num(1) } },
  hb_log: { inputs: { TEXT: txt("") } },
  hb_notify: { inputs: { TEXT: txt("") } },
  hb_set_signal: { inputs: { VALUE: txt("") } },
  math_arithmetic: { inputs: { A: num(1), B: num(1) } },
  math_modulo: { inputs: { DIVIDEND: num(10), DIVISOR: num(3) } },
  math_random_int: { inputs: { FROM: num(1), TO: num(10) } },
  logic_compare: { inputs: { B: num(0) } },
  text_join: { extraState: { itemCount: 2 } },
};

/** Extra toolbox entries for one block type (e.g. an if/else preset next to the plain if). */
const VARIANTS: Record<string, Record<string, unknown>[]> = {
  controls_if: [{ extraState: { hasElse: true } }],
};

export interface ToolboxLabels {
  category: (c: ToolboxCategory) => string;
}

type ToolboxItem = Record<string, unknown>;

export function buildToolbox(catalog: BlockCatalog, labels: ToolboxLabels): ToolboxItem {
  const byCat = new Map<ToolboxCategory, BlockSpec[]>();
  for (const spec of catalog.blocks) {
    const c = categoryOf(spec);
    byCat.set(c, [...(byCat.get(c) ?? []), spec]);
  }
  const contents = TOOLBOX_CATEGORIES.map((c): ToolboxItem => {
    const specs = byCat.get(c) ?? [];
    const base = {
      kind: "category",
      name: labels.category(c),
      categorystyle: `hb_${c}_category`,
      toolboxitemid: c,
    };
    if (c === "data") {
      // Variables come from a callback (typed create buttons + one set of blocks per variable).
      return {
        ...base,
        custom: VARIABLES_CALLBACK,
      };
    }
    return {
      ...base,
      contents: specs.flatMap((s) => [
        { kind: "block", type: s.type, ...(PRESETS[s.type] ?? {}) },
        ...(VARIANTS[s.type] ?? []).map((v) => ({ kind: "block", type: s.type, ...v })),
      ]),
    };
  });
  return { kind: "categoryToolbox", contents };
}

/** Data blocks that do not depend on a variable (shown under the variable section). */
export function dataBlocks(catalog: BlockCatalog): ToolboxItem[] {
  return catalog.blocks
    .filter((s) => categoryOf(s) === "data" && !s.type.startsWith("variables_") && s.type !== "math_change")
    .map((s) => ({ kind: "block", type: s.type, ...(PRESETS[s.type] ?? {}) }));
}

export interface VariableInfo {
  id: string;
  name: string;
  type: string;
}

/** Flyout of the Data category: two create buttons, then set / change / get per variable. */
export function variablesFlyout(
  catalog: BlockCatalog,
  vars: VariableInfo[],
  labels: { newNumber: string; newText: string },
): ToolboxItem[] {
  const items: ToolboxItem[] = [
    { kind: "button", text: labels.newNumber, callbackkey: "hb_new_number" },
    { kind: "button", text: labels.newText, callbackkey: "hb_new_text" },
  ];
  const sorted = [...vars].sort((a, b) => a.name.localeCompare(b.name));
  const first = sorted[0];
  if (first) {
    const ref = (v: VariableInfo) => ({ VAR: { id: v.id } });
    items.push({
      kind: "block",
      type: "variables_set",
      fields: ref(first),
      inputs: { VALUE: first.type === "String" ? txt("") : num(0) },
    });
    const firstNumber = sorted.find((v) => v.type !== "String");
    if (firstNumber)
      items.push({ kind: "block", type: "math_change", fields: ref(firstNumber), inputs: { DELTA: num(1) } });
    for (const v of sorted) items.push({ kind: "block", type: "variables_get", fields: ref(v) });
  }
  items.push({ kind: "sep", gap: 24 }, ...dataBlocks(catalog));
  return items;
}
