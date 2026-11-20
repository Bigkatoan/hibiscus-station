/**
 * Mock of the trajectories / poses / detectors / signals / programs backend (station-programs.md
 * §3-§7, §11) for vitest and the mock build (`pnpm build:mock`). It follows the contract shapes and the state
 * machine additions (`recording_traj`, `playing`, `programming`, dry runs that never leave
 * `idle`/`disconnected`), and runs block programs straight from the Blockly JSON with a small
 * generator-based interpreter (the real Station compiles to an AST on the server; this mock only
 * has to behave alike for the UI). Time only advances through `MockStation.step()`.
 */
import type { components } from "../api/schema";
import type {
  CheckIssue,
  CheckReport,
  ColorRule,
  Detector,
  DetectorInput,
  DetectorResult,
  FakeConditions,
  OperatorInput,
  Pose,
  PoseInput,
  Program,
  ProgramInput,
  ProgramLogLine,
  ProgramRunSummary,
  ProgramState,
  ProgramSummary,
  RecordTrajectoryRequest,
  RunProgramRequest,
  Session,
  Signal,
  Trajectory,
  TrajectoryDetail,
  TrajectorySummary,
  TrajectoryUpdate,
  PlayTrajectoryRequest,
} from "../api/types";
import catalogJson from "./blockCatalog.json";
import {
  asEditorDoc,
  emptyProgram,
  referencedValues,
  specIndex,
  startBlocks,
  walkBlocks,
  type EditorDoc,
  type SBlock,
} from "../programs/blockly/serialize";
import type { BlockCatalog } from "../api/types";
import * as fx from "./fixtures";
import { MockProblem, type MockStation } from "./sim";

type S = components["schemas"];
type Phase = NonNullable<S["Status"]["sub"]>;
type WaitInfo = S["WaitInfo"];
type ConditionValue = S["ConditionValue"];
type Scalar = number | string;

export const CATALOG = catalogJson as BlockCatalog;
const SPECS = specIndex(CATALOG);
const JOINTS = fx.MOTORS.map((m) => `${m}.pos`);
const CAL_HASH = "cal_3f9a1c";

// ------------------------------------------------------------------ fixtures
interface Take {
  meta: Trajectory;
  t: number[];
  rows: number[][];
  checkedReplay: boolean;
}

function iso(offsetMin = 0): string {
  return new Date(Date.UTC(2026, 10, 16, 10, 0) + offsetMin * 60_000).toISOString();
}

function synthTake(seed: number, seconds: number, fps: number): { t: number[]; rows: number[][] } {
  const n = Math.round(seconds * fps);
  const t: number[] = [];
  const rows: number[][] = [];
  for (let k = 0; k < n; k += 1) {
    const s = k / fps;
    t.push(Math.round(s * 1000) / 1000);
    // Idle 0.8 s at both ends, motion in between (so the auto trim has something to find).
    const u = Math.min(1, Math.max(0, (s - 0.8) / Math.max(0.1, seconds - 1.6)));
    const ease = u * u * (3 - 2 * u);
    rows.push(
      JOINTS.map((_, i) => {
        if (i === 5) return Math.round((20 + 60 * Math.sin(Math.PI * ease) ** 2) * 10) / 10;
        return (
          Math.round(Math.sin(ease * Math.PI * (1 + ((i + seed) % 3)) + seed + i) * (25 + 5 * i) * 10) / 10
        );
      }),
    );
  }
  return { t, rows };
}

function decimate(values: number[], n: number): number[] {
  if (values.length <= n) return values;
  return Array.from({ length: n }, (_, k) => values[Math.round((k * (values.length - 1)) / (n - 1))] ?? 0);
}

/** Auto trim (§3.1): idle = every joint moves < 0.5° for > 0.5 s at the start and at the end. */
export function suggestTrim(
  t: number[],
  rows: number[][],
  deg = 0.5,
  minS = 0.5,
): { start_s: number; end_s: number } {
  const moved = (a: number[] | undefined, b: number[] | undefined) =>
    a !== undefined && b !== undefined && a.some((v, i) => Math.abs(v - (b[i] ?? v)) >= deg);
  let first = 0;
  while (first < rows.length - 1 && !moved(rows[first + 1], rows[0])) first += 1;
  let last = rows.length - 1;
  while (last > 0 && !moved(rows[last - 1], rows[rows.length - 1])) last -= 1;
  const raw = t[t.length - 1] ?? 0;
  const start = t[first] ?? 0;
  const end = raw - (t[last] ?? raw);
  return {
    start_s: start > minS ? Math.round(start * 100) / 100 : 0,
    end_s: end > minS ? Math.round(end * 100) / 100 : 0,
  };
}

function pose(row: number[] | undefined): Record<string, number> {
  return Object.fromEntries(JOINTS.map((j, i) => [j, row?.[i] ?? 0]));
}

function makeTake(
  id: string,
  name: string,
  opts: { seconds: number; fps?: number; seed: number; status?: Trajectory["status"]; at?: number },
): Take {
  const fps = opts.fps ?? 30;
  const { t, rows } = synthTake(opts.seed, opts.seconds, fps);
  const sug = suggestTrim(t, rows);
  const take: Take = {
    t,
    rows,
    checkedReplay: false,
    meta: {
      id,
      name,
      robot: fx.robot.id,
      created_at: iso(opts.at ?? 0),
      updated_at: iso(opts.at ?? 0),
      fps,
      joints: [...JOINTS],
      samples: t.length,
      raw_duration_s: t[t.length - 1] ?? 0,
      trim: sug,
      suggested_trim: sug,
      duration_s: 0,
      start_pose: {},
      end_pose: {},
      max_speed_deg_s: 0,
      calibration_hash: opts.status === "needs_check" ? "cal_old" : CAL_HASH,
      status: opts.status ?? "ready",
      checked_at: null,
      keyframe_cameras: ["front"],
      keyframe_times: Array.from({ length: Math.floor(opts.seconds) }, (_, k) => k),
      samples_file: "samples.parquet",
    },
  };
  applyTrim(take);
  return take;
}

function trimmedRange(take: Take): [number, number] {
  const { start_s, end_s } = take.meta.trim;
  const raw = take.meta.raw_duration_s;
  let a = take.t.findIndex((x) => x >= start_s);
  let b = take.t.length - 1;
  while (b > 0 && (take.t[b] ?? 0) > raw - end_s) b -= 1;
  if (a < 0) a = 0;
  if (b < a) b = a;
  return [a, b];
}

function applyTrim(take: Take): void {
  const [a, b] = trimmedRange(take);
  const m = take.meta;
  m.duration_s = Math.max(0, Math.round(((take.t[b] ?? 0) - (take.t[a] ?? 0)) * 100) / 100);
  m.start_pose = pose(take.rows[a]);
  m.end_pose = pose(take.rows[b]);
  let peak = 0;
  for (let k = a + 1; k <= b; k += 1) {
    const dt = (take.t[k] ?? 0) - (take.t[k - 1] ?? 0) || 1 / m.fps;
    for (let i = 0; i < 5; i += 1) {
      const v = Math.abs(((take.rows[k]?.[i] ?? 0) - (take.rows[k - 1]?.[i] ?? 0)) / dt);
      if (v > peak) peak = v;
    }
  }
  m.max_speed_deg_s = Math.round(peak * 10) / 10;
}

function summary(take: Take): TrajectorySummary {
  const [a, b] = trimmedRange(take);
  const rows = take.rows.slice(a, b + 1);
  return {
    ...structuredClone(take.meta),
    preview: Object.fromEntries(
      JOINTS.map((j, i) => [
        j,
        decimate(
          rows.map((r) => r[i] ?? 0),
          64,
        ),
      ]),
    ),
  };
}

function detail(take: Take): TrajectoryDetail {
  return {
    ...structuredClone(take.meta),
    series: {
      t: decimate(take.t, 600),
      joints: Object.fromEntries(
        JOINTS.map((j, i) => [
          j,
          decimate(
            take.rows.map((r) => r[i] ?? 0),
            600,
          ),
        ]),
      ),
    },
  };
}

export const RED: ColorRule = {
  label: "red",
  h_min: 170,
  h_max: 8,
  s_min: 120,
  s_max: 255,
  v_min: 70,
  v_max: 255,
  min_fraction: 0.05,
};
export const BLUE: ColorRule = {
  label: "blue",
  h_min: 100,
  h_max: 125,
  s_min: 120,
  s_max: 255,
  v_min: 50,
  v_max: 255,
  min_fraction: 0.05,
};

export function sampleProgramDoc(a: string, b: string): EditorDoc {
  const num = (id: string, n: number) => ({ block: { type: "math_number", id, fields: { NUM: n } } });
  return {
    blocks: {
      languageVersion: 0,
      blocks: [
        {
          type: "hb_start",
          id: "start",
          x: 40,
          y: 40,
          inputs: {
            DO: {
              block: {
                type: "hb_repeat_forever",
                id: "loop",
                inputs: {
                  DO: {
                    block: {
                      type: "controls_if",
                      id: "if_ab",
                      extraState: { elseIfCount: 1 },
                      inputs: {
                        IF0: {
                          block: {
                            type: "logic_operation",
                            id: "or_a",
                            fields: { OP: "OR" },
                            inputs: {
                              A: { block: { type: "hb_key_pressed", id: "key_1", fields: { KEY: "1" } } },
                              B: {
                                block: {
                                  type: "hb_camera_sees",
                                  id: "sees_red",
                                  fields: { CAMERA: "", DETECTOR: "cube_color", LABEL: "red" },
                                },
                              },
                            },
                          },
                        },
                        DO0: {
                          block: {
                            type: "hb_play_trajectory",
                            id: "play_a",
                            fields: { TRAJECTORY: a, SPEED: 100 },
                          },
                        },
                        IF1: {
                          block: {
                            type: "logic_operation",
                            id: "or_b",
                            fields: { OP: "OR" },
                            inputs: {
                              A: { block: { type: "hb_key_pressed", id: "key_2", fields: { KEY: "2" } } },
                              B: {
                                block: {
                                  type: "hb_camera_sees",
                                  id: "sees_blue",
                                  fields: { CAMERA: "", DETECTOR: "cube_color", LABEL: "blue" },
                                },
                              },
                            },
                          },
                        },
                        DO1: {
                          block: {
                            type: "hb_play_trajectory",
                            id: "play_b",
                            fields: { TRAJECTORY: b, SPEED: 100 },
                          },
                        },
                      },
                      next: {
                        block: { type: "hb_wait", id: "wait", inputs: { SECONDS: num("wait_s", 0.2) } },
                      },
                    },
                  },
                },
              },
            },
          },
        },
      ],
    },
    variables: [],
  };
}

// ------------------------------------------------------------------ the interpreter
interface Wait {
  info: WaitInfo["kind"] | "tick";
  block: string;
  timeout: number | null;
  done: () => boolean;
  phase?: Phase;
}

class Timeout extends Error {
  constructor(readonly block: string) {
    super("timeout");
  }
}

class StopSignal extends Error {
  constructor(
    readonly outcome: ProgramState["status"],
    readonly reason: string | null,
  ) {
    super(reason ?? outcome);
  }
}

interface Run {
  state: ProgramState;
  doc: EditorDoc;
  vars: Map<string, { name: string; type: string }>;
  started: number;
  gen: Generator<Wait, void>;
  wait: Wait | null;
  waitSince: number;
  latches: { buttons: Set<string>; keys: Set<string> };
  answer: string | null;
  fakes: FakeConditions;
  stopRequested: boolean;
  lastBroadcast: number;
  seq: number;
  lines: ProgramLogLine[];
  summary: ProgramRunSummary;
  msgSeen: Map<string, number>;
  session: boolean;
}

const MOTION_TYPES = new Set([
  "hb_play_trajectory",
  "hb_move_to_pose",
  "hb_gripper",
  "hb_go_home",
  "hb_relax_arm",
  "hb_run_model_for",
  "hb_run_model_until",
]);

function runId(n: number): string {
  return `r_20261116_${String(100000 + n).slice(-6)}_${(0xa000 + n).toString(16).slice(-4)}`;
}

/** The operator's answer once an ask resumed (a function, so TS does not narrow across `yield`). */
function answerOf(run: { answer: string | null }): string {
  return run.answer ?? "";
}

/** A Blockly field value as text (numbers too); anything else gives `fallback`. */
function fstr(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : typeof v === "number" ? String(v) : fallback;
}

function num(v: Scalar | boolean | null | undefined): number {
  if (typeof v === "number") return v;
  if (typeof v === "boolean") return v ? 1 : 0;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

export class MockPrograms {
  takes: Take[];
  poses: Pose[];
  detectors: Detector[];
  programs: Program[];
  signals = new Map<string, Signal>();
  signalSeq = 0;
  runs: ProgramRunSummary[] = [];
  runLogs = new Map<string, ProgramLogLine[]>();
  run: Run | null = null;
  /** Last state per program (GET /programs/{id}/state after the end). */
  lastState = new Map<string, ProgramState>();
  record: {
    session: Session;
    req: RecordTrajectoryRequest;
    t: number;
    phase: "countdown" | "capture";
    rows: number[][];
    ts: number[];
    acc: number;
  } | null = null;
  play: { session: Session; take: Take; speed: number; check: boolean; t: number; approach: number } | null =
    null;
  private seq = 0;

  constructor(private readonly sim: MockStation) {
    const a = makeTake("t_20261116_101500_a1b2", "Pick A", { seconds: 6, seed: 1, at: 0 });
    const b = makeTake("t_20261116_101800_c3d4", "Pick B", { seconds: 5, seed: 2, at: 3 });
    const old = makeTake("t_20261110_090000_e5f6", "Wave (old calibration)", {
      seconds: 4,
      seed: 3,
      at: -9000,
      status: "needs_check",
    });
    this.takes = [a, b, old];
    this.poses = [
      {
        name: "home",
        positions: pose([0, -90, 90, 60, 0, 10]),
        source: "manual",
        trajectory: null,
        calibration_hash: CAL_HASH,
        created_at: iso(-60),
        needs_check: false,
      },
    ];
    this.detectors = [
      {
        id: "cube_color",
        name: "Cube colour",
        robot: fx.robot.id,
        created_at: iso(-30),
        updated_at: iso(-30),
        spec: {
          kind: "color",
          camera: "front",
          roi: { x: 0.55, y: 0.5, w: 0.35, h: 0.35 },
          rules: [RED, BLUE],
        },
        model_file: null,
        model_sha256: null,
        labels: ["red", "blue"],
      },
    ];
    this.programs = [];
    this.putProgram("sort_cubes", {
      name: "Sort cubes A/B",
      editor: sampleProgramDoc(a.meta.id, b.meta.id),
      buttons: [],
    });
  }

  // ------------------------------------------------------------------ trajectories
  take(id: string): Take {
    const t = this.takes.find((x) => x.meta.id === id);
    if (!t) throw new MockProblem(404, "not_found");
    return t;
  }

  listTrajectories(): { trajectories: TrajectorySummary[] } {
    return { trajectories: this.takes.map(summary) };
  }

  getTrajectory(id: string): TrajectoryDetail {
    return detail(this.take(id));
  }

  updateTrajectory(id: string, upd: TrajectoryUpdate): Trajectory {
    const take = this.take(id);
    if (this.play?.take === take) throw new MockProblem(409, "busy", { state: this.sim.state });
    if (upd.name) take.meta.name = upd.name;
    if (upd.trim) {
      const raw = take.meta.raw_duration_s;
      if (upd.trim.start_s + upd.trim.end_s >= raw) throw new MockProblem(422, "validation_failed");
      take.meta.trim = { ...upd.trim };
      applyTrim(take);
    }
    if (upd.save && take.meta.status === "draft") take.meta.status = "ready";
    take.meta.updated_at = new Date().toISOString();
    return structuredClone(take.meta);
  }

  deleteTrajectory(id: string): void {
    const take = this.take(id);
    if (this.play?.take === take || this.record)
      throw new MockProblem(409, "busy", { state: this.sim.state });
    this.takes = this.takes.filter((x) => x !== take);
  }

  confirmTrajectory(id: string): Trajectory {
    const take = this.take(id);
    if (take.meta.status !== "needs_check" || !take.checkedReplay) throw new MockProblem(409, "needs_check");
    take.meta.status = "ready";
    take.meta.calibration_hash = CAL_HASH;
    take.meta.checked_at = new Date().toISOString();
    return structuredClone(take.meta);
  }

  startRecord(req: RecordTrajectoryRequest): Session {
    this.sim.requireIdle();
    this.sim.requireCool();
    if (!this.sim.profile?.leader) throw new MockProblem(409, "not_connected", { arm: "leader" });
    const session = this.newSession("traj_record", req.fps ?? 30, "countdown", req.countdown_s ?? 3);
    this.record = { session, req, t: 0, phase: "countdown", rows: [], ts: [], acc: 0 };
    this.sim.enterSession(session, "recording_traj", "countdown");
    this.recordMsg(false, null);
    return session;
  }

  stopRecord(): TrajectoryDetail {
    const rec = this.record;
    if (!rec) throw new MockProblem(409, "busy", { state: this.sim.state });
    return this.finishRecord();
  }

  private finishRecord(): TrajectoryDetail {
    const rec = this.record;
    if (!rec) throw new MockProblem(409, "busy", { state: this.sim.state });
    this.record = null;
    const fps = rec.req.fps ?? 30;
    const seconds = Math.max(1, rec.ts.length / fps);
    const stamp = new Date();
    const hhmmss = stamp.toISOString().slice(11, 19).replace(/:/g, "");
    const id = `t_20261116_${hhmmss}_${(0xb000 + ++this.seq).toString(16).slice(-4)}`;
    const name = rec.req.name ?? `Take ${stamp.toISOString().slice(11, 16)}`;
    const take = makeTake(id, name, { seconds, fps, seed: this.seq + 3, status: "draft" });
    take.meta.created_at = stamp.toISOString();
    take.meta.updated_at = stamp.toISOString();
    this.takes.unshift(take);
    this.sim.broadcastMsg({
      type: "trajectory_record",
      session_id: rec.session.id,
      phase: "saving",
      elapsed_s: rec.t,
      limit_s: rec.req.limit_s ?? 60,
      samples: rec.ts.length,
      trajectory_id: null,
      ended: false,
    });
    this.sim.endSession("completed");
    this.sim.broadcastMsg({
      type: "trajectory_record",
      session_id: rec.session.id,
      phase: "done",
      elapsed_s: rec.t,
      limit_s: rec.req.limit_s ?? 60,
      samples: rec.ts.length,
      trajectory_id: id,
      ended: true,
    });
    return detail(take);
  }

  private recordMsg(ended: boolean, id: string | null): void {
    const rec = this.record;
    if (!rec) return;
    this.sim.broadcastMsg({
      type: "trajectory_record",
      session_id: rec.session.id,
      phase: rec.phase,
      elapsed_s: Math.round(rec.t * 100) / 100,
      limit_s: rec.req.limit_s ?? 60,
      samples: rec.ts.length,
      trajectory_id: id,
      ended,
    });
  }

  startPlay(id: string, req: PlayTrajectoryRequest): Session {
    const take = this.take(id);
    this.sim.requireIdle();
    this.sim.requireCool();
    const speed = req.check ? this.sim.settings.programs.check_speed_pct : (req.speed_pct ?? 100);
    if (take.meta.status === "draft") throw new MockProblem(409, "busy", { state: "draft" });
    if (take.meta.status === "needs_check" && !req.check) throw new MockProblem(409, "needs_check");
    if (speed > 100 && !this.sim.profile?.follower.allow_fast_replay)
      throw new MockProblem(409, "fast_replay_not_allowed");
    const session = this.newSession("traj_play", take.meta.fps, "approach", null);
    session.program = null;
    this.play = { session, take, speed, check: Boolean(req.check), t: 0, approach: 1 };
    this.sim.enterSession(session, "playing", "approach");
    return session;
  }

  // ------------------------------------------------------------------ poses
  listPoses(): { poses: Pose[] } {
    return { poses: structuredClone(this.poses) };
  }

  replacePoses(list: PoseInput[]): { poses: Pose[] } {
    const names = new Set(list.map((p) => p.name));
    if (names.size !== list.length) throw new MockProblem(422, "validation_failed");
    this.poses = list.map((p) => {
      const old = this.poses.find((x) => x.name === p.name);
      return {
        ...p,
        source: p.source ?? "manual",
        trajectory: p.trajectory ?? null,
        calibration_hash: old?.calibration_hash ?? CAL_HASH,
        created_at: old?.created_at ?? new Date().toISOString(),
        needs_check: old?.needs_check ?? false,
      };
    });
    return this.listPoses();
  }

  capturePose(name: string): Pose {
    this.sim.requireIdle();
    const p: Pose = {
      name,
      positions: Object.fromEntries(fx.MOTORS.map((m, i) => [`${m}.pos`, this.sim.jointPos(i)])),
      source: "live",
      trajectory: null,
      calibration_hash: CAL_HASH,
      created_at: new Date().toISOString(),
      needs_check: false,
    };
    this.poses = [...this.poses.filter((x) => x.name !== name), p];
    return p;
  }

  // ------------------------------------------------------------------ detectors, signals
  detector(id: string): Detector {
    const d = this.detectors.find((x) => x.id === id);
    if (!d) throw new MockProblem(404, "not_found");
    return d;
  }

  putDetector(id: string, body: DetectorInput): Detector {
    const old = this.detectors.find((x) => x.id === id);
    const labels = body.spec.kind === "color" ? body.spec.rules.map((r) => r.label) : body.spec.labels;
    if (new Set(labels).size !== labels.length)
      throw new MockProblem(422, "detector_invalid", { reason: "labels" });
    const keepModel = old?.spec.kind === "classifier" && body.spec.kind === "classifier";
    const d: Detector = {
      ...body,
      id,
      robot: fx.robot.id,
      created_at: old?.created_at ?? new Date().toISOString(),
      updated_at: new Date().toISOString(),
      model_file: keepModel ? old.model_file : null,
      model_sha256: keepModel ? old.model_sha256 : null,
      labels,
    };
    this.detectors = [...this.detectors.filter((x) => x.id !== id), d];
    return d;
  }

  deleteDetector(id: string): void {
    this.detector(id);
    this.detectors = this.detectors.filter((x) => x.id !== id);
  }

  setModel(id: string, size: number): Detector {
    const d = this.detector(id);
    if (d.spec.kind !== "classifier")
      throw new MockProblem(422, "detector_invalid", { reason: "not_classifier" });
    if (size < 16) throw new MockProblem(422, "detector_invalid", { reason: "onnx" });
    d.model_file = `${id}.onnx`;
    d.model_sha256 = "e3b0c44298fc1c149afbf4c8996fb924";
    return d;
  }

  /**
   * The mock camera draws a red cube at about (0.72, 0.66) of the front frame (`browser.ts`): a colour
   * detector whose ROI covers it on that camera sees "red"; a classifier answers its first label.
   */
  evaluate(
    id: string | null,
    spec: Detector["spec"],
    camera?: string | null,
    /** A dry run's synthetic camera: sees nothing unless a fake says otherwise (§5.2). */
    synthetic = false,
  ): DetectorResult {
    const cam = camera ?? spec.camera;
    if (!synthetic && !this.sim.profile?.cameras[cam])
      throw new MockProblem(409, "camera_unavailable", { camera: cam });
    const fake =
      this.run?.fakes.detectors?.[id ?? ""] ?? (synthetic ? { label: null, confidence: 0 } : undefined);
    if (fake) {
      return {
        detector: id,
        camera: cam,
        label: fake.label,
        confidence: fake.confidence ?? 1,
        scores: fake.label ? { [fake.label]: fake.confidence ?? 1 } : {},
        ms: 0.1,
        tick: this.sim.tick,
        annotated_jpeg_b64: null,
      };
    }
    if (spec.kind === "classifier") {
      const [first, second] = spec.labels;
      const conf = 0.81;
      return {
        detector: id,
        camera: cam,
        label: conf >= (spec.min_confidence ?? 0.5) && first !== spec.none_label ? (first ?? null) : null,
        confidence: conf,
        scores: Object.fromEntries(
          spec.labels.map((l) => [l, l === first ? conf : l === second ? 1 - conf : 0]),
        ),
        ms: 7.4,
        tick: this.sim.tick,
        annotated_jpeg_b64: null,
      };
    }
    const r = spec.roi;
    const inRoi = cam === "front" && r.x <= 0.72 && r.x + r.w >= 0.72 && r.y <= 0.66 && r.y + r.h >= 0.66;
    const cube = 0.03 / Math.max(0.01, r.w * r.h);
    const scores: Record<string, number> = {};
    for (const rule of spec.rules) {
      const red = rule.h_min > rule.h_max || rule.h_max <= 10;
      scores[rule.label] = inRoi && red ? Math.min(1, Math.round(cube * 1000) / 1000) : 0;
    }
    let best: string | null = null;
    for (const rule of spec.rules) {
      const s = scores[rule.label] ?? 0;
      if (s >= (rule.min_fraction ?? 0.05) && (best === null || s > (scores[best] ?? 0))) best = rule.label;
    }
    return {
      detector: id,
      camera: cam,
      label: best,
      confidence: best ? (scores[best] ?? 0) : 0,
      scores,
      ms: 2.1,
      tick: this.sim.tick,
      annotated_jpeg_b64: null,
    };
  }

  setSignal(name: string, value: Scalar, source: Signal["source"]): Signal {
    this.signalSeq += 1;
    const s: Signal = { name, value, source, at: new Date().toISOString(), seq: this.signalSeq };
    this.signals.set(name, s);
    this.sim.broadcastMsg({ type: "signal", ...s });
    return s;
  }

  // ------------------------------------------------------------------ programs: store + check
  program(id: string): Program {
    const p = this.programs.find((x) => x.id === id);
    if (!p) throw new MockProblem(404, "not_found");
    return p;
  }

  listPrograms(): { programs: ProgramSummary[] } {
    return {
      programs: this.programs.map((p) => ({
        id: p.id,
        name: p.name,
        version: p.version,
        updated_at: p.updated_at,
        ok: p.ast !== null && !p.issues.some((i) => i.severity === "error"),
        refs: p.refs,
        dry_run_version: p.dry_run_version,
        last_run: this.runs.find((r) => r.program_id === p.id) ?? null,
      })),
    };
  }

  putProgram(id: string, body: ProgramInput): Program {
    if (this.run?.state.program_id === id) throw new MockProblem(409, "busy", { state: "programming" });
    const old = this.programs.find((x) => x.id === id);
    const doc = asEditorDoc(body.editor);
    const issues = this.check(doc, body.buttons ?? []);
    const refs = referencedValues(doc, CATALOG);
    const now = new Date().toISOString();
    const keys = [...(refs.get("key") ?? [])].sort();
    const p: Program = {
      id,
      name: body.name,
      robot: fx.robot.id,
      version: (old?.version ?? 0) + 1,
      created_at: old?.created_at ?? now,
      updated_at: now,
      editor: body.editor,
      buttons: body.buttons ?? [],
      ast: issues.some((i) => i.severity === "error")
        ? null
        : {
            version: 1,
            variables: (doc.variables ?? []).map((v) => ({
              name: v.name,
              type: v.type === "String" ? "text" : "number",
              initial: v.type === "String" ? "" : 0,
            })),
            buttons: body.buttons ?? [],
            keys,
            body: [],
          },
      issues,
      refs: {
        trajectories: [...(refs.get("trajectory") ?? [])],
        poses: [...(refs.get("pose") ?? [])],
        detectors: [...(refs.get("detector") ?? [])],
        models: [...(refs.get("model") ?? [])],
        signals: [],
        cameras: [...(refs.get("camera") ?? [])],
      },
      dry_run_version: old?.dry_run_version ?? null,
    };
    this.programs = [...this.programs.filter((x) => x.id !== id), p];
    return p;
  }

  deleteProgram(id: string): void {
    this.program(id);
    if (this.run?.state.program_id === id) throw new MockProblem(409, "busy", { state: "programming" });
    this.programs = this.programs.filter((x) => x.id !== id);
  }

  checkReport(id: string): CheckReport {
    const p = this.program(id);
    const doc = asEditorDoc(p.editor);
    const issues = this.check(doc, p.buttons);
    const far = this.firstMotionFar(doc);
    if (far) issues.push(far);
    return {
      ok: !issues.some((i) => i.severity === "error"),
      version: p.version,
      issues,
      ast: p.ast,
      dry_run_required: this.sim.settings.programs.require_dry_run && p.dry_run_version !== p.version,
    };
  }

  /**
   * The validator's first-motion note (D-24): information, not a warning. The first motion under
   * the start block starts farther than `safety.max_approach_deg` from where the follower is now
   * (only said while a robot is connected: the pose is unknown otherwise).
   */
  firstMotionFar(doc: EditorDoc): CheckIssue | null {
    const connected = this.sim.activeId !== null && !["disconnected", "error"].includes(this.sim.state);
    const start = startBlocks(doc)[0];
    if (!connected || !start) return null;
    const first = [...walkBlocks({ blocks: { blocks: [start] } })].find((b) => MOTION_TYPES.has(b.type));
    const f = first?.fields ?? {};
    let target: Record<string, number> | null = null;
    if (first?.type === "hb_play_trajectory")
      target = this.takes.find((x) => x.meta.id === f.TRAJECTORY)?.meta.start_pose ?? null;
    else if (first?.type === "hb_move_to_pose")
      target = this.poses.find((x) => x.name === f.POSE)?.positions ?? null;
    if (!first || !target) return null;
    let deg = 0;
    fx.MOTORS.forEach((m, i) => {
      const v = target[`${m}.pos`];
      if (m !== "gripper" && v !== undefined) deg = Math.max(deg, Math.abs(v - this.sim.jointPos(i)));
    });
    const max = this.sim.settings.safety.max_approach_deg;
    if (deg <= max) return null;
    return {
      id: `first_motion_far:${first.id}`,
      code: "first_motion_far",
      severity: "info",
      block_id: first.id,
      message_key: "programs.issues.first_motion_far",
      params: { deg: Math.round(deg * 10) / 10, max_deg: max },
    };
  }

  /** A small subset of the server validator (§6), enough for the editor's issue markers. */
  check(doc: EditorDoc, buttons: { name: string }[]): CheckIssue[] {
    const issues: CheckIssue[] = [];
    const add = (
      code: CheckIssue["code"],
      severity: CheckIssue["severity"],
      block: string | null,
      params: Record<string, unknown> = {},
    ) => {
      issues.push({
        id: `${code}:${block ?? "-"}`,
        code,
        severity,
        block_id: block,
        message_key: `programs.issues.${code}`,
        params,
      });
    };
    const starts = startBlocks(doc);
    if (starts.length === 0) add("no_start_block", "error", null);
    if (starts.length > 1) for (const s of starts.slice(1)) add("many_start_blocks", "error", s.id);
    for (const top of doc.blocks?.blocks ?? [])
      if (top.type !== "hb_start" && starts.length) add("unreachable", "warning", top.id);
    const loopDepth = new Map<string, boolean>();
    const markLoops = (b: SBlock | undefined, inLoop: boolean): void => {
      for (let cur = b; cur; cur = cur.next?.block) {
        loopDepth.set(cur.id, inLoop);
        const loop =
          inLoop || ["hb_repeat_forever", "controls_repeat_ext", "controls_whileUntil"].includes(cur.type);
        for (const inp of Object.values(cur.inputs ?? {})) markLoops(inp.block, loop);
      }
    };
    for (const s of doc.blocks?.blocks ?? []) markLoops(s, false);
    for (const b of walkBlocks(doc)) {
      const spec = SPECS.get(b.type);
      if (!spec) {
        add("unknown_block", "error", b.id, { type: b.type });
        continue;
      }
      for (const inp of spec.inputs) {
        if (inp.optional || inp.repeated || inp.kind === "statement") continue;
        if (!b.inputs?.[inp.name]?.block) add("missing_input", "error", b.id, { input: inp.name });
      }
      const f = b.fields ?? {};
      if (b.type === "controls_if" && !b.inputs?.IF0?.block)
        add("missing_input", "error", b.id, { input: "IF0" });
      if (b.type === "hb_play_trajectory") {
        const take = this.takes.find((x) => x.meta.id === f.TRAJECTORY);
        if (!take) add("unknown_trajectory", "error", b.id, { trajectory: f.TRAJECTORY });
        else if (take.meta.status === "draft")
          add("trajectory_draft", "error", b.id, { trajectory: take.meta.name });
        else if (take.meta.status === "needs_check")
          add("trajectory_needs_check", "error", b.id, { trajectory: take.meta.name });
        if (num(f.SPEED as Scalar) > 100) {
          if (this.sim.profile?.follower.allow_fast_replay)
            add("fast_replay", "confirm", b.id, { speed: f.SPEED });
          else add("fast_replay_not_allowed", "error", b.id, { speed: f.SPEED });
        }
      }
      if (
        (b.type === "hb_move_to_pose" || b.type === "hb_near_pose") &&
        !this.poses.some((p) => p.name === f.POSE)
      )
        add("unknown_pose", "error", b.id, { pose: f.POSE });
      if (
        (b.type === "hb_camera_sees" || b.type === "hb_detector_confidence") &&
        typeof f.DETECTOR === "string"
      ) {
        const d = this.detectors.find((x) => x.id === f.DETECTOR);
        if (!d) add("unknown_detector", "error", b.id, { detector: f.DETECTOR });
        else if (typeof f.LABEL === "string" && f.LABEL && !d.labels.includes(f.LABEL))
          add("unknown_label", "error", b.id, { label: f.LABEL, detector: d.name });
      }
      if (b.type === "hb_button_pressed" && !buttons.some((x) => x.name === f.BUTTON))
        add("unknown_button", "error", b.id, { button: f.BUTTON });
      if (b.type === "hb_relax_arm" && loopDepth.get(b.id)) add("relax_in_loop", "confirm", b.id);
      if ((b.type === "hb_go_home" || b.type === "hb_relax_arm") && !this.sim.profile?.follower.rest_pose)
        add("no_rest_pose", "error", b.id);
      if (b.type === "hb_repeat_forever") {
        const inner = [...walkBlocks({ blocks: { blocks: b.inputs?.DO?.block ? [b.inputs.DO.block] : [] } })];
        if (
          !inner.some(
            (x) =>
              MOTION_TYPES.has(x.type) ||
              x.type === "hb_wait" ||
              x.type === "hb_wait_until" ||
              x.type === "hb_ask_operator",
          )
        )
          add("busy_loop", "error", b.id);
      }
    }
    return issues;
  }

  // ------------------------------------------------------------------ programs: run
  startRun(id: string, req: RunProgramRequest): Session {
    const p = this.program(id);
    if (this.run) throw new MockProblem(409, "busy", { state: "programming" });
    const issues = this.check(asEditorDoc(p.editor), p.buttons);
    const blocking = issues.filter(
      (i) => i.severity === "error" || (i.severity === "confirm" && !(req.confirm ?? []).includes(i.id)),
    );
    if (blocking.length)
      throw new MockProblem(422, "program_invalid", { issues: blocking.map((i) => i.id) }, blocking);
    const dry = Boolean(req.dry_run);
    if (!dry) {
      if (this.sim.settings.programs.require_dry_run && p.dry_run_version !== p.version)
        throw new MockProblem(409, "dry_run_required");
      this.sim.requireIdle();
      this.sim.requireCool();
    }
    const doc = asEditorDoc(p.editor);
    const n = ++this.seq;
    const rid = runId(n);
    const vars = new Map((doc.variables ?? []).map((v) => [v.id, { name: v.name, type: v.type ?? "" }]));
    const keys = [...(referencedValues(doc, CATALOG).get("key") ?? [])].sort();
    const state: ProgramState = {
      run_id: rid,
      program_id: p.id,
      version: p.version,
      dry_run: dry,
      status: "starting",
      block_id: null,
      block_kind: null,
      t: 0,
      steps: 0,
      variables: Object.fromEntries([...vars.values()].map((v) => [v.name, v.type === "String" ? "" : 0])),
      conditions: [],
      waiting: null,
      ask: null,
      buttons: p.buttons,
      keys,
      message: null,
    };
    const summaryRow: ProgramRunSummary = {
      run_id: rid,
      program_id: p.id,
      version: p.version,
      started_at: new Date().toISOString(),
      ended_at: null,
      outcome: null,
      dry_run: dry,
      steps: 0,
      faults: 0,
    };
    const run: Run = {
      state,
      doc,
      vars,
      started: this.sim.t,
      gen: this.exec(startBlocks(doc)[0]?.inputs?.DO?.block),
      wait: null,
      waitSince: 0,
      latches: { buttons: new Set(), keys: new Set() },
      answer: null,
      fakes: { detectors: {}, gripper_holding: null, clear: false },
      stopRequested: false,
      lastBroadcast: -1,
      seq: 0,
      lines: [],
      summary: summaryRow,
      msgSeen: new Map(),
      session: !dry,
    };
    this.run = run;
    this.runs.unshift(summaryRow);
    this.runLogs.set(rid, run.lines);
    const session = this.newSession("program", req.fps ?? 30, "running", null);
    session.program = p.id;
    if (!dry) this.sim.enterSession(session, "programming", "running");
    this.log("info", "start", null, `program ${p.id} v${p.version}${dry ? " (dry run)" : ""}`, {
      program_id: p.id,
      version: p.version,
      dry_run: dry,
    });
    state.status = "running";
    this.broadcastState();
    return session;
  }

  current(): ProgramState | null {
    return this.run ? structuredClone(this.run.state) : null;
  }

  /** `null` when the program has not run since the Station started; 404 for no such program. */
  stateOf(id: string): ProgramState | null {
    if (this.run?.state.program_id === id) return structuredClone(this.run.state);
    const last = this.lastState.get(id);
    if (!last) {
      this.program(id);
      return null;
    }
    return structuredClone(last);
  }

  private active(id: string): Run {
    const run = this.run;
    if (run?.state.program_id !== id) throw new MockProblem(409, "busy", { state: this.sim.state });
    return run;
  }

  pause(id: string): ProgramState {
    const run = this.active(id);
    if (run.state.status === "running" || run.state.status === "waiting") {
      run.state.status =
        run.wait && run.wait.info !== "motion" && run.wait.info !== "run_model" ? "paused" : "pausing";
      this.setSub(run.state.status === "paused" ? "paused" : null);
      this.broadcastState();
    }
    return structuredClone(run.state);
  }

  resume(id: string): ProgramState {
    const run = this.active(id);
    if (run.state.status === "paused" || run.state.status === "pausing") {
      run.state.status = run.wait && run.wait.info !== "tick" ? "waiting" : "running";
      this.setSub(run.state.status === "waiting" ? "waiting" : "running");
      this.broadcastState();
    }
    return structuredClone(run.state);
  }

  stopProgram(id: string): ProgramState {
    const run = this.active(id);
    this.finish(run, "stopped", "stopped by the operator");
    return structuredClone(run.state);
  }

  input(id: string | null, ev: OperatorInput): ProgramState {
    const run = id ? this.active(id) : this.run;
    if (!run) throw new MockProblem(409, "busy", { state: this.sim.state });
    if (ev.kind === "button") {
      if (!run.state.buttons.some((b) => b.name === ev.value))
        throw new MockProblem(422, "validation_failed");
      run.latches.buttons.add(ev.value);
    } else if (ev.kind === "key") {
      if (ev.value === " ") throw new MockProblem(422, "validation_failed");
      run.latches.keys.add(ev.value);
    } else {
      if (!run.state.ask?.choices.includes(ev.value))
        throw new MockProblem(409, "busy", { state: this.sim.state });
      run.answer = ev.value;
    }
    this.log("info", "input", null, `${ev.kind} ${ev.value}`, { kind: ev.kind, value: ev.value });
    return structuredClone(run.state);
  }

  fake(id: string, f: FakeConditions): ProgramState {
    const run = this.active(id);
    if (!run.state.dry_run) throw new MockProblem(409, "dry_run_required");
    if (f.clear) run.fakes = { detectors: {}, gripper_holding: null, clear: false };
    run.fakes = {
      detectors: { ...run.fakes.detectors, ...(f.detectors ?? {}) },
      gripper_holding: f.gripper_holding ?? run.fakes.gripper_holding ?? null,
      clear: false,
    };
    return structuredClone(run.state);
  }

  /** E-stop (any source, including a dry run): abort within the tick, never resume. */
  onEstop(): void {
    if (this.record || this.play) {
      this.record = null;
      this.play = null;
    }
    if (this.run) this.finish(this.run, "estopped", "e-stop");
  }

  /** Sessions this mock drives itself (MockStation leaves their phases alone). */
  ownsSession(kind: Session["kind"] | undefined): boolean {
    return kind === "traj_record" || kind === "traj_play" || kind === "program";
  }

  // ------------------------------------------------------------------ time
  step(dt: number): void {
    const rec = this.record;
    if (rec) {
      rec.t += dt;
      rec.acc += dt;
      if (rec.phase === "countdown" && rec.t >= (rec.req.countdown_s ?? 3)) {
        rec.phase = "capture";
        rec.t = 0;
        this.sim.setSub("capture");
        this.recordMsg(false, null);
      } else if (rec.phase === "capture") {
        const fps = rec.req.fps ?? 30;
        const n = Math.round(rec.t * fps) - rec.ts.length;
        for (let k = 0; k < n; k += 1) {
          rec.ts.push(rec.ts.length / fps);
          rec.rows.push(fx.MOTORS.map((_, i) => this.sim.jointPos(i)));
        }
        rec.session.episode.elapsed_s = rec.t;
        if (rec.t >= (rec.req.limit_s ?? 60)) {
          this.finishRecord();
          return;
        }
      }
      if (rec.acc >= 0.2) {
        rec.acc = 0;
        this.recordMsg(false, null);
      }
    }
    const play = this.play;
    if (play) {
      play.t += dt;
      const dur = (play.take.meta.duration_s * 100) / play.speed;
      if (play.session.episode.phase === "approach" && play.t >= play.approach) {
        play.session.episode = { ...play.session.episode, phase: "replay", elapsed_s: 0, limit_s: dur };
        this.sim.setSub("replay");
      } else if (play.session.episode.phase === "replay") {
        play.session.episode.elapsed_s = play.t - play.approach;
        if (play.t - play.approach >= dur) {
          if (play.check) play.take.checkedReplay = true;
          this.play = null;
          this.sim.endSession("completed");
        }
      }
    }
    const run = this.run;
    if (run) this.advance(run);
  }

  private advance(run: Run): void {
    run.state.t = Math.round((this.sim.t - run.started) * 1000) / 1000;
    if (run.state.status === "paused") {
      this.maybeBroadcast(run);
      return;
    }
    for (let guard = 0; guard < 500 && this.run === run; guard += 1) {
      const w = run.wait;
      if (w) {
        if (w.timeout !== null && run.state.t - run.waitSince >= w.timeout && !w.done()) {
          run.wait = null;
          this.resumeWith(run, new Timeout(w.block));
          continue;
        }
        if (!w.done()) break;
        run.wait = null;
        if (w.info === "tick") {
          this.resumeWith(run, undefined);
          break; // a loop iteration yields to the owner: at most one per step
        }
      }
      this.resumeWith(run, undefined);
    }
    if (this.run === run) this.maybeBroadcast(run);
  }

  private resumeWith(run: Run, value: Timeout | undefined): void {
    let r: IteratorResult<Wait, void>;
    try {
      r = value ? run.gen.throw(value) : run.gen.next();
    } catch (e) {
      if (e instanceof StopSignal) this.finish(run, e.outcome, e.reason);
      else if (e instanceof Timeout) this.finish(run, "timeout", "timeout");
      else this.finish(run, "failed", e instanceof Error ? e.message : String(e));
      return;
    }
    if (r.done) {
      this.finish(run, "completed", null);
      return;
    }
    run.wait = r.value;
    run.waitSince = run.state.t;
    if (r.value.info !== "tick") {
      const waitKind = r.value.info;
      run.state.waiting = {
        kind: waitKind,
        block_id: r.value.block,
        since_s: run.state.t,
        timeout_s: r.value.timeout,
      };
      if (run.state.status === "running") {
        if (waitKind !== "motion" && waitKind !== "run_model") run.state.status = "waiting";
        this.setSub(
          waitKind === "motion" || waitKind === "run_model" ? (r.value.phase ?? "replay") : "waiting",
        );
      }
      this.broadcastState();
    }
  }

  private maybeBroadcast(run: Run): void {
    if (run.state.t - run.lastBroadcast >= 0.2) this.broadcastState();
  }

  private broadcastState(): void {
    const run = this.run;
    if (!run) return;
    run.lastBroadcast = run.state.t;
    run.summary.steps = run.state.steps;
    this.sim.broadcastMsg({ type: "program_state", ...structuredClone(run.state) });
  }

  private setSub(sub: Phase | null): void {
    if (this.run?.session && sub) this.sim.setSub(sub);
  }

  private finish(run: Run, outcome: ProgramState["status"], message: string | null): void {
    if (this.run !== run) return;
    run.state.status = outcome;
    run.state.message = message;
    run.state.waiting = null;
    run.state.ask = null;
    run.summary.ended_at = new Date().toISOString();
    run.summary.outcome = outcome as ProgramRunSummary["outcome"];
    run.summary.steps = run.state.steps;
    if (outcome === "failed" || outcome === "estopped" || outcome === "timeout") run.summary.faults += 1;
    this.log(
      outcome === "completed" || outcome === "stopped" ? "info" : "error",
      "end",
      run.state.block_id,
      outcome,
      { outcome },
    );
    // A dry run passes when it completes or the operator stops it (a `repeat forever` program
    // never completes on its own); faults, timeouts and e-stops do not count.
    if ((outcome === "completed" || outcome === "stopped") && run.state.dry_run) {
      const p = this.programs.find((x) => x.id === run.state.program_id);
      if (p?.version === run.state.version) p.dry_run_version = p.version;
    }
    this.broadcastState();
    this.lastState.set(run.state.program_id, structuredClone(run.state));
    this.run = null;
    if (run.session && outcome !== "estopped") this.sim.endSession(outcome);
  }

  private log(
    level: ProgramLogLine["level"],
    kind: ProgramLogLine["kind"],
    block: string | null,
    message: string,
    data: Record<string, unknown> = {},
  ): void {
    const run = this.run;
    if (!run) return;
    const line: ProgramLogLine = {
      run_id: run.state.run_id,
      seq: ++run.seq,
      t: run.state.t,
      level,
      kind,
      block_id: block,
      message,
      data,
    };
    run.lines.push(line);
    this.sim.broadcastMsg({ type: "program_log", ...line });
  }

  private newSession(kind: Session["kind"], fps: number, phase: Phase, limit: number | null): Session {
    const s: Session = {
      id: `s_mock_${kind}_${++this.seq}`,
      kind,
      started_at: new Date().toISOString(),
      fps,
      episode: { index: 0, of: 1, saved: 0, phase, elapsed_s: 0, limit_s: limit },
      dataset: null,
      model: null,
      task: "",
      controls: { next: false, rerecord: false, stop: true },
      outcome: "running",
    };
    return s;
  }

  // ------------------------------------------------------------------ interpreter
  private *exec(first: SBlock | undefined): Generator<Wait, void> {
    for (let b = first; b; b = b.next?.block) yield* this.stmt(b);
  }

  private enter(b: SBlock): void {
    const run = this.run;
    if (!run) throw new StopSignal("stopped", null);
    run.state.block_id = b.id;
    run.state.block_kind = SPECS.get(b.type)?.ast ?? b.type;
    run.state.steps += 1;
    if (run.state.status === "waiting") {
      run.state.status = "running";
      this.setSub("running");
    }
    run.state.waiting = null;
    this.log("info", "block", b.id, run.state.block_kind);
    this.broadcastState();
  }

  private *pausePoint(): Generator<Wait, void> {
    const run = this.run;
    if (!run) return;
    if (run.state.status === "pausing") {
      run.state.status = "paused";
      this.setSub("paused");
      this.broadcastState();
    }
    if (run.state.status === "paused")
      yield {
        info: "wait",
        block: run.state.block_id ?? "",
        timeout: null,
        done: () => run.state.status !== "paused",
      };
  }

  private motion(b: SBlock, seconds: number, phase: Phase): Wait {
    const run = this.run;
    const until = (run?.state.t ?? 0) + seconds;
    this.log("info", "motion", b.id, `${b.type} ${seconds.toFixed(1)} s`, { seconds });
    return {
      info: "motion",
      block: b.id,
      timeout: null,
      done: () => (this.run?.state.t ?? Infinity) >= until,
      phase,
    };
  }

  private *stmt(b: SBlock): Generator<Wait, void> {
    yield* this.pausePoint();
    this.enter(b);
    const f = b.fields ?? {};
    const input = (name: string) => b.inputs?.[name]?.block;
    switch (b.type) {
      case "hb_play_trajectory": {
        const take = this.takes.find((x) => x.meta.id === f.TRAJECTORY);
        if (!take) throw new StopSignal("failed", "unknown trajectory");
        yield this.motion(b, 0.6, "approach");
        yield this.motion(b, (take.meta.duration_s * 100) / Math.max(10, num(f.SPEED as Scalar)), "replay");
        return;
      }
      case "hb_move_to_pose":
        yield this.motion(b, 1.5, "approach");
        return;
      case "hb_gripper":
        yield this.motion(b, 0.5, "replay");
        return;
      case "hb_go_home":
        yield this.motion(b, 1.5, "approach");
        return;
      case "hb_relax_arm":
        yield this.motion(b, 1, "approach");
        return;
      case "hb_run_model_for":
        yield this.motion(b, num(f.SECONDS as Scalar), "episode");
        return;
      case "hb_run_model_until": {
        const timeout = num((f.TIMEOUT as Scalar | undefined) ?? 30);
        try {
          yield {
            info: "run_model",
            block: b.id,
            timeout,
            done: () => this.cond(input("UNTIL")),
            phase: "episode",
          };
        } catch (e) {
          if (!(e instanceof Timeout)) throw e;
          if (!input("ON_TIMEOUT")) throw new StopSignal("timeout", "run model timed out");
          yield* this.exec(input("ON_TIMEOUT"));
        }
        return;
      }
      case "controls_if": {
        const n = num((b.extraState?.elseIfCount as number | undefined) ?? 0);
        for (let i = 0; i <= n; i += 1) {
          if (this.cond(input(`IF${i}`))) {
            yield* this.exec(input(`DO${i}`));
            return;
          }
        }
        if (input("ELSE")) yield* this.exec(input("ELSE"));
        return;
      }
      case "controls_repeat_ext": {
        const times = Math.floor(num(this.value(input("TIMES"))));
        for (let i = 0; i < times; i += 1) {
          yield* this.exec(input("DO"));
          yield { info: "tick", block: b.id, timeout: null, done: () => true };
        }
        return;
      }
      case "hb_repeat_forever":
        for (;;) {
          yield* this.exec(input("DO"));
          yield { info: "tick", block: b.id, timeout: null, done: () => true };
        }
      case "controls_whileUntil": {
        const until = f.MODE === "UNTIL";
        while (this.cond(input("BOOL")) !== until) {
          yield* this.exec(input("DO"));
          yield { info: "tick", block: b.id, timeout: null, done: () => true };
        }
        return;
      }
      case "hb_wait": {
        const until = (this.run?.state.t ?? 0) + num(this.value(input("SECONDS")));
        yield {
          info: "wait",
          block: b.id,
          timeout: null,
          done: () => (this.run?.state.t ?? Infinity) >= until,
        };
        return;
      }
      case "hb_wait_until": {
        const timeout = num((f.TIMEOUT as Scalar | undefined) ?? this.sim.settings.programs.wait_timeout_s);
        let lastEval = -1;
        let value = false;
        try {
          yield {
            info: "wait_until",
            block: b.id,
            timeout,
            done: () => {
              const t = this.run?.state.t ?? 0;
              if (t - lastEval >= 0.1) {
                lastEval = t;
                value = this.cond(input("COND"));
              }
              return value;
            },
          };
        } catch (e) {
          if (!(e instanceof Timeout)) throw e;
          this.log("warn", "timeout", b.id, "wait until timed out");
          if (!input("ON_TIMEOUT")) throw new StopSignal("timeout", "wait until timed out");
          yield* this.exec(input("ON_TIMEOUT"));
        }
        return;
      }
      case "hb_ask_operator": {
        const run = this.run;
        if (!run) return;
        const choices = fstr(f.CHOICES, "")
          .split(",")
          .map((c) => c.trim())
          .filter(Boolean)
          .slice(0, 8);
        run.answer = null;
        run.state.ask = { block_id: b.id, question: fstr(f.QUESTION, ""), choices };
        const timeout =
          f.TIMEOUT === undefined || f.TIMEOUT === null || f.TIMEOUT === "" ? null : num(f.TIMEOUT as Scalar);
        try {
          yield { info: "ask", block: b.id, timeout, done: () => run.answer !== null };
        } catch (e) {
          if (!(e instanceof Timeout)) throw e;
          throw new StopSignal("timeout", "no answer");
        } finally {
          run.state.ask = null;
        }
        this.setVar(f.VAR, answerOf(run));
        return;
      }
      case "hb_stop_program":
        throw new StopSignal("stopped", "stop block");
      case "variables_set":
        this.setVar(f.VAR, this.value(input("VALUE")));
        return;
      case "math_change": {
        const name = this.varName(f.VAR);
        this.setVar(f.VAR, num(this.run?.state.variables[name]) + num(this.value(input("DELTA"))));
        return;
      }
      case "hb_log":
        this.log("info", "log", b.id, String(this.value(input("TEXT"))));
        return;
      case "hb_notify":
        this.log("info", "notify", b.id, String(this.value(input("TEXT"))), { webhook: f.WEBHOOK === true });
        return;
      case "hb_set_signal": {
        const v = this.value(input("VALUE"));
        this.setSignal(fstr(f.NAME, ""), v, "program");
        this.log("info", "signal", b.id, `${fstr(f.NAME)} = ${String(v)}`);
        return;
      }
      default:
        throw new StopSignal("failed", `unknown block ${b.type}`);
    }
  }

  private varName(field: unknown): string {
    const id = typeof field === "object" && field !== null && "id" in field ? fstr(field.id) : "";
    return this.run?.vars.get(id)?.name ?? id;
  }

  private setVar(field: unknown, value: Scalar): void {
    const run = this.run;
    if (!run) return;
    const name = this.varName(field);
    run.state.variables = { ...run.state.variables, [name]: value };
    this.log("info", "variable", run.state.block_id, `${name} = ${String(value)}`, { name, value });
  }

  private record_(b: SBlock, value: boolean | number | string | null): void {
    const run = this.run;
    if (!run) return;
    const row: ConditionValue = { block_id: b.id, value, t: run.state.t, message: null };
    run.state.conditions = [...run.state.conditions.filter((c) => c.block_id !== b.id), row].slice(-20);
  }

  private cond(b: SBlock | undefined): boolean {
    if (!b) return false;
    const run = this.run;
    const f = b.fields ?? {};
    const input = (name: string) => b.inputs?.[name]?.block;
    let v: boolean;
    switch (b.type) {
      case "logic_boolean":
        v = f.BOOL === "TRUE";
        break;
      case "logic_negate":
        v = !this.cond(input("BOOL"));
        break;
      case "logic_operation":
        v =
          f.OP === "AND"
            ? this.cond(input("A")) && this.cond(input("B"))
            : this.cond(input("A")) || this.cond(input("B"));
        break;
      case "logic_compare": {
        const a = this.value(input("A"));
        const c = this.value(input("B"));
        const op = fstr(f.OP);
        const both = typeof a === "number" && typeof c === "number";
        v =
          op === "EQ"
            ? both
              ? a === c
              : String(a) === String(c)
            : op === "NEQ"
              ? both
                ? a !== c
                : String(a) !== String(c)
              : op === "LT"
                ? num(a) < num(c)
                : op === "LTE"
                  ? num(a) <= num(c)
                  : op === "GT"
                    ? num(a) > num(c)
                    : num(a) >= num(c);
        break;
      }
      case "hb_camera_sees": {
        const d = this.detectors.find((x) => x.id === f.DETECTOR);
        if (!d) throw new StopSignal("failed", "unknown detector");
        const cam = typeof f.CAMERA === "string" && f.CAMERA ? f.CAMERA : null;
        v = this.evaluate(d.id, d.spec, cam, run?.state.dry_run).label === f.LABEL;
        break;
      }
      case "hb_button_pressed":
        v = run?.latches.buttons.delete(fstr(f.BUTTON)) ?? false;
        break;
      case "hb_key_pressed":
        v = run?.latches.keys.delete(fstr(f.KEY)) ?? false;
        break;
      case "hb_gripper_holding":
        v = run?.fakes.gripper_holding ?? false;
        break;
      case "hb_joint_compare": {
        const i = fx.MOTORS.indexOf(f.JOINT as (typeof fx.MOTORS)[number]);
        const pos = this.sim.jointPos(Math.max(0, i));
        v = f.OP === "LT" ? pos < num(f.DEG as Scalar) : pos > num(f.DEG as Scalar);
        break;
      }
      case "hb_near_pose": {
        const p = this.poses.find((x) => x.name === f.POSE);
        if (!p) throw new StopSignal("failed", "unknown pose");
        const tol = num(f.TOLERANCE as Scalar);
        v = fx.MOTORS.every((m, i) => Math.abs((p.positions[`${m}.pos`] ?? 0) - this.sim.jointPos(i)) <= tol);
        break;
      }
      case "hb_motor_temp_compare": {
        const t = this.sim.motorTemp(fstr(f.MOTOR, "any"));
        v = f.OP === "GT" ? t > num(f.TEMP as Scalar) : t < num(f.TEMP as Scalar);
        break;
      }
      case "hb_signal_equals": {
        const s = this.signals.get(fstr(f.NAME));
        const want = fstr(f.VALUE, "");
        v = s !== undefined && String(s.value) === want;
        break;
      }
      case "hb_message_received": {
        const key = `${fstr(f.SOURCE)}:${fstr(f.NAME)}`;
        const s = this.signals.get(fstr(f.NAME));
        const seen = run?.msgSeen.get(key) ?? this.signalSeqAtStart(run);
        const now = s && s.source === f.SOURCE ? s.seq : seen;
        v = now > seen;
        run?.msgSeen.set(key, now);
        break;
      }
      default:
        throw new StopSignal("failed", `not a condition: ${b.type}`);
    }
    this.record_(b, v);
    return v;
  }

  private signalSeqAtStart(run: Run | null): number {
    if (!run) return 0;
    const at = run.msgSeen.get("__start");
    if (at !== undefined) return at;
    run.msgSeen.set("__start", this.signalSeq);
    return this.signalSeq;
  }

  private value(b: SBlock | undefined): Scalar {
    if (!b) return 0;
    const f = b.fields ?? {};
    const input = (name: string) => b.inputs?.[name]?.block;
    switch (b.type) {
      case "math_number":
        return num(f.NUM as Scalar);
      case "text":
        return fstr(f.TEXT, "");
      case "variables_get":
        return this.run?.state.variables[this.varName(f.VAR)] ?? 0;
      case "math_arithmetic": {
        const a = num(this.value(input("A")));
        const c = num(this.value(input("B")));
        const r =
          { ADD: a + c, MINUS: a - c, MULTIPLY: a * c, DIVIDE: c === 0 ? NaN : a / c, POWER: a ** c }[
            fstr(f.OP)
          ] ?? 0;
        if (!Number.isFinite(r)) throw new StopSignal("failed", "division by zero");
        return r;
      }
      case "math_modulo": {
        const c = num(this.value(input("DIVISOR")));
        if (c === 0) throw new StopSignal("failed", "division by zero");
        return num(this.value(input("DIVIDEND"))) % c;
      }
      case "math_random_int": {
        const lo = Math.ceil(num(this.value(input("FROM"))));
        const hi = Math.floor(num(this.value(input("TO"))));
        return lo + Math.floor(Math.random() * (hi - lo + 1));
      }
      case "text_join": {
        const n = num((b.extraState?.itemCount as number | undefined) ?? 0);
        return Array.from({ length: n }, (_, i) => String(this.value(input(`ADD${i}`)))).join("");
      }
      case "hb_joint_value": {
        const i = fx.MOTORS.indexOf(f.JOINT as (typeof fx.MOTORS)[number]);
        return this.sim.jointPos(Math.max(0, i));
      }
      case "hb_motor_temp":
        return this.sim.motorTemp(fstr(f.MOTOR, "any"));
      case "hb_detector_confidence": {
        const d = this.detectors.find((x) => x.id === f.DETECTOR);
        if (!d) throw new StopSignal("failed", "unknown detector");
        const r = this.evaluate(
          d.id,
          d.spec,
          typeof f.CAMERA === "string" && f.CAMERA ? f.CAMERA : null,
          this.run?.state.dry_run,
        );
        return typeof f.LABEL === "string" && f.LABEL ? (r.scores[f.LABEL] ?? 0) : r.confidence;
      }
      case "hb_signal_value": {
        const s = this.signals.get(fstr(f.NAME));
        return s?.value ?? 0;
      }
      default:
        return this.cond(b) ? 1 : 0;
    }
  }
}

/** A new, empty program document for the editor (re-exported for the mock's create path). */
export { emptyProgram };
