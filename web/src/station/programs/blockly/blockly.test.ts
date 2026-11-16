/**
 * Editor serialization (station-programs.md §12.4): the block definitions follow the Station's
 * catalogue exactly (types, field and input names), the saved workspace JSON round-trips, typed
 * variables serialize with their type, and the toolbox is exactly the six §5 categories.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import * as Blockly from "blockly/core";
import "blockly/blocks";
import * as En from "blockly/msg/en";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import en from "../../i18n/en.json";
import vi from "../../i18n/vi.json";
import { CATALOG, sampleProgramDoc } from "../../mock/programs";
import { blockJson, defineCatalog, FieldRef, glyphUri } from "./definitions";
import { emptyRefs, refOptions, setEditorRefs } from "./refs";
import {
  asEditorDoc,
  blockIds,
  countBlocks,
  emptyProgram,
  referencedValues,
  slugify,
  stableJson,
  startBlocks,
  unknownTypes,
  type EditorDoc,
} from "./serialize";
import { BLOCK_COLOURS, hibiscusTheme, shade } from "./theme";
import { buildToolbox, categoryOf, variablesFlyout } from "./toolbox";

const tr = (key: string, fallback: string): string => {
  const v = key.split(".").reduce<unknown>((o, k) => (o as Record<string, unknown> | undefined)?.[k], en);
  return typeof v === "string" ? v : fallback;
};

let ws: Blockly.Workspace;

beforeAll(() => {
  Blockly.setLocale(En as unknown as Record<string, string>);
  expect(defineCatalog(CATALOG, tr)).toEqual([]);
});

afterEach(() => {
  ws.dispose();
});

function load(doc: EditorDoc): Blockly.Workspace {
  ws = new Blockly.Workspace();
  Blockly.serialization.workspaces.load(doc, ws);
  return ws;
}

describe("block definitions from the catalogue", () => {
  it("defines every catalogue block with exactly its field and input names", () => {
    ws = new Blockly.Workspace();
    for (const spec of CATALOG.blocks) {
      const b = ws.newBlock(spec.type);
      for (const f of spec.fields) expect(b.getField(f.name), `${spec.type}.${f.name}`).not.toBeNull();
      for (const i of spec.inputs) {
        const name = i.repeated ? `${i.name}0` : i.name;
        if (spec.type === "controls_if" && i.name === "ELSE") continue; // added by the mutator
        expect(b.getInput(name), `${spec.type}.${name}`).not.toBeNull();
      }
      if (spec.output === "statement") {
        expect(b.previousConnection, spec.type).not.toBeNull();
        expect(b.outputConnection, spec.type).toBeNull();
      } else if (spec.output === "hat") {
        expect(b.previousConnection).toBeNull();
        expect(b.nextConnection).toBeNull();
      } else {
        expect(b.outputConnection, spec.type).not.toBeNull();
      }
    }
  });

  it("types value inputs and outputs so a condition only fits a condition slot", () => {
    const wait = blockJson(
      CATALOG.blocks.find((b) => b.type === "hb_wait_until")!,
      tr,
    );
    expect(JSON.stringify(wait)).toContain('"check":"Boolean"');
    const sees = blockJson(
      CATALOG.blocks.find((b) => b.type === "hb_camera_sees")!,
      tr,
    );
    expect(sees.output).toBe("Boolean");
    const conf = blockJson(
      CATALOG.blocks.find((b) => b.type === "hb_detector_confidence")!,
      tr,
    );
    expect(conf.output).toBe("Number");
    const start = blockJson(
      CATALOG.blocks.find((b) => b.type === "hb_start")!,
      tr,
    );
    expect(start.hat).toBe("cap");
    expect(start.message1).toBe("do %1");
  });

  it("puts a 16 px Hibiscus glyph in front of every label and shifts the placeholders", () => {
    const play = blockJson(
      CATALOG.blocks.find((b) => b.type === "hb_play_trajectory")!,
      tr,
    );
    expect(play.message0).toBe("%1 play trajectory %2 at %3 %");
    const args = play.args0 as { type: string; src?: string; width?: number }[];
    expect(args[0]).toMatchObject({ type: "field_image", width: 16 });
    expect(args[0]?.src).toMatch(/^data:image\/svg\+xml,/);
    expect(decodeURIComponent(glyphUri("robot"))).toContain('shape-rendering="crispEdges"');
  });

  it("appends placeholders a translation forgot, so a block never loses a field", () => {
    const json = blockJson(
      CATALOG.blocks.find((b) => b.type === "hb_play_trajectory")!,
      () => "play",
    );
    expect(json.message0).toBe("%1 play %2 %3");
  });

  it("uses a text field for an optional number without default (empty = none)", () => {
    const ask = blockJson(
      CATALOG.blocks.find((b) => b.type === "hb_ask_operator")!,
      tr,
    );
    const timeout = (ask.args0 as { name?: string; type: string }[]).find((a) => a.name === "TIMEOUT");
    expect(timeout?.type).toBe("field_input");
  });
});

describe("workspace JSON", () => {
  it("round-trips the A/B sample program: same block ids, types and fields", () => {
    const doc = sampleProgramDoc("t_20261116_101500_a1b2", "t_20261116_101800_c3d4");
    load(doc);
    const saved = Blockly.serialization.workspaces.save(ws) as EditorDoc;
    expect([...blockIds(saved)].sort()).toEqual([...blockIds(doc)].sort());
    const play = [...ws.getAllBlocks(false)].find((b) => b.id === "play_a");
    expect(play?.getFieldValue("TRAJECTORY")).toBe("t_20261116_101500_a1b2");
    expect(play?.getFieldValue("SPEED")).toBe(100);
    const ifBlock = ws.getBlockById("if_ab");
    expect(ifBlock?.getInput("IF1")).not.toBeNull();
    expect(startBlocks(saved)).toHaveLength(1);
    expect(countBlocks(saved)).toBe(countBlocks(doc));
  });

  it("keeps a reference to a deleted trajectory (shown as missing) instead of dropping it", () => {
    setEditorRefs({ ...emptyRefs(), text: { ...emptyRefs().text, missing: "(missing)" } });
    load(sampleProgramDoc("t_20990101_000000_dead", "t_20990101_000000_beef"));
    const field = ws.getBlockById("play_a")?.getField("TRAJECTORY");
    expect(field).toBeInstanceOf(FieldRef);
    expect(field?.getValue()).toBe("t_20990101_000000_dead");
    expect((field as FieldRef).getOptions()).toContainEqual([
      "t_20990101_000000_dead (missing)",
      "t_20990101_000000_dead",
    ]);
  });

  it("serializes typed variables (Number / String) as the compiler expects", () => {
    ws = new Blockly.Workspace();
    ws.getVariableMap().createVariable("count", "Number", "v_count");
    ws.getVariableMap().createVariable("answer", "String", "v_answer");
    const set = ws.newBlock("variables_set");
    set.setFieldValue("v_count", "VAR");
    const saved = Blockly.serialization.workspaces.save(ws) as EditorDoc;
    expect(saved.variables).toEqual(
      expect.arrayContaining([
        { name: "count", id: "v_count", type: "Number" },
        { name: "answer", id: "v_answer", type: "String" },
      ]),
    );
    const b = saved.blocks?.blocks?.[0];
    expect(b?.fields?.VAR).toEqual({ id: "v_count" });
  });

  it("collects referenced ids per kind and spots unknown block types", () => {
    const doc = sampleProgramDoc("t_a", "t_b");
    const refs = referencedValues(doc, CATALOG);
    expect([...(refs.get("trajectory") ?? [])].sort()).toEqual(["t_a", "t_b"]);
    expect([...(refs.get("key") ?? [])].sort()).toEqual(["1", "2"]);
    expect([...(refs.get("detector") ?? [])]).toEqual(["cube_color"]);
    expect(unknownTypes(doc, CATALOG)).toEqual([]);
    const bad: EditorDoc = { blocks: { blocks: [{ type: "hb_teleport", id: "x" }] } };
    expect(unknownTypes(bad, CATALOG)).toEqual(["hb_teleport"]);
  });

  it("a new program is exactly one start block; junk editor JSON falls back to it", () => {
    expect(startBlocks(emptyProgram())).toHaveLength(1);
    expect(asEditorDoc(null)).toEqual(emptyProgram());
    expect(asEditorDoc({ blocks: 3 })).toEqual(emptyProgram());
    expect(stableJson({ b: 1, a: [2, { d: 3, c: 4 }] })).toBe('{"a":[2,{"c":4,"d":3}],"b":1}');
  });

  it("makes program ids from Vietnamese names", () => {
    expect(slugify("Phân loại khối Đỏ/Xanh")).toBe("phan_loai_khoi_do_xanh");
    expect(slugify("!!!")).toBe("");
  });
});

describe("reference dropdowns", () => {
  it("labels follow the chosen detector; optional fields offer the default first", () => {
    const refs = {
      ...emptyRefs(),
      detectors: [{ value: "cube_color", label: "Cube colour", labels: ["red", "blue"] }],
      cameras: ["wrist", "front"],
    };
    expect(refOptions("label", { detector: "cube_color", refs })).toEqual([
      ["red", "red"],
      ["blue", "blue"],
    ]);
    expect(refOptions("camera", { optional: true, refs })[0]?.[1]).toBe("");
    expect(refOptions("trajectory", { refs })).toEqual([["-", ""]]);
    expect(refOptions("motor", { refs })[0]).toEqual(["*", "any"]);
    expect(refOptions("key", { refs })).toHaveLength(36);
  });

  it("a new 'camera sees' block starts on the detector's first label; a saved label is kept", () => {
    setEditorRefs({
      ...emptyRefs(),
      detectors: [{ value: "cube_color", label: "Cube colour", labels: ["red", "blue"] }],
    });
    try {
      ws = new Blockly.Workspace();
      const fresh = ws.newBlock("hb_camera_sees");
      fresh.initModel();
      expect(fresh.getFieldValue("DETECTOR")).toBe("cube_color");
      expect(fresh.getFieldValue("LABEL")).toBe("red");
      const saved = Blockly.serialization.blocks.append(
        { type: "hb_camera_sees", fields: { DETECTOR: "cube_color", LABEL: "blue" } },
        ws,
      );
      expect(saved.getFieldValue("LABEL")).toBe("blue");
      // The optional label of a confidence block keeps "best label" (empty) as its default.
      const conf = ws.newBlock("hb_detector_confidence");
      conf.initModel();
      expect(conf.getFieldValue("LABEL")).toBe("");
    } finally {
      setEditorRefs(emptyRefs());
    }
  });
});

describe("toolbox", () => {
  const labels = { category: (c: string) => tr(`programs.toolbox.${c}`, c) };

  it("has exactly the six §5 categories, in order, with translated names", () => {
    const tb = buildToolbox(CATALOG, labels) as { contents: { name: string; toolboxitemid: string }[] };
    expect(tb.contents.map((c) => c.toolboxitemid)).toEqual([
      "motion",
      "ai",
      "control",
      "conditions",
      "data",
      "output",
    ]);
    expect(tb.contents.map((c) => c.name)).toEqual([
      "Motion",
      "AI",
      "Control",
      "Conditions",
      "Data",
      "Output",
    ]);
  });

  it("offers every catalogue block (start in Control, operator blocks in Conditions)", () => {
    const tb = buildToolbox(CATALOG, labels) as {
      contents: { toolboxitemid: string; contents?: { type: string }[] }[];
    };
    const flyout = variablesFlyout(CATALOG, [{ id: "v", name: "n", type: "Number" }], {
      newNumber: "+n",
      newText: "+t",
    });
    const offered = new Set([
      ...tb.contents.flatMap((c) => (c.contents ?? []).map((b) => b.type)),
      ...flyout.filter((i) => i.kind === "block").map((i) => i.type as string),
    ]);
    for (const spec of CATALOG.blocks) expect(offered, spec.type).toContain(spec.type);
    const control = tb.contents.find((c) => c.toolboxitemid === "control");
    expect(control?.contents?.[0]?.type).toBe("hb_start");
    expect(categoryOf(CATALOG.blocks.find((b) => b.type === "hb_key_pressed")!)).toBe("conditions");
  });

  it("default inputs are real blocks, not shadows (one JSON shape for the compiler)", () => {
    expect(JSON.stringify(buildToolbox(CATALOG, labels))).not.toContain("shadow");
  });

  it("the variables flyout has typed create buttons and set/change/get blocks", () => {
    const items = variablesFlyout(
      CATALOG,
      [
        { id: "v1", name: "count", type: "Number" },
        { id: "v2", name: "answer", type: "String" },
      ],
      { newNumber: "New number", newText: "New text" },
    );
    expect(items.slice(0, 2).map((i) => i.callbackkey)).toEqual(["hb_new_number", "hb_new_text"]);
    expect(items.filter((i) => i.type === "variables_get")).toHaveLength(2);
    expect(items.find((i) => i.type === "math_change")?.fields).toEqual({ VAR: { id: "v1" } });
  });
});

describe("Hibiscus theme", () => {
  it("defines light and dark themes with Nunito and the palette block colours", () => {
    const light = hibiscusTheme("light");
    const dark = hibiscusTheme("dark");
    expect(light.fontStyle.family).toMatch(/^Nunito/);
    expect(light.blockStyles.hb_motion_blocks?.colourPrimary).toBe(BLOCK_COLOURS.hb_motion_blocks);
    expect(light.blockStyles.logic_blocks?.colourPrimary).toBe(BLOCK_COLOURS.hb_conditions_blocks);
    expect(light.componentStyles.workspaceBackgroundColour).toBe("#f3dfb2");
    expect(dark.componentStyles.workspaceBackgroundColour).toBe("#161a2e");
    expect(shade("#808080", 0.5)).toBe("#404040");
  });
});

describe("Hibiscus skin (blockly.css)", () => {
  const skin = readFileSync(join(process.cwd(), "src/station/programs/blockly/blockly.css"), "utf8");
  const rule = (selector: string): string => {
    const at = skin.indexOf(`${selector} {`);
    expect(at, selector).toBeGreaterThanOrEqual(0);
    return skin.slice(at, skin.indexOf("}", at));
  };
  it("keeps Blockly's toolbox and flyouts inside the editor's stacking context", () => {
    expect(rule(".hb-blockly")).toMatch(/isolation:\s*isolate/);
  });
  it("hides scrollbars Blockly hid with display=none despite the global svg reset", () => {
    expect(rule('.hb-blockly svg[display="none"]')).toMatch(/display:\s*none/);
  });
  it("outlines the running (highlighted) block in cyan instead of the pale emboss", () => {
    expect(skin).toMatch(/\.hb-blockly \.blocklyHighlighted > \.blocklyPath,[^{]*\{[^}]*stroke: #5ef1e3/);
    expect(rule(".hb-blockly .blocklyHighlighted > .blocklyPath")).toMatch(/filter:\s*none/);
  });
});

describe("block strings", () => {
  const placeholders = (s: string) => new Set([...s.matchAll(/%(\d+)/g)].map((m) => m[1]));
  it("every Hibiscus block has a label in en and vi with all its placeholders", () => {
    for (const spec of CATALOG.blocks.filter((b) => b.type.startsWith("hb_"))) {
      const n = spec.fields.length + spec.inputs.filter((i) => i.kind !== "statement").length;
      for (const bundle of [en, vi]) {
        const msg = (bundle.programs.blocks as Record<string, string>)[spec.type];
        expect(msg, spec.type).toBeTypeOf("string");
        expect(placeholders(msg ?? "").size, spec.type).toBe(n);
      }
    }
  });
});
