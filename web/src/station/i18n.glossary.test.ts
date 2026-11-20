/**
 * vi glossary (QC 0.2.9 QD-22): an English word that has an agreed Vietnamese term never appears
 * in vi.json. Round 4 found "Hãy reset nút dừng khẩn cấp trước." right above the button
 * "Đã an toàn, đặt lại", and "dataset" where every screen says "bộ dữ liệu".
 *
 * The terms are the ones vi.json itself uses for its labels (nav, buttons, headings). Loanwords
 * the UI keeps on purpose (camera, model, token, policy, telemetry, Station, robot, follower,
 * leader, Home, USB, Space, bus) are not listed. A quote of another program's own English UI
 * (Windows settings) is allowed by key.
 */
import { describe, expect, it } from "vitest";
import vi from "./i18n/vi.json";

/** English word (regex, whole word, any case) → the Vietnamese term vi.json uses for it. */
const GLOSSARY: readonly (readonly [RegExp, string])[] = [
  [/\bresets?\b/i, "đặt lại"],
  [/\bdatasets?\b/i, "bộ dữ liệu"],
  [/\bcalibrat(e|es|ed|ing|ion|ions)\b/i, "hiệu chỉnh"],
  [/\bepisodes?\b/i, "tập"],
  [/\buploads?\b/i, "tải lên"],
  [/\bsessions?\b/i, "phiên"],
  [/\bjoints?\b/i, "khớp"],
  [/\btorque\b/i, "mô-men"],
  [/\bteleop(eration)?\b/i, "điều khiển tay"],
  [/\bfiles?\b/i, "tệp"],
  [/\bsettings\b/i, "cài đặt"],
  [/\brecord(ing)?\b/i, "ghi"],
  [/\bstop(ped)?\b/i, "dừng"],
  [/\bHiệu chuẩn\b/i, "Hiệu chỉnh"],
];

/** Keys that quote another program's English UI word for word (the user must find it there). */
const QUOTES = new Set(["lost.check_suspend"]);

function strings(o: unknown, path = ""): [string, string][] {
  if (typeof o === "string") return [[path, o]];
  if (o && typeof o === "object")
    return Object.entries(o).flatMap(([k, v]) => strings(v, path ? `${path}.${k}` : k));
  return [];
}

/** The words a reader sees: placeholders ({{x}}) and tags (<b>) are not text. */
function visible(s: string): string {
  return s.replace(/\{\{[^}]*\}\}/g, " ").replace(/<[^>]*>/g, " ");
}

describe("vi glossary (QD-22)", () => {
  it("no vi string uses an English word that has an agreed Vietnamese term", () => {
    const hits: string[] = [];
    for (const [key, s] of strings(vi)) {
      if (QUOTES.has(key)) continue;
      for (const [word, term] of GLOSSARY) {
        const m = visible(s).match(word);
        if (m) hits.push(`${key}: "${m[0]}" → "${term}" in "${s}"`);
      }
    }
    expect(hits).toEqual([]);
  });

  it("every agreed term is really used in vi.json", () => {
    const all = strings(vi)
      .map(([, s]) => s.toLowerCase())
      .join("\n");
    for (const [, term] of GLOSSARY) {
      if (term === "Hiệu chỉnh") continue;
      expect(all, term).toContain(term.toLowerCase());
    }
  });

  it("the check catches the round-4 strings", () => {
    const flagged = (s: string) => GLOSSARY.some(([w]) => w.test(visible(s)));
    expect(flagged("Hãy reset nút dừng khẩn cấp trước.")).toBe(true);
    expect(flagged("Đã có dataset với tên này.")).toBe(true);
    expect(flagged("Hãy đặt lại nút dừng khẩn cấp trước.")).toBe(false);
    expect(flagged("Tập {{episode}} / {{of}}")).toBe(false);
  });
});
