/**
 * MockStation: an in-page simulation of the Station backend for tests and the dev server in
 * mock mode. It implements the §4.4 state machine, the §5.3 control stream (joints, telemetry with a
 * heating scenario and the ThermalGuard safe stop, alerts, sessions, jobs, calibration) and the
 * §5.4 video stream (HSF1 binary frames carrying the tick of the frames handed to the policy).
 * Time only advances through `step(dt)` (tests) or `start()` (browser, 20 Hz).
 */
import type {
  AlertMsg,
  Arm,
  ArmCalibrationCheck,
  CalibrationCheck,
  CalibrationMsg,
  DeviceLost,
  FrameHeader,
  Job,
  Level,
  LocalDatasetDetail,
  ModelEntry,
  MotorSample,
  RecordRequest,
  RobotProfile,
  Phase,
  PoseCompare,
  ReconnectResult,
  RunRequest,
  ServerLink,
  Session,
  SessionEnd,
  Status,
  StationState,
} from "../api/types";
import { omit } from "../api/types";

export const UNPAIRED: ServerLink = {
  paired: false,
  url: null,
  web_url: null,
  workspace_id: null,
  workspace: null,
  workspace_name: null,
  token_prefix: null,
  scopes: [],
};

export function pairedLink(url: string): ServerLink {
  return {
    paired: true,
    url: `${url}/api/v1`,
    web_url: url,
    workspace_id: "ws_lab",
    workspace: "lab",
    workspace_name: "Lab",
    token_prefix: "hbp_mock…",
    scopes: ["datasets:write", "models:read", "runs:read"],
  };
}
import type { SocketLike } from "../ws/control";
import { encodeFrame } from "../ws/video";
import * as fx from "./fixtures";
import { MockPrograms } from "./programs";

/** Replay: the approach to the first recorded pose, then the episode (the Station's phases). */
const REPLAY_APPROACH_S = 1.5;
const REPLAY_S = 30;

export class MockProblem extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly params: Record<string, unknown> = {},
    /** Problem `errors` (e.g. the blocking CheckIssues of `program_invalid`). */
    readonly errors: Record<string, unknown>[] | null = null,
  ) {
    super(code);
  }
}

export type FrameSource = (
  cam: string,
  tick: number,
  w: number,
  h: number,
) => Uint8Array | Promise<Uint8Array>;

export interface MockOptions {
  connected?: boolean;
  paired?: boolean;
  /** °C per second added to follower elbow_flex while the arm moves (the "heat" scenario). */
  heatRate?: number;
  startTemp?: number;
  deadman?: boolean;
  frameSource?: FrameSource;
  datasets?: LocalDatasetDetail[];
  models?: ModelEntry[];
  /** Calibration scenario: "ok" (both arms calibrated), "lelab" (the motors carry LeLab's files),
   *  "fresh" (no calibration at all). */
  calib?: "ok" | "lelab" | "fresh";
  /** The pose check finds elbow_flex 35° apart (a wrong calibration file). */
  poseOff?: boolean;
  /** Start in the "device lost" error (the follower's USB adapter went away after torque-on). */
  lost?: boolean;
}

const MIN_RANGE = 100;

const OPEN = 1;

/** Fake WebSocket attached to the mock station. */
export class MockSocket implements SocketLike {
  readyState = 0;
  binaryType: BinaryType = "blob";
  onopen: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  sent: string[] = [];

  constructor(
    readonly url: string,
    private readonly station: MockStation,
  ) {
    setTimeout(() => {
      if (this.readyState !== 0) return;
      this.readyState = OPEN;
      // The server registers the socket (and says hello) before the client sees "open".
      station.attach(this);
      this.onopen?.(new Event("open"));
    }, 0);
  }

  send(data: string): void {
    this.sent.push(data);
    this.station.receive(this, data);
  }

  close(): void {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.station.detach(this);
    this.onclose?.({ code: 1000 } as CloseEvent);
  }

  /** Server → client. */
  deliver(data: string | ArrayBuffer): void {
    if (this.readyState !== OPEN) return;
    this.onmessage?.({ data } as MessageEvent);
  }

  /** Simulates a dropped connection. */
  drop(): void {
    this.close();
  }
}

interface SessionRt {
  s: Session;
  phaseT: number;
  rec?: RecordRequest;
  run?: RunRequest;
  countdown: number;
  /** The operator pressed Stop: the session ends once the episode is saved. */
  stopping?: boolean;
}

/** Simulated seconds to encode one episode after Stop. */
const SAVE_S = 1;

const tinyJpeg = new Uint8Array([0xff, 0xd8, 0xff, 0xd9]);

export class MockStation {
  state: StationState = "disconnected";
  sub: Phase | null = null;
  lastSession: SessionEnd | null = null;
  reason: string | null = null;
  detail: string | null = null;
  profiles: RobotProfile[] = [structuredClone(fx.robot)];
  activeId: string | null = null;
  torque = false;
  calibrated: Record<Arm, boolean> = { follower: true, leader: true };
  server: ServerLink = { ...UNPAIRED };
  datasets: LocalDatasetDetail[];
  models: ModelEntry[];
  loaded: string | null = null;
  settings = structuredClone(fx.settings);
  jobs: Job[] = [];
  sessionsHist = [...fx.sessions];
  session: SessionRt | null = null;
  temps: Record<Arm, Record<string, number>>;
  /** Consecutive samples at or above critical, per `${arm}.${motor}` (§4.5.3: 2 in a row). */
  critStreak: Record<string, number> = {};
  levels: Record<string, Level> = {};
  alerts = new Map<string, AlertMsg>();
  calib: CalibrationMsg | null = null;
  calibT0 = 0;
  calibScenario: "ok" | "lelab" | "fresh" = "ok";
  poseOff = false;
  lost: DeviceLost | null = null;
  /** An e-stop ended a motion: the UI offers "Return to rest pose" (field report 0.2.8). */
  interrupted = false;
  t = 0;
  tick = 0;
  heatRate: number;
  deadman: boolean;
  lastHeartbeat = 0;
  lastEstopAt = -Infinity;
  frameSource: FrameSource;
  private control = new Set<MockSocket>();
  private video = new Map<MockSocket, { cameras: string[]; width: number; fps: number }>();
  private acc = { joints: 0, telemetry: 0, video: 0, session: 0, calib: 0 };
  private timer: ReturnType<typeof setInterval> | null = null;
  private jobSeq = 0;
  /** Trajectories, poses, detectors, signals and block programs (station-programs.md). */
  readonly programs: MockPrograms;

  constructor(opts: MockOptions = {}) {
    this.programs = new MockPrograms(this);
    this.heatRate = opts.heatRate ?? 0;
    this.deadman = opts.deadman ?? false;
    this.frameSource = opts.frameSource ?? (() => tinyJpeg);
    this.datasets = opts.datasets ?? [fx.dataset()];
    this.models = opts.models ?? [structuredClone(fx.model)];
    const base = opts.startTemp ?? 36;
    this.temps = {
      follower: Object.fromEntries(fx.MOTORS.map((m, i) => [m, base + i])),
      leader: Object.fromEntries(fx.MOTORS.map((m) => [m, 31])),
    };
    if (opts.paired)
      this.server = {
        ...pairedLink("https://hibiscus.example.org"),
      };
    this.calibScenario = opts.calib ?? "ok";
    this.poseOff = opts.poseOff ?? false;
    if (this.calibScenario !== "ok") this.calibrated = { follower: false, leader: false };
    if (opts.connected) this.doConnect("desk_so101");
    if (opts.connected && opts.lost) this.loseDevice("follower", true);
  }

  // ------------------------------------------------------------------ sockets
  socketFactory = (url: string): SocketLike => new MockSocket(url, this);

  attach(sock: MockSocket): void {
    if (sock.url.endsWith("/ws/video")) {
      this.video.set(sock, { cameras: [], width: 320, fps: 12 });
      return;
    }
    this.control.add(sock);
    this.lastHeartbeat = this.t;
    sock.deliver(JSON.stringify({ type: "hello", v: 1, status: this.status() }));
    for (const a of this.alerts.values()) sock.deliver(JSON.stringify(a));
  }

  detach(sock: MockSocket): void {
    this.control.delete(sock);
    this.video.delete(sock);
  }

  receive(sock: MockSocket, data: string): void {
    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(data) as Record<string, unknown>;
    } catch {
      return;
    }
    if (this.video.has(sock)) {
      if (msg.type === "subscribe") {
        this.video.set(sock, {
          cameras: Array.isArray(msg.cameras) ? (msg.cameras as string[]) : [],
          width: typeof msg.width === "number" ? msg.width : 320,
          fps: typeof msg.fps === "number" ? msg.fps : 12,
        });
      }
      return;
    }
    switch (msg.type) {
      case "heartbeat":
      case "hello":
        this.lastHeartbeat = this.t;
        return;
      case "estop":
        this.estop("user");
        return;
      case "control":
        try {
          this.controlAction(msg.action as "next" | "rerecord" | "stop");
        } catch {
          /* ignored over WS */
        }
        return;
      case "program_input":
        try {
          this.programs.input(null, {
            kind: msg.kind as "button" | "key" | "answer",
            value: String(msg.value),
          });
        } catch (e) {
          if (e instanceof MockProblem)
            sock.deliver(JSON.stringify({ type: "error", code: e.code, message: e.code }));
        }
        return;
      default:
        return;
    }
  }

  get controlSockets(): MockSocket[] {
    return [...this.control];
  }

  private broadcast(msg: unknown): void {
    const s = JSON.stringify(msg);
    for (const c of this.control) c.deliver(s);
  }

  /** Server → every control socket (used by MockPrograms). */
  broadcastMsg(msg: unknown): void {
    this.broadcast(msg);
  }

  // ------------------------------------------------------------------ status
  get profile(): RobotProfile | undefined {
    return this.profiles.find((p) => p.id === this.activeId);
  }

  hottest(): Status["health"] {
    let best: { arm: Arm; motor: string; temp_c: number } | null = null;
    for (const arm of ["follower", "leader"] as Arm[]) {
      if (arm === "leader" && !this.profile?.leader) continue;
      for (const [m, v] of Object.entries(this.temps[arm])) {
        if (!best || v > best.temp_c) best = { arm, motor: m, temp_c: Math.round(v) };
      }
    }
    const order: Level[] = ["ok", "warn", "hot", "critical"];
    let level: Level = "ok";
    for (const l of Object.values(this.levels)) if (order.indexOf(l) > order.indexOf(level)) level = l;
    return { level, hottest: this.activeId ? best : null };
  }

  status(): Status {
    const p = this.profile;
    const connected = this.activeId !== null && this.state !== "disconnected" && this.state !== "error";
    return {
      station: { version: "0.1.0", lerobot: "0.7.1", device: "cpu", mock: true, home: "~/.hibiscus/station" },
      state: this.state,
      sub: this.sub,
      reason: this.reason,
      detail: this.detail,
      robot: p
        ? {
            id: p.id,
            name: p.name,
            mock: p.follower.type === "hibiscus_mock_follower",
            connected,
            follower_torque: this.torque,
            arms: {
              follower: { port: p.follower.port, calibrated: this.calibrated.follower },
              ...(p.leader ? { leader: { port: p.leader.port, calibrated: this.calibrated.leader } } : {}),
            },
          }
        : null,
      cameras:
        connected && p
          ? Object.entries(p.cameras).map(([name, c]) => ({
              name,
              type: c.type,
              streaming: true,
              width: c.width,
              height: c.height,
              fps: c.fps,
              stale: false,
              error: null,
            }))
          : [],
      health: this.hottest(),
      alerts: [...this.alerts.values()].map((a) => omit(a, "type")),
      session: this.session?.s ?? null,
      last_session: this.lastSession,
      server: { paired: this.server.paired, url: this.server.web_url, workspace: this.server.workspace },
      loaded_model: this.loaded,
      program: this.programs.current(),
      lost: this.lost,
      interrupted: this.interrupted,
    };
  }

  private setState(
    state: StationState,
    extra: { sub?: Phase | null; reason?: string | null; detail?: string | null } = {},
  ): void {
    this.state = state;
    this.sub = extra.sub ?? null;
    this.reason = extra.reason ?? null;
    this.detail = extra.detail ?? null;
    this.broadcast({ type: "state", ...this.status() });
  }

  /** Enter a motion state for a session MockPrograms drives (recording_traj / playing / programming). */
  enterSession(s: Session, state: StationState, sub: Phase): void {
    this.session = { s, phaseT: 0, countdown: 0 };
    this.torque = true;
    this.lastHeartbeat = this.t;
    this.setState(state, { sub });
    this.broadcast({ type: "session", ...s });
  }

  /** Change the sub-phase of the current motion state (broadcasts `state`). */
  setSub(sub: Phase): void {
    if (this.sub === sub) return;
    this.sub = sub;
    if (this.session) this.session.s.episode = { ...this.session.s.episode, phase: sub };
    this.broadcast({ type: "state", ...this.status() });
  }

  /** Present position of follower joint `i` (degrees; gripper 0-100). */
  jointPos(i: number): number {
    return this.pos(i);
  }

  /** Follower motor temperature; "any" = the hottest motor. */
  motorTemp(motor: string): number {
    const temps = this.temps.follower;
    if (motor === "any") return Math.round(Math.max(...Object.values(temps)));
    return Math.round(temps[motor] ?? 0);
  }

  // ------------------------------------------------------------------ commands (REST)
  requireIdle(): void {
    if (this.state === "disconnected") throw new MockProblem(409, "not_connected");
    if (this.state === "estopped") throw new MockProblem(409, "estopped");
    if (this.state !== "idle") throw new MockProblem(409, "busy", { state: this.state });
  }

  requireCool(): void {
    // the Station's shape: {arm, motor, temp_c} per motor at or above "hot"
    const hot = Object.entries(this.levels)
      .filter(([, l]) => l === "hot" || l === "critical")
      .map(([k]) => {
        const [arm = "follower", motor = ""] = k.split(".");
        const temp = this.temps[arm as Arm][motor];
        return { arm, motor, temp_c: temp === undefined ? null : Math.round(temp) };
      });
    if (hot.length) throw new MockProblem(409, "motor_hot", { motors: hot });
  }

  calibrationCheck(): CalibrationCheck {
    if (this.state === "disconnected" || this.state === "error") throw new MockProblem(409, "not_connected");
    const p = this.profile;
    const arm = (a: Arm): ArmCalibrationCheck | null => {
      const id = a === "follower" ? p?.follower.calibration_id : p?.leader?.calibration_id;
      if (!p || !id) return null;
      const own = fx.calibrations.find((c) => c.arm === a && c.id === id);
      const lelab = this.calibScenario === "lelab";
      const files = fx.calibrations
        .filter((c) => c.arm === a)
        .filter((c) => this.calibScenario !== "fresh" || (c.dir ?? "").startsWith("so1"))
        .filter((c) => c !== own || this.calibScenario === "ok")
        .map((c) => ({
          ...c,
          own: c === own,
          valid: true,
          matches_motors: (c === own && this.calibrated[a]) || (lelab && (c.dir ?? "").startsWith("so101")),
          matches_other_arm: false,
        }));
      const suggestion = files.find((f) => f.matches_motors && !f.own) ?? null;
      const state = this.calibrated[a] ? "ok" : suggestion ? "adopt" : "needs_calibration";
      return {
        arm: a,
        state,
        calibrated: this.calibrated[a],
        calibration_id: id,
        file: own?.path ?? `~/.cache/huggingface/lerobot/calibration/${a}/${id}.json`,
        file_exists: Boolean(own) && this.calibScenario === "ok",
        suggestion: state === "adopt" ? suggestion : null,
        files,
        issue: this.calibrated[a] ? null : `no calibration file for ${id}`,
      };
    };
    return { arms: { follower: arm("follower"), leader: arm("leader") } };
  }

  poseCompare(): PoseCompare {
    this.requireIdle();
    for (const a of ["follower", "leader"] as const)
      if (!this.calibrated[a]) throw new MockProblem(409, "not_calibrated", { arm: a });
    const joints = fx.MOTORS.map((m, i) => {
      const f = this.pos(i);
      const off = this.poseOff && m === "elbow_flex" ? 35.2 : ((i * 7) % 5) * 0.6;
      const l = Math.round((f + off) * 10) / 10;
      const diff = Math.round(Math.abs(l - f) * 10) / 10;
      return {
        joint: m,
        follower: f,
        leader: l,
        diff,
        unit: m === "gripper" ? "%" : "deg",
        ok: diff <= 20,
      } as const;
    });
    const off = joints.filter((j) => !j.ok).map((j) => j.joint);
    const worst = joints.reduce((a, b) => (b.diff > a.diff ? b : a));
    return {
      joints: [...joints],
      threshold: 20,
      ok: off.length === 0,
      off,
      worst: off.length ? worst.joint : null,
      max_diff: worst.diff,
    };
  }

  /** The follower's (or leader's) USB adapter went away (unplug, brown-out, selective suspend). */
  loseDevice(arm: Arm, afterTorqueOn: boolean): void {
    const p = this.profile;
    if (!p) return;
    const port = arm === "follower" ? p.follower.port : (p.leader?.port ?? "");
    if (this.session) this.session = null;
    this.torque = false;
    const detail = `${arm}: the serial device ${port} was lost (Access is denied.)`;
    this.lost = {
      arm,
      port,
      error: "Access is denied.",
      identity: {
        device: port,
        vid_pid: "1a86:55d3",
        serial_number: "5A7A018791",
        description: "USB Single Serial",
      },
      robot: p.id,
      during: "teleop",
      after_torque_on: afterTorqueOn,
      t: Date.now() / 1000,
      detail,
    };
    // As the Station: the closed bus's motor alerts can never clear later, so they go now.
    this.dropAlerts((a) => a.arm !== null || a.camera !== null);
    this.levels = {};
    this.setState("error", { reason: "device_lost", detail });
  }

  /** Remove alerts like the Station does: each with an `active: false` event (QC 0.2.9 QD-23). */
  private dropAlerts(which: (a: AlertMsg) => boolean): void {
    for (const [id, a] of [...this.alerts]) {
      if (!which(a)) continue;
      this.alerts.delete(id);
      this.broadcast({ ...a, active: false });
    }
  }

  reconnect(): ReconnectResult {
    if (this.state !== "error" || !this.activeId) throw new MockProblem(409, "busy", { state: this.state });
    const p = this.profile;
    this.lost = null;
    this.torque = true;
    this.setState("idle");
    const ports: Record<string, string> = {};
    if (p) {
      ports.follower = p.follower.port;
      if (p.leader) ports.leader = p.leader.port;
    }
    return { ...this.status(), ports, port_changes: {} };
  }

  doConnect(id: string): Status {
    const p = this.profiles.find((x) => x.id === id);
    if (!p) throw new MockProblem(404, "not_found");
    if (this.activeId && this.state !== "disconnected")
      throw new MockProblem(409, "busy", { state: this.state });
    this.activeId = id;
    this.torque = true;
    this.setState("idle");
    return this.status();
  }

  disconnect(): Status {
    if (this.session) throw new MockProblem(409, "busy", { state: this.state });
    this.activeId = null;
    this.torque = false;
    this.dropAlerts(() => true);
    this.levels = {};
    this.setState("disconnected");
    return this.status();
  }

  /** POST /robots/rest-pose: the follower's present pose becomes the robot's Home (CR-2). */
  setRestPose(): { rest_pose: Record<string, number> } {
    if (this.state !== "idle") throw new MockProblem(409, "busy", { state: this.state });
    const p = this.profile;
    if (!p) throw new MockProblem(409, "not_connected", { state: this.state });
    if (!this.calibrated.follower) throw new MockProblem(409, "not_calibrated", { arm: "follower" });
    const pose = Object.fromEntries(
      fx.MOTORS.map((m, i) => [`${m}.pos`, Math.round(this.pos(i) * 100) / 100]),
    );
    p.follower.rest_pose = pose;
    return { rest_pose: pose };
  }

  setTorque(enabled: boolean): Status {
    if (this.state !== "idle" && this.state !== "estopped")
      throw new MockProblem(409, "busy", { state: this.state });
    this.torque = enabled;
    this.broadcast({ type: "state", ...this.status() });
    return this.status();
  }

  calibrationStart(arm: Arm, keep: boolean, source?: string): Status {
    this.requireIdle();
    if (keep) {
      const own = fx.calibrations.some((c) => c.arm === arm && (c.dir ?? "").startsWith("so_"));
      if (!source && this.calibScenario === "fresh" && !own) throw new MockProblem(404, "not_found", { arm });
      this.calibrated[arm] = true;
      this.broadcast({ type: "state", ...this.status() });
      return this.status();
    }
    this.calibT0 = this.t;
    this.calib = {
      type: "calibration",
      arm,
      step: "home",
      motors: Object.fromEntries(
        fx.MOTORS.map((m) => [m, { min: 2048, pos: 2048, max: 2048, full_turn: false, ok: false }]),
      ),
      warnings: [],
      min_range: MIN_RANGE,
      ready: false,
    };
    this.torque = false;
    this.setState("calibrating", { sub: "home" });
    this.broadcast(this.calib);
    return this.status();
  }

  calibrationStep(action: "set_home" | "finish_ranges" | "cancel"): Status {
    if (this.state !== "calibrating" || !this.calib)
      throw new MockProblem(409, "busy", { state: this.state });
    if (action === "cancel") {
      this.calib = null;
      this.setState("idle");
    } else if (action === "set_home") {
      this.calibT0 = this.t;
      this.calib = {
        ...this.calib,
        step: "ranges",
        motors: Object.fromEntries(
          Object.entries(this.calib.motors).map(([m, r]) => [m, { ...r, min: r.pos, max: r.pos }]),
        ),
      };
      this.setState("calibrating", { sub: "ranges" });
      this.broadcast(this.calib);
    } else {
      if (!this.calib.ready) throw new MockProblem(422, "validation_failed");
      const arm = this.calib.arm;
      this.calibrated[arm] = true;
      this.calib = {
        ...this.calib,
        step: "done",
        path: fx.calibrations.find((c) => c.arm === arm)?.path ?? null,
      };
      this.broadcast(this.calib);
      this.setState("idle");
    }
    return this.status();
  }

  startSession(kind: Session["kind"], body: Record<string, unknown>): Session {
    this.requireIdle();
    this.requireCool();
    const fps = typeof body.fps === "number" ? body.fps : 30;
    const s: Session = {
      id: `s_mock_${kind}_${++this.jobSeq}`,
      kind,
      started_at: new Date().toISOString(),
      fps,
      episode: { index: 0, of: 0, saved: 0, phase: "approach", elapsed_s: 0, limit_s: null },
      dataset: null,
      model: null,
      task: "",
      controls: { next: false, rerecord: false, stop: true },
      outcome: "running",
    };
    const rt: SessionRt = { s, phaseT: 0, countdown: 3 };
    let state: StationState = "teleop";
    if (kind === "teleop" && body.align === true) s.episode.phase = "align";
    if (kind === "rest") {
      s.episode = { index: 0, of: 1, saved: 0, phase: "approach", elapsed_s: 0, limit_s: 3 };
      state = "playing";
    } else if (kind === "record") {
      const rec = body as unknown as RecordRequest;
      rt.rec = rec;
      rt.countdown = rec.countdown_s ?? 3;
      s.dataset = rec.dataset;
      s.task = rec.task;
      s.episode = {
        index: 0,
        of: rec.num_episodes ?? 1,
        saved: 0,
        phase: "countdown",
        elapsed_s: 0,
        limit_s: rec.countdown_s ?? 3,
      };
      s.controls = { next: false, rerecord: false, stop: true };
      state = "recording";
      if (!this.datasets.some((d) => d.name === rec.dataset))
        this.datasets.push({ ...fx.dataset(rec.dataset, 0), task: rec.task });
    } else if (kind === "run") {
      const run = body as unknown as RunRequest;
      if (this.loaded !== run.model) throw new MockProblem(409, "model_not_loaded");
      rt.run = run;
      s.model = run.model;
      s.task = run.task ?? "";
      s.episode = {
        index: 0,
        of: run.num_episodes ?? 1,
        saved: 0,
        phase: "countdown",
        elapsed_s: 0,
        limit_s: 3,
      };
      state = "inferring";
    } else if (kind === "replay") {
      s.dataset = String(body.dataset);
      s.episode = {
        index: Number(body.episode),
        of: 1,
        saved: 0,
        phase: "approach", // as the Station: approach (1.5 s), then replay
        elapsed_s: 0,
        limit_s: REPLAY_APPROACH_S,
      };
      state = "replaying";
    }
    this.session = rt;
    this.torque = true;
    this.lastHeartbeat = this.t;
    if (kind !== "rest") this.interrupted = false;
    this.setState(state, { sub: s.episode.phase });
    if (kind === "teleop") rt.phaseT = 0;
    this.broadcast({ type: "session", ...s });
    return s;
  }

  controlAction(action: "next" | "rerecord" | "stop"): Session {
    const rt = this.session;
    if (!rt) throw new MockProblem(409, "busy", { state: this.state });
    const ep = rt.s.episode;
    if (action === "stop") {
      // Like the Station (field report 0.2.9): a recorded episode is saved inside the session
      // (phase "saving", the loop keeps running), then the session ends "stopped".
      if (rt.rec && ep.phase === "episode" && ep.elapsed_s > 0) {
        this.saveEpisode(rt);
        rt.stopping = true;
        rt.s.episode = { ...ep, phase: "saving" }; // the timer stays where Stop was pressed
        rt.phaseT = 0;
        rt.s.controls = { next: false, rerecord: false, stop: true };
        this.sub = "saving";
        this.broadcast({ type: "state", ...this.status() });
        this.broadcast({ type: "session", ...rt.s });
        return rt.s;
      }
      if (ep.phase !== "saving") this.endSession("stopped");
      return rt.s;
    }
    if (action === "rerecord") {
      if (!rt.rec || (ep.phase !== "episode" && ep.phase !== "reset"))
        throw new MockProblem(409, "busy", { state: this.state });
      if (ep.phase === "reset" && ep.saved > 0) {
        ep.saved -= 1;
        const d = this.datasets.find((x) => x.name === rt.s.dataset);
        if (d) {
          d.episode_list.pop();
          d.episodes -= 1;
        }
      }
      ep.index = ep.saved;
      this.phase(rt, "episode", rt.rec.episode_time_s ?? 30);
    } else if (ep.phase === "episode") {
      if (rt.rec) this.saveEpisode(rt);
      this.afterEpisode(rt);
    } else if (ep.phase === "reset") this.nextEpisode(rt);
    return rt.s;
  }

  private phase(rt: SessionRt, phase: Phase, limit: number | null): void {
    rt.s.episode = { ...rt.s.episode, phase, elapsed_s: 0, limit_s: limit };
    rt.phaseT = 0;
    const rec = Boolean(rt.rec);
    rt.s.controls = {
      next: phase === "episode" || phase === "reset",
      rerecord: rec && (phase === "episode" || phase === "reset"),
      stop: true,
    };
    this.sub = phase;
    this.broadcast({ type: "state", ...this.status() });
    this.broadcast({ type: "session", ...rt.s });
  }

  private saveEpisode(rt: SessionRt): void {
    const ep = rt.s.episode;
    const d = this.datasets.find((x) => x.name === rt.s.dataset);
    if (!d) return;
    const idx = d.episode_list.length;
    d.episode_list.push({
      index: idx,
      state: "saved",
      length_s: Math.round(ep.elapsed_s * 10) / 10,
      frames: Math.round(ep.elapsed_s * rt.s.fps),
      tasks: [rt.s.task],
      telemetry_lines: Math.round(ep.elapsed_s * 2),
      max_temp_c: {
        follower: Object.fromEntries(Object.entries(this.temps.follower).map(([m, v]) => [m, Math.round(v)])),
      },
    });
    d.episodes = d.episode_list.length;
    d.frames += Math.round(ep.elapsed_s * rt.s.fps);
    ep.saved += 1;
  }

  private afterEpisode(rt: SessionRt): void {
    const ep = rt.s.episode;
    const last = (rt.rec ? ep.saved : ep.index + 1) >= ep.of;
    if (last) {
      this.endSession("completed");
      return;
    }
    const reset = rt.rec?.reset_time_s ?? rt.run?.reset_time_s ?? 0;
    if (reset > 0) this.phase(rt, "reset", reset);
    else this.nextEpisode(rt);
  }

  private nextEpisode(rt: SessionRt): void {
    rt.s.episode.index = rt.rec ? rt.s.episode.saved : rt.s.episode.index + 1;
    this.phase(rt, "episode", rt.rec?.episode_time_s ?? rt.run?.episode_time_s ?? 30);
  }

  endSession(
    outcome: string,
    to: StationState = "idle",
    reason: string | null = null,
    detail: string | null = null,
  ): void {
    const rt = this.session;
    if (!rt) return;
    // CR-1: a user Stop holds the arm where it is; the UI offers Return Home / Relax.
    if (outcome === "stopped") this.interrupted = true;
    // Like RecordSession.end(): an e-stop (or a fault) mid-episode drops that episode; a new
    // dataset that kept no episode is removed (QC 0.2.9 QD-12).
    let summary: Record<string, unknown> = { episodes: rt.s.episode.saved };
    if (rt.rec) {
      const ep = rt.s.episode;
      const dropped = ep.phase === "episode" && ep.elapsed_s > 0;
      const d = this.datasets.find((x) => x.name === rt.s.dataset);
      const kept = Boolean(d && d.episodes > 0);
      if (d && !kept) this.datasets = this.datasets.filter((x) => x !== d);
      summary = {
        ...summary,
        dataset: rt.s.dataset,
        saved: ep.saved,
        discarded: dropped ? 1 : 0,
        dropped_in_progress: dropped,
        dataset_kept: kept,
      };
    }
    // Like the backend teardown (§5.3): state "stopping", then the final `session` message
    // (`ended: true`, phase "done" with the saved count), then the new state.
    rt.s.episode = { ...rt.s.episode, phase: "done" };
    rt.s.controls = { next: false, rerecord: false, stop: false };
    rt.s.outcome = outcome;
    this.setState("stopping");
    const peaks = Object.fromEntries(
      Object.entries(this.temps.follower).map(([m, v]) => [`follower.${m}`, Math.round(v)]),
    );
    const end: SessionEnd = {
      ...rt.s,
      reason: reason ?? outcome,
      summary,
      loop: { ticks: 0, overruns: 0, tick_ms_p95: 0, telemetry_reads: 0, telemetry_forced: 0 },
      max_temp_c: peaks,
    };
    this.broadcast({ type: "session", ...end, ended: true });
    this.lastSession = end;
    this.session = null;
    this.sessionsHist.unshift({
      id: rt.s.id,
      kind: rt.s.kind,
      started_at: rt.s.started_at,
      ended_at: new Date().toISOString(),
      outcome,
      reason: reason ?? outcome,
      dataset: rt.s.dataset,
      model: rt.s.model,
      robot: this.activeId,
      episodes: rt.s.episode.saved,
      max_temp_c: Math.round(Math.max(...Object.values(this.temps.follower))),
    });
    this.setState(to, { reason, detail });
  }

  /** `detail` is the Station's own English line (the dead-man stop has one, like hw/owner.py). */
  estop(reason: string, detail: string | null = null): Status {
    if (this.state === "estopped") {
      // Second press within 2 s: torque off (§4.7).
      if (this.t - this.lastEstopAt <= 2) this.torque = false;
      this.lastEstopAt = this.t;
      this.broadcast({ type: "state", ...this.status() });
      return this.status();
    }
    // E-stop aborts a program (dry runs too) and a trajectory take / replay within the tick.
    this.programs.onEstop();
    if (this.state === "disconnected") return this.status();
    this.lastEstopAt = this.t;
    if (this.session) {
      this.interrupted = true;
      this.endSession(`estop_${reason}`, "estopped", reason, detail);
    } else this.setState("estopped", { reason, detail });
    return this.status();
  }

  estopReset(): Status {
    if (this.state !== "estopped") return this.status();
    this.requireCool();
    for (const [id, a] of this.alerts) {
      if (a.level === "critical") {
        this.alerts.delete(id);
        this.broadcast({ ...a, active: false });
      }
    }
    this.setState("idle");
    return this.status();
  }

  // ------------------------------------------------------------------ jobs
  newJob(kind: Job["kind"], subject: string, total: number, unit: "bytes" | "steps" = "bytes"): Job {
    const phase =
      kind === "upload"
        ? "hashing"
        : kind === "load"
          ? "loading"
          : kind === "pull"
            ? "downloading"
            : "extracting";
    const job: Job = {
      id: `j_${++this.jobSeq}`,
      kind,
      status: "running",
      progress: { done: 0, total, unit, phase },
      result: null,
      error: null,
      subject,
    };
    this.jobs.push(job);
    this.broadcast({ type: "job", ...job });
    return job;
  }

  private advanceJobs(dt: number): void {
    for (const j of this.jobs) {
      if (j.status !== "running") continue;
      const p = j.progress;
      p.done = Math.min(p.total, p.done + p.total * dt * 0.5);
      if (j.kind === "upload" && p.phase === "hashing" && p.done >= p.total) {
        p.phase = "uploading";
        p.done = 0;
      } else if (p.done >= p.total) this.finishJob(j);
      this.broadcast({ type: "job", ...j });
    }
  }

  private finishJob(j: Job): void {
    j.status = "succeeded";
    if (j.kind === "upload") {
      const d = this.datasets.find((x) => x.name === j.subject);
      const web = this.server.web_url ?? "";
      const version = (d?.uploaded?.version ?? 0) + 1;
      const up = {
        server: this.server.url ?? "",
        dataset_id: "d_7",
        version_id: `dv_7_${version}`,
        version,
        at: new Date().toISOString(),
        server_url: `${web}/w/lab/datasets/d_7`,
        train_url: `${web}/w/lab/runs/new?version=dv_7_${version}`,
      };
      if (d) {
        d.uploads = [...d.uploads, up];
        d.uploaded = up;
      }
      j.result = { dataset: j.subject, ...omit(up, "server", "at") };
    } else if (j.kind === "load") {
      this.loaded = j.subject ?? null;
      j.result = { model: j.subject, device: "cpu", load_s: 2.1, warmup_ms: 41 };
      this.broadcast({ type: "state", ...this.status() });
    } else {
      const sm = fx.serverModels.find((m) => m.id === j.subject);
      const key = sm ? sm.name.replace(/[^a-z0-9]+/gi, "_").toLowerCase() : `imported_${this.jobSeq}`;
      if (!this.models.some((m) => m.key === key)) {
        this.models.push({
          ...structuredClone(fx.model),
          key,
          name: sm?.name ?? key,
          source: j.kind === "pull" ? "server" : "pretrained_dir",
          verified: j.kind === "pull",
          policy_type: sm?.policy_type ?? "act",
        });
      }
      j.result = { model: key };
    }
  }

  // ------------------------------------------------------------------ simulation
  start(intervalMs = 50): void {
    if (this.timer) return;
    this.timer = setInterval(() => {
      this.step(intervalMs / 1000);
    }, intervalMs);
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  get moving(): boolean {
    return [
      "teleop",
      "recording",
      "replaying",
      "inferring",
      "recording_traj",
      "playing",
      "programming",
    ].includes(this.state);
  }

  step(dt: number): void {
    this.t += dt;
    const connected = this.activeId !== null && !["disconnected", "error"].includes(this.state);
    if (!connected) {
      this.programs.step(dt); // a dry run works without a robot
      return;
    }
    const fps = this.session?.s.fps ?? 10;
    this.tick += Math.max(1, Math.round(fps * dt));
    this.heat(dt);
    if (
      this.deadman &&
      ["inferring", "replaying", "playing", "programming"].includes(this.state) &&
      this.t - this.lastHeartbeat > 1.0
    ) {
      this.estop("ui_lost", "no heartbeat from the UI for 1.0 s");
    }
    this.advanceSession(dt);
    this.programs.step(dt);
    this.advanceJobs(dt);
    this.acc.joints += dt;
    this.acc.telemetry += dt;
    this.acc.video += dt;
    this.acc.session += dt;
    this.acc.calib += dt;
    if (this.acc.joints >= 0.05) {
      this.acc.joints = 0;
      this.broadcast(this.jointsMsg());
    }
    if (this.acc.telemetry >= 0.5) {
      this.acc.telemetry = 0;
      this.emitTelemetry();
    }
    if (this.acc.session >= 1 && this.session) {
      this.acc.session = 0;
      this.broadcast({ type: "session", ...this.session.s });
    }
    if (this.state === "calibrating" && this.calib?.step === "ranges" && this.acc.calib >= 0.1) {
      this.acc.calib = 0;
      this.calib = {
        ...this.calib,
        motors: Object.fromEntries(
          Object.entries(this.calib.motors).map(([m, r], i) => {
            // The demo hand moves one joint after the other, as the wizard asks.
            const since = this.t - this.calibT0 - i * 1.4;
            const amp = since <= 0 ? 0 : Math.min(900, since * 700);
            const pos = Math.round(2048 + Math.sin(since * 2.2) * amp);
            const min = Math.min(r.min ?? pos, pos);
            const max = Math.max(r.max ?? pos, pos);
            return [m, { ...r, pos, min, max, ok: max - min >= MIN_RANGE }];
          }),
        ),
      };
      this.calib.ready = Object.values(this.calib.motors).every((r) => r.ok);
      this.broadcast(this.calib);
    }
    const subs = [...this.video.values()];
    const maxFps = Math.max(0, ...subs.map((s) => s.fps));
    if (maxFps > 0 && this.acc.video >= 1 / maxFps) {
      this.acc.video = 0;
      void this.emitFrames();
    }
  }

  private advanceSession(dt: number): void {
    const rt = this.session;
    if (!rt || this.programs.ownsSession(rt.s.kind)) return;
    rt.phaseT += dt;
    const ep = rt.s.episode;
    if (rt.s.kind === "teleop") {
      if (this.sub === "align" && rt.phaseT >= 2) {
        this.sub = "approach";
        rt.s.episode.phase = "approach";
        rt.phaseT = 0;
        this.broadcast({ type: "state", ...this.status() });
      } else if (this.sub === "approach" && rt.phaseT >= 1.5) {
        this.sub = "teleop";
        rt.s.episode.phase = "teleop";
        this.broadcast({ type: "state", ...this.status() });
      }
      return;
    }
    if (ep.phase === "saving") {
      if (rt.phaseT >= SAVE_S) this.endSession(rt.stopping ? "stopped" : "completed");
      return;
    }
    ep.elapsed_s = rt.phaseT;
    if (ep.limit_s === null || rt.phaseT < ep.limit_s) return;
    if (rt.s.kind === "rest") {
      this.interrupted = false;
      this.endSession("completed");
      return;
    }
    if (rt.s.kind === "replay") {
      // The Station announces this phase change with a session message only (no state message).
      if (ep.phase === "approach") {
        rt.s.episode = { ...ep, phase: "replay", elapsed_s: 0, limit_s: REPLAY_S };
        rt.phaseT = 0;
        this.broadcast({ type: "session", ...rt.s });
      } else this.endSession("completed");
      return;
    }
    if (ep.phase === "countdown")
      this.phase(rt, "episode", rt.rec?.episode_time_s ?? rt.run?.episode_time_s ?? 30);
    else if (ep.phase === "episode") {
      if (rt.rec?.on_timeout !== "discard" && rt.rec) this.saveEpisode(rt);
      this.afterEpisode(rt);
    } else if (ep.phase === "reset") this.nextEpisode(rt);
  }

  private heat(dt: number): void {
    for (const arm of ["follower", "leader"] as Arm[]) {
      for (const m of Object.keys(this.temps[arm])) {
        const cur = this.temps[arm][m] ?? 30;
        let next = cur;
        if (arm === "follower" && m === "elbow_flex" && this.moving) next = cur + this.heatRate * dt;
        else if (!this.moving) next = Math.max(arm === "follower" ? 34 : 30, cur - 0.4 * dt);
        this.temps[arm][m] = next;
      }
    }
  }

  private pos(i: number): number {
    return Math.round(Math.sin(this.t * 0.8 + i) * (i === 5 ? 40 : 35) * 10) / 10 + (i === 5 ? 50 : 0);
  }

  jointsMsg(): unknown {
    const follower = Object.fromEntries(fx.MOTORS.map((m, i) => [`${m}.pos`, this.pos(i)]));
    const msg: Record<string, unknown> = {
      type: "joints",
      t: this.session ? this.session.phaseT : this.t,
      tick: this.tick,
      arms: { follower },
      clipped: [],
      loop: {
        fps: this.session ? this.session.s.fps - 0.2 : 10,
        tick_ms_p95: this.state === "teleop" ? 3.1 : 21.4,
        overruns: 0,
        telemetry_forced: 0,
        ...(this.state === "teleop" || this.state === "recording"
          ? { latency_ms_p50: this.state === "teleop" ? 4.6 : 19.5, latency_ms_p95: 7.2, clip_fraction: 0 }
          : {}),
      },
    };
    if (this.state === "teleop" || this.state === "recording") {
      (msg.arms as Record<string, unknown>).leader = Object.fromEntries(
        fx.MOTORS.map((m, i) => [`${m}.pos`, this.pos(i) + 1.2]),
      );
    }
    if (this.state === "inferring" && this.session?.s.episode.phase === "episode") {
      const action = Object.fromEntries(
        fx.MOTORS.map((m, i) => [`${m}.pos`, this.pos(i) + (i === 3 ? 8 : 2)]),
      );
      const sent = { ...action, "wrist_flex.pos": (follower["wrist_flex.pos"] ?? 0) + 5 };
      msg.action = action;
      msg.sent = sent;
      msg.clipped = ["wrist_flex.pos"];
      msg.loop = { ...(msg.loop as object), inference_ms_p50: 18, inference_ms_p95: 24.5, clipped_pct: 12 };
    }
    return msg;
  }

  sample(arm: Arm, motor: string): MotorSample {
    const temp = Math.round(this.temps[arm][motor] ?? 30);
    const level = this.levels[`${arm}.${motor}`] ?? "ok";
    // Field report 0.2.8: the leader's 5 V servos answer no temperature and no current.
    const leader = arm === "leader";
    return {
      temp_c: leader ? null : temp,
      voltage_v: leader ? 5.0 : 12.1,
      current_a: leader ? null : this.moving ? 0.42 : 0.05,
      load_pct: this.moving ? -31.5 : 2,
      status: [],
      level,
      stale: false,
    };
  }

  private emitTelemetry(): void {
    const th = this.profile?.thresholds ?? this.settings.thresholds;
    for (const arm of ["follower", "leader"] as Arm[]) {
      if (arm === "leader" && !this.profile?.leader) continue;
      for (const motor of Object.keys(this.temps[arm])) {
        const key = `${arm}.${motor}`;
        const temp = this.temps[arm][motor] ?? 0;
        const prev = this.levels[key] ?? "ok";
        const streak = temp >= th.temp_critical_c ? (this.critStreak[key] ?? 0) + 1 : 0;
        this.critStreak[key] = streak;
        // Hysteresis: a level clears only 3 °C below its threshold.
        let level: Level = "ok";
        if (streak >= 2 || (prev === "critical" && temp >= th.temp_critical_c - 3)) level = "critical";
        else if (temp >= th.temp_hot_c || (["hot", "critical"].includes(prev) && temp >= th.temp_hot_c - 3))
          level = "hot";
        else if (temp >= th.temp_warn_c || (prev !== "ok" && temp >= th.temp_warn_c - 3)) level = "warn";
        if (level !== prev) this.levelChange(arm, motor, prev, level, Math.round(temp));
      }
      this.broadcast({
        type: "telemetry",
        t: this.t,
        arm,
        motors: Object.fromEntries(Object.keys(this.temps[arm]).map((m) => [m, this.sample(arm, m)])),
        group: "thermal",
        forced: false,
        limits: {
          max_temp_c: 70,
          min_voltage_v: arm === "follower" ? 9.5 : 4.0,
          max_voltage_v: arm === "follower" ? 14 : 8,
          nominal_voltage_v: arm === "follower" ? 12 : 5,
          protection_current_a: Object.fromEntries(Object.keys(this.temps[arm]).map((m) => [m, 1.625])),
        },
      });
    }
  }

  private levelChange(arm: Arm, motor: string, prev: Level, level: Level, value: number): void {
    const key = `${arm}.${motor}`;
    this.levels[key] = level;
    const id = `temp-${key}`;
    if (prev !== "ok") {
      const old = this.alerts.get(id);
      if (old) this.broadcast({ ...old, active: false });
      this.alerts.delete(id);
    }
    if (level !== "ok") {
      const a: AlertMsg = {
        type: "alert",
        id,
        t: this.t,
        level,
        kind: "temperature",
        arm,
        motor,
        camera: null,
        value,
        message_key: `motor.temp.${level}`,
        params: { motor, value },
        active: true,
      };
      this.alerts.set(id, a);
      this.broadcast(a);
    }
    if (level === "critical" && this.state !== "estopped") {
      // ThermalGuard safe stop: hold, park, torque off, latch estopped(thermal).
      if (this.session) this.endSession("thermal", "estopped", "thermal");
      else this.setState("estopped", { reason: "thermal" });
      if (arm === "follower") this.torque = false;
      this.broadcast({ type: "state", ...this.status() });
    }
  }

  private async emitFrames(): Promise<void> {
    const p = this.profile;
    if (!p) return;
    const tick = this.tick;
    const policy = this.state === "inferring";
    for (const [sock, sub] of this.video) {
      for (const cam of sub.cameras) {
        const c = p.cameras[cam];
        if (!c) {
          sock.deliver(JSON.stringify({ type: "camera_error", cam, code: "camera_unavailable" }));
          continue;
        }
        const w = Math.min(sub.width, c.width);
        const h = Math.round((w * c.height) / c.width);
        const header: FrameHeader = {
          cam,
          tick,
          t: this.t,
          w,
          h,
          src_w: c.width,
          src_h: c.height,
          policy_input: policy,
          stale: false,
        };
        const jpeg = await this.frameSource(cam, tick, w, h);
        sock.deliver(encodeFrame(header, jpeg));
      }
    }
  }
}
