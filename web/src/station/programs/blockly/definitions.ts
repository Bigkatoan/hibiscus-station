/**
 * Hibiscus block definitions, generated from the Station's block catalogue (`GET /programs/blocks`,
 * normative, station-programs.md §12.4). Built-in Blockly blocks (`controls_if`, `logic_compare`,
 * `math_*`, `text*`, `variables_*`) keep Blockly's own definitions from `blockly/blocks`; every
 * `hb_*` block is defined here with exactly the catalogue's field and input names.
 *
 * Labels come from the station i18n bundle: `programs.blocks.<type>` is a Blockly message whose
 * `%1..%n` are the block's fields and value/condition inputs in catalogue order; every statement
 * input gets its own row labelled `programs.inputs.<NAME>`.
 */
import * as Blockly from "blockly/core";
import { GLYPHS, type GlyphName } from "@/hibiscus/glyphs.gen";
import type { BlockCatalog, BlockSpec } from "../../api/types";
import { refOptions } from "./refs";
import { isRefKind, type RefKind } from "./serialize";

type Field = BlockSpec["fields"][number];
type Input = BlockSpec["inputs"][number];
export type Translate = (key: string, fallback: string) => string;

export const CATEGORY_STYLE: Record<BlockSpec["category"], string> = {
  start: "hb_start_blocks",
  motion: "hb_motion_blocks",
  ai: "hb_ai_blocks",
  control: "hb_control_blocks",
  conditions: "hb_conditions_blocks",
  operator: "hb_operator_blocks",
  data: "hb_data_blocks",
  output: "hb_output_blocks",
};

const CATEGORY_GLYPH: Record<BlockSpec["category"], GlyphName> = {
  start: "play",
  motion: "robot",
  ai: "chip",
  control: "refresh",
  conditions: "eye",
  operator: "keyboard",
  data: "box",
  output: "chat",
};

/** An 8×8 Hibiscus glyph as an SVG data URI (drawn at 16 px: one art pixel = 2 CSS px). */
export function glyphUri(name: GlyphName, colour = "#fff6dc"): string {
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8" width="16" height="16" shape-rendering="crispEdges">` +
    `<path fill="${colour}" d="${GLYPHS[name]}"/></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

// ------------------------------------------------------------------ reference dropdown field
interface RefFieldJson extends Blockly.FieldDropdownFromJsonConfig {
  refKind: RefKind;
  optional?: boolean;
}

/**
 * A dropdown whose options come from the live Station lists (`refs.ts`). It accepts any string
 * value (a deleted trajectory stays selected and shows as "id ?") and never caches its options.
 */
export class FieldRef extends Blockly.FieldDropdown {
  constructor(
    readonly refKind: RefKind,
    readonly optional = false,
  ) {
    super(function (this: Blockly.FieldDropdown) {
      const block = this.getSourceBlock();
      const det: unknown = refKind === "label" ? block?.getFieldValue("DETECTOR") : null;
      return refOptions(refKind, {
        optional,
        detector: typeof det === "string" ? det : null,
        value: this.getValue(),
      });
    });
  }

  override getOptions(): Blockly.MenuOption[] {
    return super.getOptions(false);
  }

  /**
   * A required detector label starts on the detector's first label. The menu is built before the
   * block's DETECTOR field exists, so a fresh "camera sees" block (toolbox, flyout) otherwise showed
   * "(none yet)" although the detector has labels.
   */
  override initModel(): void {
    super.initModel();
    if (this.refKind !== "label" || this.optional || this.getValue()) return;
    const first = this.getOptions().find((o) => typeof o[1] === "string" && o[1] !== "");
    if (first) this.setValue(first[1]);
  }

  protected override doClassValidation_(newValue?: string): string | null {
    return typeof newValue === "string" ? newValue : null;
  }

  static override fromJson(options: Blockly.FieldDropdownFromJsonConfig): FieldRef {
    const o = options as RefFieldJson;
    return new FieldRef(o.refKind, Boolean(o.optional));
  }
}

let fieldRegistered = false;
function registerField(): void {
  if (fieldRegistered) return;
  fieldRegistered = true;
  Blockly.fieldRegistry.register("field_hb_ref", FieldRef);
}

// ------------------------------------------------------------------ catalogue → Blockly JSON
function fieldArg(f: Field, tr: Translate, blockType: string): Record<string, unknown> {
  switch (f.kind) {
    case "number":
      // An optional number without a default (ask TIMEOUT) is a text field: empty = none.
      if (f.optional && (f.default === null || f.default === undefined))
        return { type: "field_input", name: f.name, text: "" };
      return {
        type: "field_number",
        name: f.name,
        value: typeof f.default === "number" ? f.default : (f.min ?? 0) > 0 ? f.min : 0,
        ...(f.min !== null && f.min !== undefined ? { min: f.min } : {}),
        ...(f.max !== null && f.max !== undefined ? { max: f.max } : {}),
      };
    case "text":
    case "signal":
      return { type: "field_input", name: f.name, text: typeof f.default === "string" ? f.default : "" };
    case "checkbox":
      return { type: "field_checkbox", name: f.name, checked: f.default === true };
    case "dropdown":
      return {
        type: "field_dropdown",
        name: f.name,
        options: (f.options ?? []).map((v) => [tr(`programs.options.${blockType}.${f.name}.${v}`, v), v]),
      };
    case "variable":
      return {
        type: "field_variable",
        name: f.name,
        variable: tr("programs.editor.answer_var", "answer"),
        variableTypes: ["String"],
        defaultType: "String",
      };
    default:
      if (isRefKind(f.kind))
        return { type: "field_hb_ref", name: f.name, refKind: f.kind, optional: f.optional };
      return { type: "field_input", name: f.name, text: "" };
  }
}

function inputArg(i: Input): Record<string, unknown> {
  if (i.kind === "statement") return { type: "input_statement", name: i.name };
  const check =
    i.kind === "condition"
      ? "Boolean"
      : i.check === "number"
        ? "Number"
        : i.check === "text"
          ? "String"
          : null;
  return { type: "input_value", name: i.name, ...(check ? { check } : {}) };
}

const OUTPUT: Record<string, string | null> = { number: "Number", text: "String", boolean: "Boolean" };

/** Placeholders `%1..%n` that are not in the message are appended, so a short translation still works. */
function withArgs(message: string, n: number): string {
  let m = message;
  for (let i = 1; i <= n; i += 1) if (!m.includes(`%${i}`)) m += ` %${i}`;
  return m;
}

/** The Blockly JSON definition of one `hb_*` block. */
export function blockJson(spec: BlockSpec, tr: Translate): Record<string, unknown> {
  const inline = spec.inputs.filter((i) => i.kind !== "statement");
  const statements = spec.inputs.filter((i) => i.kind === "statement");
  const args0 = [
    { type: "field_image", src: glyphUri(CATEGORY_GLYPH[spec.category]), width: 16, height: 16, alt: "" },
    ...spec.fields.map((f) => fieldArg(f, tr, spec.type)),
    ...inline.map(inputArg),
  ];
  const json: Record<string, unknown> = {
    type: spec.type,
    message0: `%1 ${withArgs(tr(`programs.blocks.${spec.type}`, spec.type), args0.length - 1).replace(/%(\d+)/g, (_, d: string) => `%${Number(d) + 1}`)}`,
    args0,
    style: CATEGORY_STYLE[spec.category],
    tooltip: tr(`programs.tooltips.${spec.type}`, ""),
    inputsInline: inline.length > 0 && inline.length <= 2,
  };
  statements.forEach((s, k) => {
    json[`message${k + 1}`] = `${tr(`programs.inputs.${s.name}`, s.name.toLowerCase())} %1`;
    json[`args${k + 1}`] = [inputArg(s)];
  });
  if (spec.output === "statement") {
    json.previousStatement = null;
    json.nextStatement = null;
  } else if (spec.output === "hat") {
    json.hat = "cap";
  } else {
    json.output = OUTPUT[spec.output] ?? null;
  }
  return json;
}

/**
 * (Re)defines every `hb_*` block of the catalogue in the current language. Built-in types in the
 * catalogue must already exist (`blockly/blocks`); a missing one is returned so the screen can say
 * that this Station needs a newer editor.
 */
export function defineCatalog(catalog: BlockCatalog, tr: Translate): string[] {
  registerField();
  const missing: string[] = [];
  for (const spec of catalog.blocks) {
    if (!spec.type.startsWith("hb_")) {
      if (!(spec.type in Blockly.Blocks)) missing.push(spec.type);
      continue;
    }
    const json = blockJson(spec, tr);
    Blockly.Blocks[spec.type] = {
      init(this: Blockly.Block) {
        this.jsonInit(json);
      },
    };
  }
  return missing;
}
