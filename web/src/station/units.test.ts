/**
 * Class sweep after QC 0.2.9 QD-21: every size, duration and measured number on a Station screen
 * goes through units.ts (decimal kB / MB / GB, the locale's decimal separator), so no screen can
 * print "0.00 GiB" or "1.5" in Vietnamese again.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { i18n } from "@/lib/i18n";
import en from "./i18n/en.json";
import vi from "./i18n/vi.json";
import { fmtFixed, fmtSeconds, fmtSize } from "./units";

const ROOT = join(process.cwd(), "src/station");

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return f === "test" || f === "mock" ? [] : sources(p);
    return /\.tsx?$/.test(f) && !f.includes(".test.") && !f.endsWith(".d.ts") ? [p] : [];
  });
}

afterEach(async () => {
  await i18n.changeLanguage("en");
});

describe("one number formatter for sizes and durations (QC 0.2.9 QD-21 class sweep)", () => {
  it("no screen formats a number by hand (toFixed, / 1024, KiB / MiB / GiB)", () => {
    const bad: string[] = [];
    for (const file of sources(ROOT)) {
      const rel = file.slice(ROOT.length + 1);
      if (rel === "units.ts") continue;
      readFileSync(file, "utf8")
        .split("\n")
        .forEach((line, i) => {
          if (/\.toFixed\(|\/\s*1024\b|\b[KMG]iB\b/.test(line))
            bad.push(`${rel}:${String(i + 1)}: ${line.trim()}`);
        });
    }
    expect(bad).toEqual([]);
  });

  it("no string says KiB / MiB / GiB", () => {
    const strings = JSON.stringify([en, vi]);
    expect(strings).not.toMatch(/\b[KMG]iB\b/);
  });

  it("sizes and seconds read in the user's language", async () => {
    expect(fmtSize(3.4e6)).toBe("3.4 MB");
    expect(fmtSize(4.2e6 * 1)).toBe("4.2 MB");
    expect(fmtSize(1.5e9)).toBe("1.5 GB");
    expect(fmtSeconds(4.46)).toBe("4.5 s");
    expect(fmtSeconds(42.3)).toBe("42 s");
    expect(fmtFixed(12.06)).toBe("12.1");
    await i18n.changeLanguage("vi");
    expect(fmtSize(3.4e6)).toBe("3,4 MB");
    expect(fmtFixed(12.06)).toBe("12,1");
    expect(fmtSeconds(4.46)).toBe("4,5 s");
  });
});
