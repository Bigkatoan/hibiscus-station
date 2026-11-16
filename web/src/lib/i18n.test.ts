/**
 * Shared i18n resources (src/i18n/{vi,en}/translation.json: the default namespace used by the
 * shared components in src/components): valid JSON without duplicate keys, same key set in vi and
 * en (modulo each language's CLDR plural categories), identical interpolation tokens, no empty
 * strings, Vietnamese actually translated, and every static key used in the shared code exists.
 * The Station's own strings ("station" namespace) are checked by station/station.unit.test.ts.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import en from "@/i18n/en/translation.json";
import vi from "@/i18n/vi/translation.json";

type Tree = { [k: string]: string | Tree };

function entries(tree: Tree, prefix = ""): [string, string][] {
  return Object.entries(tree).flatMap(([k, v]): [string, string][] =>
    typeof v === "string" ? [[`${prefix}${k}`, v]] : entries(v, `${prefix}${k}.`),
  );
}

const enMap = new Map(entries(en));
const viMap = new Map(entries(vi));
const enKeys = new Set(enMap.keys());
const viKeys = new Set(viMap.keys());

const PLURAL_RE = /_(zero|one|two|few|many|other)$/;
/** Keys a locale must have, given en's keys: plural forms follow that language's CLDR categories. */
function expectedKeys(lng: string): Set<string> {
  const cats = new Set(new Intl.PluralRules(lng).resolvedOptions().pluralCategories);
  const out = new Set<string>();
  for (const k of enKeys) {
    const m = PLURAL_RE.exec(k);
    if (!m) out.add(k);
    else for (const c of cats) out.add(k.replace(PLURAL_RE, `_${c}`));
  }
  return out;
}

const tokens = (s: string): string[] =>
  [...s.matchAll(/\{\{\s*([^}]+?)\s*\}\}/g)].map((m) => m[1] ?? "").sort();
const tags = (s: string): string[] => [...s.matchAll(/<\/?([a-zA-Z0-9]+)\s*\/?>/g)].map((m) => m[0]).sort();

/**
 * Strings that may legitimately be identical in vi and en: product names and the ML/domain terms
 * the glossary keeps in English (docs/ux/copy-deck.md §2). A value is exempt when nothing but
 * these terms, interpolation tokens, digits and punctuation remain.
 */
const SAME_IN_VI = [
  "Hibiscus",
  "LeRobot",
  "Hugging Face",
  "Cloudflare Email Service",
  "Amazon SES",
  "SMTP",
  "Resend",
  "Discord",
  "Telegram",
  "Webhook",
  "Email",
  "ONNX",
  "GPU",
  "FPS",
  "2FA",
  "Camera",
  "Dataset",
  "Episode",
  "Feature",
  "Learning rate",
  "Loss",
  "Mixed precision",
  "Model",
  "Policy",
  "Preset",
  "Seed",
  "Version",
  "Workspace",
];
function exempt(value: string): boolean {
  let rest = value.replace(/\{\{[^}]+\}\}/g, "");
  for (const term of SAME_IN_VI) rest = rest.split(term).join("");
  return /^[\s\d()/·.,:%+-]*$/.test(rest);
}

/** JSON.parse silently keeps the last of two equal keys; walk the text and reject duplicates. */
function duplicateKeys(text: string): string[] {
  const dups: string[] = [];
  const stack: Set<string>[] = [];
  const re = /"((?:[^"\\]|\\.)*)"\s*(:)?|[{}]/g;
  for (const m of text.matchAll(re)) {
    if (m[0] === "{") stack.push(new Set());
    else if (m[0] === "}") stack.pop();
    else if (m[2]) {
      const seen = stack[stack.length - 1];
      const key = m[1] ?? "";
      if (seen?.has(key)) dups.push(key);
      seen?.add(key);
    }
  }
  return dups;
}

function has(key: string): boolean {
  return enKeys.has(key) || enKeys.has(`${key}_one`) || enKeys.has(`${key}_other`);
}

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    // station/ uses its own "station" namespace, checked by station/station.unit.test.ts.
    if (statSync(p).isDirectory()) return f === "generated" || f === "test" || f === "station" ? [] : walk(p);
    return /\.(ts|tsx)$/.test(f) && !f.includes(".test.") ? [p] : [];
  });
}

const srcDir = resolve(__dirname, "..");

describe("i18n resources", () => {
  it.each(["en", "vi"])("%s/translation.json is UTF-8 JSON without duplicate keys", (lng) => {
    const raw = readFileSync(resolve(srcDir, `i18n/${lng}/translation.json`));
    expect(raw.subarray(0, 3).equals(Buffer.from([0xef, 0xbb, 0xbf]))).toBe(false);
    const text = raw.toString("utf8");
    expect(() => JSON.parse(text) as unknown).not.toThrow();
    expect(duplicateKeys(text)).toEqual([]);
  });

  it("vi has exactly en's keys (plural forms per CLDR: vi uses _other only)", () => {
    const want = expectedKeys("vi");
    expect([...want].filter((k) => !viKeys.has(k))).toEqual([]);
    expect([...viKeys].filter((k) => !want.has(k))).toEqual([]);
    expect([...expectedKeys("en")].filter((k) => !enKeys.has(k))).toEqual([]);
  });

  it("no empty strings", () => {
    const empty = [...enMap, ...viMap].filter(([, v]) => v.trim() === "").map(([k]) => k);
    expect(empty).toEqual([]);
  });

  it("vi and en use identical interpolation tokens and tags per key", () => {
    const bad: string[] = [];
    for (const [k, v] of viMap) {
      const e = enMap.get(k) ?? enMap.get(k.replace(PLURAL_RE, "_other")) ?? "";
      if (tokens(v).join() !== tokens(e).join() || tags(v).join() !== tags(e).join()) bad.push(k);
    }
    expect(bad).toEqual([]);
  });

  it("at least 97% of Vietnamese strings are translated (glossary terms exempt)", () => {
    const same = [...viMap].filter(([k, v]) => enMap.get(k) === v);
    const untranslated = same.filter(([, v]) => !exempt(v)).map(([k]) => k);
    const translated = 1 - untranslated.length / viMap.size;
    expect(
      translated,
      `untranslated (${untranslated.length}): ${untranslated.slice(0, 40).join(", ")}`,
    ).toBeGreaterThanOrEqual(0.97);
  });

  it("every static t('…') key used in src exists", () => {
    const missing: string[] = [];
    for (const file of walk(srcDir)) {
      const text = readFileSync(file, "utf8");
      for (const m of text.matchAll(/\bt\(\s*"([a-zA-Z0-9_.-]+)"/g)) {
        const key = m[1] ?? "";
        if (!has(key)) missing.push(`${file.replace(srcDir, "src")}: ${key}`);
      }
      for (const m of text.matchAll(/"(validation\.[a-z_]+)"/g)) {
        if (!has(m[1] ?? "")) missing.push(`${file}: ${m[1] ?? ""}`);
      }
    }
    expect(missing).toEqual([]);
  });
});
