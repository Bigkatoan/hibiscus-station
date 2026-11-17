/**
 * Live Station state fed by the control WebSocket (§5.3): status, joints (+10 s history),
 * motor telemetry (+120 s temperature history), active alerts, calibration progress and jobs.
 * A tiny external store read with useSyncExternalStore; every update replaces the snapshot.
 */
import type {
  AlertMsg,
  Arm,
  CalibrationMsg,
  Job,
  JointsMsg,
  MotorLimits,
  MotorSample,
  ProgramLogLine,
  ProgramState,
  ServerMessage,
  Session,
  Signal,
  Status,
  TrajectoryRecordMsg,
} from "../api/types";
import { omit } from "../api/types";

export type ConnState = "connecting" | "open" | "reconnecting" | "closed";

export interface Series {
  t: number[];
  v: (number | null)[];
}

export interface JointHistory {
  t: number[];
  obs: Record<string, (number | null)[]>;
  cmd: Record<string, (number | null)[]>;
  clipped: Record<string, number[]>;
}

export interface StationSnapshot {
  conn: ConnState;
  status: Status | null;
  joints: JointsMsg | null;
  jointHist: JointHistory;
  telemetry: Partial<Record<Arm, Record<string, MotorSample>>>;
  tempHist: Partial<Record<Arm, Record<string, Series>>>;
  limits: Partial<Record<Arm, MotorLimits>>;
  alerts: AlertMsg[];
  calibration: CalibrationMsg | null;
  jobs: Record<string, Job>;
  /** Max temperature per `${arm}.${motor}` since the last `resetPeaks()` (run summary). */
  peaks: Record<string, number>;
  alertCount: number;
  /** The most recent session seen (kept after it ends, for end cards and run summaries). */
  lastSession: Session | null;
  /** The end of the last session that ended (its final `session` message): why, and its summary. */
  lastEnd: SessionEndInfo | null;
  /** The current (or last finished) program run (programs §7: WS `program_state`, `Status.program`). */
  program: ProgramState | null;
  /** Log lines of that run (WS `program_log`), newest last, at most PROGRAM_LOG_MAX. */
  programLog: ProgramLogLine[];
  /** Progress of a trajectory take (WS `trajectory_record`); the final one carries the draft id. */
  trajRecord: TrajectoryRecordMsg | null;
  /** Last value of every signal seen on the bus (WS `signal`). */
  signals: Record<string, Signal>;
}

export interface SessionEndInfo {
  id: string;
  outcome: string;
  reason: string | null;
  summary: Record<string, unknown> | null;
}

export const PROGRAM_LOG_MAX = 300;

/** Program statuses after which a run never changes again. */
export const PROGRAM_DONE: readonly ProgramState["status"][] = [
  "completed",
  "stopped",
  "failed",
  "estopped",
  "timeout",
];

export const JOINT_WINDOW_S = 10;
export const TEMP_WINDOW_S = 120;

function emptyHist(): JointHistory {
  return { t: [], obs: {}, cmd: {}, clipped: {} };
}

export function initialSnapshot(): StationSnapshot {
  return {
    conn: "connecting",
    status: null,
    joints: null,
    jointHist: emptyHist(),
    telemetry: {},
    tempHist: {},
    limits: {},
    alerts: [],
    calibration: null,
    jobs: {},
    peaks: {},
    alertCount: 0,
    lastSession: null,
    lastEnd: null,
    program: null,
    programLog: [],
    trajRecord: null,
    signals: {},
  };
}

/** Index of the first sample still inside the window ending at `now`. */
function firstInWindow(ts: readonly number[], now: number, window: number): number {
  let i = 0;
  while (i < ts.length && (ts[i] ?? 0) < now - window) i += 1;
  return i;
}

/** Joint name from a lerobot feature key ("shoulder_pan.pos" → "shoulder_pan"). */
export function jointName(key: string): string {
  return key.endsWith(".pos") ? key.slice(0, -4) : key;
}

export function appendJoints(hist: JointHistory, msg: JointsMsg): JointHistory {
  // A new session restarts `t` at 0: start a fresh window.
  const last = hist.t[hist.t.length - 1];
  const base = last !== undefined && msg.t < last ? emptyHist() : hist;
  const from = firstInWindow(base.t, msg.t, JOINT_WINDOW_S);
  const t = [...base.t.slice(from), msg.t];
  const follower = msg.arms.follower;
  const names = Object.keys(follower).map(jointName);
  const obs: JointHistory["obs"] = {};
  const cmd: JointHistory["cmd"] = {};
  const n = t.length - 1;
  for (const name of names) {
    const prevObs = base.obs[name]?.slice(from) ?? [];
    const prevCmd = base.cmd[name]?.slice(from) ?? [];
    while (prevObs.length < n) prevObs.unshift(null);
    while (prevCmd.length < n) prevCmd.unshift(null);
    obs[name] = [...prevObs, follower[`${name}.pos`] ?? follower[name] ?? null];
    const a = msg.sent ?? msg.action ?? msg.arms.leader;
    cmd[name] = [...prevCmd, a ? (a[`${name}.pos`] ?? a[name] ?? null) : null];
  }
  const clipped: JointHistory["clipped"] = {};
  const t0 = t[0] ?? msg.t;
  for (const [name, ts] of Object.entries(base.clipped)) {
    const keep = ts.filter((x) => x >= t0);
    if (keep.length) clipped[name] = keep;
  }
  for (const c of msg.clipped) {
    const name = jointName(c);
    clipped[name] = [...(clipped[name] ?? []), msg.t];
  }
  return { t, obs, cmd, clipped };
}

function appendTemps(
  hist: StationSnapshot["tempHist"],
  arm: Arm,
  t: number,
  motors: Record<string, MotorSample>,
): StationSnapshot["tempHist"] {
  const armHist = { ...(hist[arm] ?? {}) };
  for (const [motor, s] of Object.entries(motors)) {
    const prev = armHist[motor] ?? { t: [], v: [] };
    const lastT = prev.t[prev.t.length - 1];
    const src = lastT !== undefined && t < lastT ? { t: [], v: [] } : prev;
    const from = firstInWindow(src.t, t, TEMP_WINDOW_S);
    armHist[motor] = { t: [...src.t.slice(from), t], v: [...src.v.slice(from), s.stale ? null : s.temp_c] };
  }
  return { ...hist, [arm]: armHist };
}

/** Drop the message envelope (`type`) from a flat WS message. */
function strip<T extends { type: string }>(msg: T): Omit<T, "type"> {
  return omit(msg, "type");
}

export class StationStore {
  private snap: StationSnapshot = initialSnapshot();
  private listeners = new Set<() => void>();

  getSnapshot = (): StationSnapshot => this.snap;

  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };

  private set(patch: Partial<StationSnapshot>): void {
    this.snap = { ...this.snap, ...patch };
    for (const l of this.listeners) l();
  }

  setConn(conn: ConnState): void {
    if (conn !== this.snap.conn) this.set({ conn });
  }

  setStatus(status: Status): void {
    const cur = this.snap.program;
    let program = cur;
    if (status.program) program = this.newerProgram(status.program);
    else if (cur && !PROGRAM_DONE.includes(cur.status)) program = null;
    this.set({
      status,
      lastSession: status.session ?? this.snap.lastSession,
      ...(program !== cur ? this.programPatch(program) : {}),
    });
  }

  /**
   * The Session a REST call answered (a run, a program run). Only `status.session` changes: the
   * rest of the stored status may be older than the WS messages already handled (a hardware
   * program run answers after its first `program_state`), so it must not go through setStatus,
   * which would read the stale `program: null` as "the run vanished".
   */
  setSession(session: Session): void {
    const st = this.snap.status;
    this.set({ lastSession: session, ...(st ? { status: { ...st, session } } : {}) });
  }

  /** A program state from REST or WS; an older `t` of the same run never replaces a newer one. */
  setProgram(state: ProgramState): void {
    const next = this.newerProgram(state);
    if (next !== this.snap.program) this.set(this.programPatch(next));
  }

  private newerProgram(state: ProgramState): ProgramState {
    const cur = this.snap.program;
    if (cur?.run_id === state.run_id && state.t < cur.t && !PROGRAM_DONE.includes(state.status)) return cur;
    return state;
  }

  private programPatch(program: ProgramState | null): Partial<StationSnapshot> {
    const sameRun = program !== null && this.snap.program?.run_id === program.run_id;
    if (sameRun) return { program };
    // A status without the run keeps its lines: the Station's session `state` can go out between
    // the run's first messages and its registration, and the next `state` brings the run back.
    if (program === null) return { program };
    // A new run keeps only the lines that already arrived for it (a log line can beat its state).
    return { program, programLog: this.snap.programLog.filter((l) => l.run_id === program.run_id) };
  }

  setJob(job: Job): void {
    this.set({ jobs: { ...this.snap.jobs, [job.id]: job } });
  }

  resetPeaks(): void {
    this.set({ peaks: {}, alertCount: 0 });
  }

  handle(msg: ServerMessage): void {
    switch (msg.type) {
      case "hello":
        this.setStatus(msg.status);
        return;
      case "state":
        this.setStatus(strip(msg));
        return;
      case "joints":
        this.set({ joints: msg, jointHist: appendJoints(this.snap.jointHist, msg) });
        return;
      case "telemetry": {
        const peaks = { ...this.snap.peaks };
        for (const [motor, s] of Object.entries(msg.motors)) {
          const k = `${msg.arm}.${motor}`;
          if (s.temp_c !== null && !s.stale && s.temp_c > (peaks[k] ?? -Infinity)) peaks[k] = s.temp_c;
        }
        this.set({
          telemetry: {
            ...this.snap.telemetry,
            [msg.arm]: { ...this.snap.telemetry[msg.arm], ...msg.motors },
          },
          tempHist: appendTemps(this.snap.tempHist, msg.arm, msg.t, msg.motors),
          limits: { ...this.snap.limits, [msg.arm]: msg.limits },
          peaks,
        });
        return;
      }
      case "alert": {
        const rest = this.snap.alerts.filter((a) => a.id !== msg.id);
        this.set({
          alerts: msg.active ? [...rest, msg] : rest,
          alertCount: this.snap.alertCount + (msg.active ? 1 : 0),
        });
        return;
      }
      case "calibration":
        this.set({ calibration: msg });
        return;
      case "session": {
        const ended = msg.ended === true;
        const session = omit(strip(msg), "ended", "reason", "summary", "loop", "max_temp_c");
        // The final message of a session (`ended: true`) only updates the end card; the `state`
        // message that follows clears `status.session`. The Station announces a phase change
        // (approach → replay, ...) with a session message only; `status.sub` is the session's
        // phase (as in GET /status), so it follows here (QC 0.2.9 QD-5: "Follower moving to the
        // leader pose…" stayed up for a whole replay).
        const st = this.snap.status;
        this.set({
          lastSession: session,
          ...(ended
            ? {
                lastEnd: {
                  id: msg.id,
                  outcome: msg.outcome,
                  reason: msg.reason ?? null,
                  summary: msg.summary ?? null,
                },
              }
            : {}),
          ...(st && !ended ? { status: { ...st, session, sub: session.episode.phase ?? st.sub } } : {}),
        });
        return;
      }
      case "job":
        this.setJob(strip(msg));
        return;
      case "program_state":
        this.setProgram(strip(msg));
        return;
      case "program_log": {
        const line = strip(msg);
        const sameRun = this.snap.program === null || this.snap.program.run_id === line.run_id;
        const prev = sameRun ? this.snap.programLog : [];
        if (prev.some((l) => l.seq === line.seq && l.run_id === line.run_id)) return;
        this.set({ programLog: [...prev, line].slice(-PROGRAM_LOG_MAX) });
        return;
      }
      case "trajectory_record":
        this.set({ trajRecord: msg });
        return;
      case "signal": {
        const sig = strip(msg);
        this.set({ signals: { ...this.snap.signals, [sig.name]: sig } });
        return;
      }
      default:
        return;
    }
  }
}
