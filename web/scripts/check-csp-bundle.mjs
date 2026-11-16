// Fails the production build when the bundle evaluates strings as code, so the Station UI keeps
// working under a `script-src 'self'` Content-Security-Policy without 'unsafe-eval' (a runtime
// schema compiler using `new Function` once crashed the Hibiscus web UI that way).
// Usage: node scripts/check-csp-bundle.mjs [dist/assets]
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const dir = process.argv[2] ?? "dist/assets";
const patterns = [/\bnew Function\s*\(/, /(?<![.\w$])eval\s*\(/, /(?<![.\w$])Function\s*\(\s*["'`]/];
const bad = [];
for (const f of readdirSync(dir)) {
  if (!f.endsWith(".js")) continue;
  const src = readFileSync(join(dir, f), "utf8");
  for (const re of patterns) {
    const m = re.exec(src);
    if (m) bad.push(`${f}: …${src.slice(Math.max(0, m.index - 60), m.index + 60)}…`);
  }
}
if (bad.length) {
  console.error(`CSP check failed: string-to-code evaluation in the bundle:\n${bad.join("\n")}`);
  process.exit(1);
}
console.log(`CSP check: no eval / new Function in ${dir}`);

// uPlot calls `new Intl.NumberFormat(navigator.language)` at module load, which throws on
// tags like `en-US@posix` (LANG=C). The locale-guard chunk must be imported by the entry before
// the charts chunk so the sanitised navigator.language is in place when uPlot evaluates.
const entry = readdirSync(dir).find((f) => /^index-.*\.js$/.test(f));
if (entry) {
  const src = readFileSync(join(dir, entry), "utf8");
  const guard = src.search(/from\s*"\.\/locale-guard-[^"]+\.js"/);
  const charts = src.search(/from\s*"\.\/charts-[^"]+\.js"/);
  if (guard === -1 || (charts !== -1 && charts < guard)) {
    console.error(`Locale guard check failed: ${entry} must import locale-guard before charts.`);
    process.exit(1);
  }
  console.log("Locale guard check: locale-guard is imported before charts");
}
