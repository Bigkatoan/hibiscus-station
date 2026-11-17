/**
 * Every value the server can send has words, in en and vi (QC 0.2.9 QD-14, QD-15).
 *
 * The literal-key test in station.unit.test.ts cannot see keys built at run time, such as
 * t(`session.kind_${s.kind}`). Those showed raw keys ("session.kind_program") or English server
 * words ("stopped") on the Sessions page. This test finds every such template key in the station
 * UI, looks up the set of values that can fill it (from openapi.json enums, or from the Python
 * source where the wire type is a plain string), and checks that each key exists in both locales.
 * A new template key with no declared domain fails here, so it cannot slip through again.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import en from "./i18n/en.json";
import vi from "./i18n/vi.json";

const ROOT = join(process.cwd(), "..");
const SRC = join(process.cwd(), "src/station/");

type Schema = {
  enum?: string[];
  anyOf?: Schema[];
  oneOf?: Schema[];
  items?: Schema;
  properties?: Record<string, Schema>;
};
const openapi = JSON.parse(readFileSync(join(ROOT, "openapi.json"), "utf8")) as {
  components: { schemas: Record<string, Schema> };
};

function enumOf(p: Schema | undefined): string[] {
  if (!p) return [];
  if (p.enum) return p.enum;
  const alts = p.anyOf ?? p.oneOf;
  if (alts) return alts.flatMap(enumOf);
  return enumOf(p.items);
}

/** The enum of `schema.prop` in openapi.json; fails loudly when it is gone. */
function wire(schema: string, prop: string): string[] {
  const values = enumOf(openapi.components.schemas[schema]?.properties?.[prop]);
  if (values.length === 0) throw new Error(`openapi.json has no enum for ${schema}.${prop}`);
  return values;
}

function py(rel: string): string {
  return readFileSync(join(ROOT, rel), "utf8");
}

function pyLiteral(rel: string, name: string): string[] {
  const m = new RegExp(`${name}\\s*=\\s*Literal\\[([^\\]]+)\\]`).exec(py(rel));
  if (!m?.[1]) throw new Error(`${rel}: no Literal ${name}`);
  return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1] ?? "");
}

function pySources(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return pySources(p);
    return f.endsWith(".py") ? [readFileSync(p, "utf8")] : [];
  });
}

const PY = pySources(join(ROOT, "hibiscus_station"));

/** `raise_alert(kind, level, "message.key", …)` and the motor alerts built from a level (hw/telemetry.py). */
const ALERT_KEYS = [
  ...new Set([
    ...PY.flatMap((s) =>
      [...s.matchAll(/raise_alert\(\s*(?:"[^"]*"|[^,()]+),\s*(?:"[^"]*"|[^,()]+),\s*"([a-z_.]+)"/g)].map(
        (m) => m[1] ?? "",
      ),
    ),
    ...["ok", "warn", "hot", "critical"].map((l) => `motor.temp.${l}`),
    ...["ok", "warn", "critical"].flatMap((l) => [`motor.status.${l}`, `motor.voltage.${l}`]),
    ...["ok", "warn"].flatMap((l) => [`motor.current.${l}`, `motor.load.${l}`]),
  ]),
];

/** Session outcomes and e-stop / error reasons: plain strings on the wire. */
const REASONS = [
  ...new Set([
    // e-stop and fault reasons (hw/owner.py press_estop / _fail, safety events)
    "user",
    "thermal",
    "electrical",
    "ui_lost",
    "camera_lost",
    "bus_lost",
    "device_lost",
    "internal",
    "disconnect",
    // session outcomes (sessions/*.py finish(...))
    "running",
    "completed",
    "stopped",
    "error",
    ...wire("ProgramRunSummary", "outcome"),
  ]),
];

const STATUS_BITS = [...py("hibiscus_station/hw/feetech.py").matchAll(/^\s+\d+: "([a-z_]+)",$/gm)].map(
  (m) => m[1] ?? "",
);

const ERROR_CODES = (() => {
  const block = /STATUS = \{([^}]+)\}/.exec(py("hibiscus_station/errors.py"))?.[1] ?? "";
  return [...block.matchAll(/"([a-z_]+)":/g)].map((m) => m[1] ?? "");
})();

/** Model compatibility checks (models/compat.py): check ids ("camera:<key>" reads as "camera") and codes. */
const COMPAT = py("hibiscus_station/models/compat.py");
const COMPAT_IDS = [...new Set([...COMPAT.matchAll(/"id": "([a-z_]+)"/g)].map((m) => m[1] ?? "")), "camera"];
const COMPAT_CODES = [...new Set([...COMPAT.matchAll(/"code": "([a-z_]+)"/g)].map((m) => m[1] ?? ""))];

/**
 * Template-key prefix → the values that can fill it. `ui` marks a value set defined by the UI
 * itself (a typed TS union in the same file), which tsc already keeps in step.
 */
const DOMAINS: Record<string, string[] | "ui"> = {
  "session.kind_": wire("SessionSummary", "kind"),
  "cameras.type_": wire("DiscoveredCamera", "type"),
  "reasons.": REASONS,
  "jobs.kind_": wire("Job", "kind"),
  "jobs.status_": wire("Job", "status"),
  "jobs.phase_": wire("JobProgress", "phase"),
  "programs.status.": wire("ProgramState", "status"),
  "programs.log_kind.": wire("ProgramLogLine", "kind"),
  "programs.motion.": [...pyLiteral("hibiscus_station/programs/interfaces.py", "MotionOutcome"), "start"],
  "programs.run.waiting_": wire("WaitInfo", "kind"),
  "programs.traj.status_": wire("TrajectorySummary", "status"),
  "programs.poses.source_": wire("Pose", "source"),
  "programs.issues.": wire("CheckIssue", "code"),
  "run.source_": wire("ModelEntry", "source"),
  "device.": wire("LoadRequest", "device"),
  "robot.role_": ["follower", "leader"],
  "arm.": ["follower", "leader"],
  "alerts.kind_": wire("Alert", "kind"),
  "alerts.": ALERT_KEYS,
  "level.": wire("Health", "level"),
  "state.": wire("Status", "state"),
  "health.bit_": STATUS_BITS,
  "errors.": ERROR_CODES,
  "calibrate.step_": "ui",
  "compat.": COMPAT_IDS,
  "compat.code_": COMPAT_CODES,
  "lock.": "ui",
  "nav.": "ui",
  "theme.": "ui",
  "programs.mood.": "ui",
  "programs.toolbox.": "ui",
  "programs.det.": "ui",
  "programs.det.roi_": "ui",
  "programs.det.colour_": "ui",
  "programs.ast.": "ui",
};

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return f === "test" || f === "mock" ? [] : sources(p);
    return /\.tsx?$/.test(f) && !f.includes(".test.") && !f.endsWith(".d.ts") ? [p] : [];
  });
}

function has(bundle: unknown, key: string): boolean {
  let node: unknown = bundle;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null) return false;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "string";
}

const hasKey = (bundle: unknown, key: string) => has(bundle, key) || has(bundle, `${key}_other`);

describe("station i18n: keys built at run time (QC 0.2.9 QD-14)", () => {
  const prefixes = new Set<string>();
  for (const file of sources(SRC)) {
    for (const m of readFileSync(file, "utf8").matchAll(/\bt\(\s*`([a-z_.]+)\$\{/g)) prefixes.add(m[1] ?? "");
  }

  it("finds the template keys", () => {
    expect(prefixes.size).toBeGreaterThan(20);
  });

  it("every template key has a declared value set", () => {
    expect([...prefixes].filter((p) => !(p in DOMAINS)).sort()).toEqual([]);
  });

  it("every value the server can send has words in en and vi", () => {
    const missing: string[] = [];
    for (const prefix of prefixes) {
      const domain = DOMAINS[prefix];
      if (!Array.isArray(domain)) continue;
      expect(domain.length, prefix).toBeGreaterThan(0);
      for (const value of domain) {
        const key = `${prefix}${value}`;
        if (!hasKey(en, key)) missing.push(`en ${key}`);
        if (!hasKey(vi, key)) missing.push(`vi ${key}`);
      }
    }
    expect(missing.sort()).toEqual([]);
  });
});
