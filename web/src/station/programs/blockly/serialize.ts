/**
 * Pure helpers around the Blockly workspace JSON (`Blockly.serialization.workspaces.save()`), the
 * document `PUT /programs/{id}` stores as `ProgramInput.editor` (station-programs.md §12.4). Nothing
 * here imports Blockly, so the program screen and the mock station can use them without loading
 * the editor chunk.
 */
import type { BlockCatalog, BlockSpec } from "../../api/types";

export type Json = null | boolean | number | string | Json[] | { [k: string]: Json };
export type JsonObject = Record<string, Json>;

/** One serialized block (`blocks.blocks[i]`, or `inputs.X.block`, or `next.block`). */
export interface SBlock {
  type: string;
  id: string;
  x?: number;
  y?: number;
  fields?: Record<string, Json>;
  inputs?: Record<string, { block?: SBlock; shadow?: SBlock }>;
  next?: { block?: SBlock; shadow?: SBlock };
  extraState?: JsonObject;
  [k: string]: unknown;
}

export interface SVariable {
  name: string;
  id: string;
  type?: string;
}

export interface EditorDoc {
  blocks?: { languageVersion?: number; blocks?: SBlock[] };
  variables?: SVariable[];
  [k: string]: unknown;
}

export const START_BLOCK = "hb_start";

/** A new program: just the single `hb_start` block (§12.4: exactly one start block). */
export function emptyProgram(): EditorDoc {
  return {
    blocks: { languageVersion: 0, blocks: [{ type: START_BLOCK, id: "start", x: 40, y: 40 }] },
    variables: [],
  };
}

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** Narrow an `editor` object from the API (typed `{[k: string]: unknown}`) to the document shape. */
export function asEditorDoc(v: unknown): EditorDoc {
  if (!isObj(v)) return emptyProgram();
  const blocks = v.blocks;
  if (blocks !== undefined && (!isObj(blocks) || !Array.isArray(blocks.blocks ?? []))) return emptyProgram();
  return v;
}

/** Depth-first walk over every block (top-level stacks, inputs, next), real blocks before shadows. */
export function* walkBlocks(doc: EditorDoc): Generator<SBlock> {
  const stack: SBlock[] = [...(doc.blocks?.blocks ?? [])].reverse();
  while (stack.length) {
    const b = stack.pop();
    if (!b) continue;
    yield b;
    const kids: SBlock[] = [];
    for (const inp of Object.values(b.inputs ?? {})) {
      if (inp.block) kids.push(inp.block);
      else if (inp.shadow) kids.push(inp.shadow);
    }
    if (b.next?.block) kids.push(b.next.block);
    stack.push(...kids.reverse());
  }
}

export function countBlocks(doc: EditorDoc): number {
  return [...walkBlocks(doc)].length;
}

/** Block ids in the document (to drop a stale highlight or issue that names a deleted block). */
export function blockIds(doc: EditorDoc): Set<string> {
  return new Set([...walkBlocks(doc)].map((b) => b.id));
}

export function startBlocks(doc: EditorDoc): SBlock[] {
  return (doc.blocks?.blocks ?? []).filter((b) => b.type === START_BLOCK);
}

/** Field kinds whose value is the id of something stored on the Station. */
export const REF_KINDS = [
  "trajectory",
  "pose",
  "detector",
  "label",
  "camera",
  "model",
  "button",
  "signal",
  "joint",
  "motor",
  "key",
] as const;
export type RefKind = (typeof REF_KINDS)[number];

export function isRefKind(kind: string): kind is RefKind {
  return (REF_KINDS as readonly string[]).includes(kind);
}

export function specIndex(catalog: BlockCatalog): Map<string, BlockSpec> {
  return new Map(catalog.blocks.map((b) => [b.type, b]));
}

/**
 * Every referenced value per field kind ("trajectory" → ids...). The editor adds them to its
 * dropdowns before loading, so a program that names a deleted trajectory still opens (the
 * compiler then reports `unknown_trajectory` on that block).
 */
export function referencedValues(doc: EditorDoc, catalog: BlockCatalog): Map<RefKind, Set<string>> {
  const specs = specIndex(catalog);
  const out = new Map<RefKind, Set<string>>();
  for (const b of walkBlocks(doc)) {
    const spec = specs.get(b.type);
    if (!spec) continue;
    for (const f of spec.fields) {
      const v = b.fields?.[f.name];
      if (!isRefKind(f.kind) || typeof v !== "string" || v === "") continue;
      const set = out.get(f.kind) ?? new Set<string>();
      set.add(v);
      out.set(f.kind, set);
    }
  }
  return out;
}

/** Block types the document uses that the catalogue does not know (an older/newer Station). */
export function unknownTypes(doc: EditorDoc, catalog: BlockCatalog): string[] {
  const specs = specIndex(catalog);
  return [...new Set([...walkBlocks(doc)].map((b) => b.type).filter((t) => !specs.has(t)))];
}

const ID_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/;

/** A program / detector id from a display name (same rule as `ITEM_ID_RE` on the Station). */
export function slugify(name: string): string {
  const s = name
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "d")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 64);
  if (ID_RE.test(s)) return s;
  // A name with no Latin letter or digit (日本語, Русский, emoji…) still gets a valid, stable id.
  const trimmed = name.trim();
  return trimmed ? `program_${hash36(trimmed)}` : "";
}

/** FNV-1a 32-bit of the name, base 36: the same name always gives the same fallback id. */
function hash36(text: string): string {
  let h = 0x811c9dc5;
  for (const ch of text) {
    h ^= ch.codePointAt(0) ?? 0;
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(36);
}

export function isItemId(id: string): boolean {
  return ID_RE.test(id);
}

/** Stable JSON text (sorted keys) to tell whether the editor document changed since the last save. */
export function stableJson(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(stableJson).join(",")}]`;
  if (isObj(v))
    return `{${Object.keys(v)
      .sort()
      .filter((k) => v[k] !== undefined)
      .map((k) => `${JSON.stringify(k)}:${stableJson(v[k])}`)
      .join(",")}}`;
  return v === undefined ? "null" : JSON.stringify(v);
}
