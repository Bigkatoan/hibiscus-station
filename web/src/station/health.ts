/**
 * Motor health (R1, docs/spec/station.md §4.5.3): thresholds, levels and their pixel colours.
 * The Station owner decides alerts and the safe stop; the UI colours samples with the same rules
 * so a cell is never green while the server says otherwise (server `level` always wins).
 */
import { PALETTE, type SpriteName } from "@/hibiscus/sprites.gen";
import type { Level, MotorLimits, MotorSample, Thresholds as SettingsThresholds } from "./api/types";
import { fmtFixed } from "./units";

/** The temperature part of the Station thresholds (Settings.thresholds / RobotProfile.thresholds). */
export type Thresholds = Pick<SettingsThresholds, "temp_warn_c" | "temp_hot_c" | "temp_critical_c">;

export const DEFAULT_THRESHOLDS: Thresholds = { temp_warn_c: 50, temp_hot_c: 60, temp_critical_c: 65 };
export const FACTORY_MAX_TEMP_C = 70;
export const LOAD_WARN_PCT = 90;
export const CRITICAL_STATUS_BITS = ["overheat", "overload"] as const;

const ORDER: Record<Level, number> = { ok: 0, warn: 1, hot: 2, critical: 3 };

export function tempLevel(temp: number | null | undefined, th: Thresholds = DEFAULT_THRESHOLDS): Level {
  if (temp === null || temp === undefined || !Number.isFinite(temp)) return "ok";
  if (temp >= th.temp_critical_c) return "critical";
  if (temp >= th.temp_hot_c) return "hot";
  if (temp >= th.temp_warn_c) return "warn";
  return "ok";
}

export function worstLevel(levels: Iterable<Level>): Level {
  let w: Level = "ok";
  for (const l of levels) if (ORDER[l] > ORDER[w]) w = l;
  return w;
}

/** Effective level: the worse of the server's level and the locally computed one.
 *
 * The leader is moved by hand with torque off: its status bits and load are shown but never raise
 * its level, and its temperature never goes beyond "hot" (field report 0.2.8; the Station does the
 * same and never stops the robot for the leader). */
export function motorLevel(
  s: MotorSample | undefined,
  th: Thresholds = DEFAULT_THRESHOLDS,
  arm: "follower" | "leader" = "follower",
): Level {
  if (!s) return "ok";
  const temp = tempLevel(s.temp_c, th);
  if (arm === "leader") {
    const w = worstLevel([s.level, temp]);
    return w === "critical" ? "hot" : w;
  }
  const local: Level[] = [temp];
  if (s.status.some((b) => (CRITICAL_STATUS_BITS as readonly string[]).includes(b))) local.push("critical");
  if (s.load_pct !== null && Math.abs(s.load_pct) >= LOAD_WARN_PCT) local.push("warn");
  return worstLevel([s.level, ...local]);
}

type PaletteKey = keyof typeof PALETTE;

/** Fixed pixel colours per level (same in day and night, like the button sprites). */
export const LEVEL_STYLE: Record<Level, { bg: PaletteKey; fg: PaletteKey; edge: PaletteKey }> = {
  ok: { bg: "g", fg: "o", edge: "f" },
  warn: { bg: "y", fg: "o", edge: "Y" },
  hot: { bg: "Y", fg: "o", edge: "d" },
  critical: { bg: "m", fg: "C", edge: "r" },
};

export function levelCss(level: Level): { backgroundColor: string; color: string; borderColor: string } {
  const s = LEVEL_STYLE[level];
  return { backgroundColor: PALETTE[s.bg], color: PALETTE[s.fg], borderColor: PALETTE[s.edge] };
}

export function thermoSprite(level: Level): SpriteName {
  if (level === "critical") return "icon_thermo_critical";
  if (level === "hot" || level === "warn") return "icon_thermo_hot";
  return "icon_thermo_ok";
}

/**
 * §4.5.3 rule enforced at load: critical ≤ max_temperature_limit − 3, hot ≤ critical − 3,
 * warn ≤ hot − 5. Returns i18n keys (station namespace) of the violated rules.
 */
export function validateThresholds(th: Thresholds, maxTempC: number = FACTORY_MAX_TEMP_C): string[] {
  const errs: string[] = [];
  if (th.temp_critical_c > maxTempC - 3) errs.push("settings.err_critical");
  if (th.temp_hot_c > th.temp_critical_c - 3) errs.push("settings.err_hot");
  if (th.temp_warn_c > th.temp_hot_c - 5) errs.push("settings.err_warn");
  return errs;
}

export function fmt(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined || !Number.isFinite(v) ? "–" : fmtFixed(v, digits);
}

/** Lowest motor temperature limit reported by the motors (or the factory value). */
export function maxTempLimit(limits: Partial<Record<string, MotorLimits>>): number {
  const vals = Object.values(limits)
    .map((l) => l?.max_temp_c)
    .filter((v): v is number => typeof v === "number");
  return vals.length ? Math.min(...vals) : FACTORY_MAX_TEMP_C;
}

/**
 * Linear cooling estimate (§4.5.3 "cooling countdown"): seconds until `temp` falls below
 * `target`, fitted over (t, v) samples. Null when not cooling.
 */
export function coolingEtaS(
  t: readonly number[],
  v: readonly (number | null)[],
  target: number,
): number | null {
  const pts: [number, number][] = [];
  t.forEach((x, i) => {
    const y = v[i];
    if (y !== null && y !== undefined) pts.push([x, y]);
  });
  if (pts.length < 3) return null;
  const tEnd = pts[pts.length - 1]?.[0] ?? 0;
  const win = pts.filter(([x]) => x >= tEnd - 60);
  const n = win.length;
  const mx = win.reduce((a, [x]) => a + x, 0) / n;
  const my = win.reduce((a, [, y]) => a + y, 0) / n;
  let num = 0;
  let den = 0;
  for (const [x, y] of win) {
    num += (x - mx) * (y - my);
    den += (x - mx) ** 2;
  }
  if (den === 0) return null;
  const slope = num / den;
  if (slope >= -1e-6) return null;
  const now = my + slope * (tEnd - mx);
  if (now <= target) return 0;
  return Math.ceil((target - now) / slope);
}

/** Peak temperature of an episode sidecar summary (`arm -> motor -> °C`), or null when empty. */
export function peakTemp(maxTemp: Record<string, Record<string, number>> | null | undefined): number | null {
  const all = Object.values(maxTemp ?? {}).flatMap((m) => Object.values(m));
  return all.length ? Math.max(...all) : null;
}
