/**
 * Class sweep after QC 0.2.9 QD-19: no screen prints the Station's own English line (a status
 * `detail`, an arm's calibration `issue`, a locked step's `why`, a Problem or OS `message`) as
 * text. Such a line goes through components/ServerText.tsx: the known wording in the user's
 * language, anything else behind a closed "Technical details".
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = join(process.cwd(), "src/station");

/** Where a raw Station line may be read: the helpers that translate it or hide it. */
const MAY_READ = new Set(["components/ServerText.tsx", "components/StationError.tsx"]);

const FIELD = String.raw`(?:\b\w+\??\.(?:detail|why|issue|message)\b|\blost\??\.error\b|\.error\??\.(?:message|detail)\b|^\s*(?:detail|issue|why)\s*(?:\?\?[^{}]*)?$)`;
/** A JSX child `{…}` (after a tag or another child, not an arrow body) or a `title={…}` reading one. */
const RAW_IN_JSX = new RegExp(String.raw`(?:(?<!=)>|\})\s*\{([^{}]*)\}|title=\{([^{}]*)\}`, "g");
const FIELD_RE = new RegExp(FIELD, "m");

/** Every place in `src` that renders a raw Station line, as "line: code". */
function rawRenders(src: string): string[] {
  const out: string[] = [];
  for (const m of src.matchAll(RAW_IN_JSX)) {
    const expr = m[1] ?? m[2] ?? "";
    if (/^\s*t\(/.test(expr)) continue; // a translated string
    if (FIELD_RE.test(expr)) {
      const line = src.slice(0, m.index).split("\n").length;
      out.push(`${String(line)}: ${m[0].replace(/\s+/g, " ").trim()}`);
    }
  }
  if (/\berrorDetail\(/.test(src)) out.push("errorDetail() outside StationError");
  return out;
}

function tsx(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return f === "test" || f === "mock" ? [] : tsx(p);
    return f.endsWith(".tsx") && !f.includes(".test.") ? [p] : [];
  });
}

describe("no raw Station text on screen (QC 0.2.9 QD-19 class sweep)", () => {
  it("the scanner finds the shapes QC found", () => {
    // Banners.tsx and the wizard rail before the fix
    expect(
      rawRenders(`{status.detail ? <p className="mt-1 font-mono text-xs">{status.detail}</p> : null}`),
    ).toHaveLength(1);
    expect(rawRenders(`<p title={s.why}>\n  {s.why}\n</p>`)).toHaveLength(2);
    expect(rawRenders(`{t("robot.connecting")} {status.detail ?? ""}`)).toHaveLength(1);
    expect(rawRenders(`<span className="font-mono">{issue}</span>`)).toHaveLength(1);
    expect(rawRenders(`{t("lost.os_said")} {lost.error}`)).toHaveLength(1);
    expect(rawRenders(`<p>{mine.message}</p>`)).toHaveLength(1);
    // allowed: a translated line, an error passed to <StationError>, a line passed to the helper
    expect(rawRenders(`<p>{t("lock.estopped")}</p>`)).toEqual([]);
    expect(rawRenders(`<StationError error={start.error ?? save.error} />`)).toEqual([]);
    expect(rawRenders(`<ServerDetail line={status.detail} />`)).toEqual([]);
    expect(rawRenders(`const f = () => {\n  return x.detail;\n};`)).toEqual([]);
  });

  it("no component renders status.detail / error.detail / issue / why / a server message", () => {
    const files = tsx(ROOT);
    expect(files.length).toBeGreaterThan(30);
    const bad: string[] = [];
    for (const file of files) {
      const rel = file.slice(ROOT.length + 1);
      if (MAY_READ.has(rel)) continue;
      for (const hit of rawRenders(readFileSync(file, "utf8"))) bad.push(`${rel}:${hit}`);
    }
    expect(bad).toEqual([]);
  });
});
