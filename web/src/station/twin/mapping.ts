/**
 * Level 1 3D twin: pure data shaping (no three.js here, so it is cheap to import and unit-test).
 *
 * Joint mapping, Station → SO-101 URDF (`so101/so101_new_calib.urdf`, TheRobotStudio SO-ARM100):
 *
 *   Station key           unit (lerobot, use_degrees=True)       URDF joint      URDF angle
 *   shoulder_pan.pos      degrees, 0 = middle of calibrated range shoulder_pan    +deg · π/180
 *   shoulder_lift.pos     degrees, 0 = middle of calibrated range shoulder_lift   +deg · π/180
 *   elbow_flex.pos        degrees, 0 = middle of calibrated range elbow_flex      +deg · π/180
 *   wrist_flex.pos        degrees, 0 = middle of calibrated range wrist_flex      +deg · π/180
 *   wrist_roll.pos        degrees, 0 = middle of calibrated range wrist_roll      +deg · π/180
 *   gripper.pos           0–100 % (0 = closed, 100 = open)        gripper         pct/100 · GRIPPER_OPEN_RAD
 *
 * lerobot's degree mode puts 0° at the middle of each joint's calibrated range, which is exactly
 * the zero of the "new calibration" URDF ("each joint's virtual zero is set to the middle of its
 * joint range"), so the arm joints need no offset; the signs were checked on screen against the
 * URDF axes (see JOINT_SIGN). The URDF gripper is a revolute jaw (−10°…100°) while lerobot drives
 * it 0–100 %: 0 % maps to the closed jaw (0 rad) and 100 % to GRIPPER_OPEN_RAD. Every angle is
 * clamped to the URDF limits so a bad sample can never fold the model through itself.
 */
import type { Level, MotorSample } from "../api/types";
import { motorLevel, type Thresholds } from "../health";
import { PALETTE } from "@/hibiscus/sprites.gen";

export const TWIN_JOINTS = [
  "shoulder_pan",
  "shoulder_lift",
  "elbow_flex",
  "wrist_flex",
  "wrist_roll",
  "gripper",
] as const;
export type TwinJoint = (typeof TWIN_JOINTS)[number];

/** URDF joint limits (rad), copied from so101_new_calib.urdf. */
export const URDF_LIMITS: Record<TwinJoint, readonly [number, number]> = {
  shoulder_pan: [-1.91986, 1.91986],
  shoulder_lift: [-1.74533, 1.74533],
  elbow_flex: [-1.69, 1.69],
  wrist_flex: [-1.65806, 1.65806],
  wrist_roll: [-2.74385, 2.84121],
  gripper: [-0.174533, 1.74533],
};

/** +1: a positive Station angle turns the URDF joint the positive way about its axis. */
export const JOINT_SIGN: Record<Exclude<TwinJoint, "gripper">, 1 | -1> = {
  shoulder_pan: 1,
  shoulder_lift: 1,
  elbow_flex: 1,
  wrist_flex: 1,
  wrist_roll: 1,
};

/** Jaw angle for a fully open gripper (100 %). */
export const GRIPPER_OPEN_RAD = 1.74533;

const DEG = Math.PI / 180;

function clamp(v: number, [lo, hi]: readonly [number, number]): number {
  return Math.min(hi, Math.max(lo, v));
}

/** One Station joint value (degrees, or % for the gripper) → URDF angle (rad), clamped. */
export function jointToUrdf(joint: TwinJoint, value: number): number {
  if (joint === "gripper") return clamp((value / 100) * GRIPPER_OPEN_RAD, URDF_LIMITS.gripper);
  return clamp(JOINT_SIGN[joint] * value * DEG, URDF_LIMITS[joint]);
}

export type UrdfPose = Partial<Record<TwinJoint, number>>;

/**
 * Station positions (`{"shoulder_pan.pos": 12.5, …}` or bare joint names) → URDF angles.
 * Missing or non-finite values are left out (the model keeps its previous angle for them).
 */
export function toUrdfPose(
  positions: Readonly<Record<string, number | null | undefined>> | null | undefined,
): UrdfPose {
  const out: UrdfPose = {};
  if (!positions) return out;
  for (const j of TWIN_JOINTS) {
    const v = positions[`${j}.pos`] ?? positions[j];
    if (typeof v === "number" && Number.isFinite(v)) out[j] = jointToUrdf(j, v);
  }
  return out;
}

/** The calibrated rest pose: every joint in the middle of its range, gripper closed. */
export const REST_POSE: UrdfPose = Object.fromEntries(TWIN_JOINTS.map((j) => [j, 0]));

// ------------------------------------------------------------------ temperature colours

/** Motor housing colour per level: the same pixel palette as the motor-health cells. */
export const LEVEL_COLOR: Record<Level, string> = {
  ok: PALETTE.g,
  warn: PALETTE.y,
  hot: PALETTE.Y,
  critical: PALETTE.r,
};

/** Colour of a motor with no telemetry yet (neutral grey-blue, not "ok" green). */
export const UNKNOWN_COLOR = PALETTE.s;

/** Level of every twin motor from live follower telemetry (null = no sample yet). */
export function motorLevels(
  motors: Readonly<Record<string, MotorSample>> | undefined,
  th: Thresholds,
): Record<TwinJoint, Level | null> {
  const out = {} as Record<TwinJoint, Level | null>;
  for (const j of TWIN_JOINTS) {
    const s = motors?.[j];
    out[j] = s && !s.stale ? motorLevel(s, th) : null;
  }
  return out;
}

export function levelColor(level: Level | null): string {
  return level === null ? UNKNOWN_COLOR : LEVEL_COLOR[level];
}

// ------------------------------------------------------------------ ghost playback

export interface JointSeries {
  /** Seconds from the start; when absent the samples are spread evenly over `duration`. */
  t?: readonly number[];
  joints: Readonly<Record<string, readonly number[]>>;
}

/** Sample count of a series (the longest joint list). */
export function seriesLength(s: JointSeries): number {
  return Math.max(0, ...Object.values(s.joints).map((v) => v.length));
}

/** Time of sample `i` (evenly spread when the series has no `t`). */
function timeAt(s: JointSeries, i: number, n: number, duration: number): number {
  const t = s.t?.[i];
  if (t !== undefined) return t;
  return n <= 1 ? 0 : (i / (n - 1)) * duration;
}

/** Length of the series in seconds (its last `t`, or `duration` for a `t`-less preview). */
export function seriesDuration(s: JointSeries, duration = 0): number {
  const n = seriesLength(s);
  if (n === 0) return 0;
  return s.t?.length ? (s.t[s.t.length - 1] ?? 0) - (s.t[0] ?? 0) : duration;
}

/**
 * Joint positions (Station units) at `time` seconds from the series start, linearly
 * interpolated between the two neighbouring samples and held at both ends.
 */
export function sampleSeries(s: JointSeries, time: number, duration = 0): Record<string, number> {
  const n = seriesLength(s);
  const out: Record<string, number> = {};
  if (n === 0) return out;
  const t0 = timeAt(s, 0, n, duration);
  const t = t0 + Math.max(0, time);
  // Binary search for the last sample at or before t.
  let lo = 0;
  let hi = n - 1;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (timeAt(s, mid, n, duration) <= t) lo = mid;
    else hi = mid - 1;
  }
  const i = lo;
  const j = Math.min(n - 1, i + 1);
  const ti = timeAt(s, i, n, duration);
  const tj = timeAt(s, j, n, duration);
  const f = j === i || tj <= ti ? 0 : Math.min(1, (t - ti) / (tj - ti));
  for (const [key, vals] of Object.entries(s.joints)) {
    const a = vals[Math.min(i, vals.length - 1)];
    const b = vals[Math.min(j, vals.length - 1)];
    if (a === undefined || b === undefined) continue;
    out[key] = a + (b - a) * f;
  }
  return out;
}
