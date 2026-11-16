import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { PALETTE } from "@/hibiscus/sprites.gen";
import { contrastRatio } from "@/lib/pixelTheme";
import type { JointsMsg, TelemetryMsg } from "./api/types";
import {
  DEFAULT_THRESHOLDS,
  LEVEL_STYLE,
  coolingEtaS,
  motorLevel,
  tempLevel,
  validateThresholds,
  worstLevel,
} from "./health";
import en from "./i18n/en.json";
import vi_ from "./i18n/vi.json";
import { MockStation } from "./mock/sim";
import { wizardSteps } from "./StationShell";
import { realArmDraft, roleWarnings } from "./pages/RobotPage";
import { ControlSocket, HEARTBEAT_MS, backoffMs } from "./ws/control";
import { JOINT_WINDOW_S, StationStore, appendJoints } from "./ws/store";
import { encodeFrame, parseFrame } from "./ws/video";

describe("motor health thresholds (R1, §4.5.3)", () => {
  it("maps temperatures to levels at 50 / 60 / 65 °C", () => {
    expect(tempLevel(49)).toBe("ok");
    expect(tempLevel(50)).toBe("warn");
    expect(tempLevel(59)).toBe("warn");
    expect(tempLevel(60)).toBe("hot");
    expect(tempLevel(65)).toBe("critical");
    expect(tempLevel(null)).toBe("ok");
  });

  it("never shows a motor cooler than the server says, and status bits are critical", () => {
    const s = {
      temp_c: 40,
      voltage_v: 12,
      current_a: 0.1,
      load_pct: 0,
      status: [],
      level: "hot" as const,
      stale: false,
    };
    expect(motorLevel(s)).toBe("hot");
    expect(motorLevel({ ...s, level: "ok", status: ["overheat"] })).toBe("critical");
    expect(motorLevel({ ...s, level: "ok", load_pct: -95 })).toBe("warn");
    expect(worstLevel(["ok", "warn", "critical", "hot"])).toBe("critical");
  });

  it("enforces critical ≤ motor cutoff − 3, hot ≤ critical − 3, warn ≤ hot − 5", () => {
    expect(validateThresholds(DEFAULT_THRESHOLDS, 70)).toEqual([]);
    expect(validateThresholds({ temp_warn_c: 50, temp_hot_c: 60, temp_critical_c: 68 }, 70)).toContain(
      "settings.err_critical",
    );
    expect(validateThresholds({ temp_warn_c: 50, temp_hot_c: 63, temp_critical_c: 65 }, 70)).toContain(
      "settings.err_hot",
    );
    expect(validateThresholds({ temp_warn_c: 57, temp_hot_c: 60, temp_critical_c: 65 }, 70)).toContain(
      "settings.err_warn",
    );
  });

  it("level colours keep WCAG AA text contrast in both themes (fixed pixel colours)", () => {
    for (const s of Object.values(LEVEL_STYLE)) {
      expect(contrastRatio(PALETTE[s.fg], PALETTE[s.bg])).toBeGreaterThanOrEqual(4.5);
    }
    // The e-stop label (cream on hibiscus red) and the critical banner.
    expect(contrastRatio(PALETTE.C, PALETTE.r)).toBeGreaterThanOrEqual(4.5);
  });

  it("estimates the cooling time with a linear fit", () => {
    const t = [0, 10, 20, 30];
    expect(coolingEtaS(t, [66, 65, 64, 63], 60)).toBe(30);
    expect(coolingEtaS(t, [60, 61, 62, 63], 60)).toBeNull();
  });
});

describe("HSF1 video frames (§5.4)", () => {
  it("round-trips header and JPEG bytes", () => {
    const header = {
      cam: "wrist",
      tick: 1834,
      t: 61.13,
      w: 320,
      h: 240,
      src_w: 640,
      src_h: 480,
      policy_input: true,
      stale: false,
    };
    const buf = encodeFrame(header, new Uint8Array([0xff, 0xd8, 1, 2, 0xff, 0xd9]));
    const f = parseFrame(buf);
    expect(f?.header).toEqual(header);
    expect(Array.from(f?.jpeg ?? [])).toEqual([0xff, 0xd8, 1, 2, 0xff, 0xd9]);
    const bytes = new Uint8Array(buf);
    expect(String.fromCharCode(...bytes.slice(0, 4))).toBe("HSF1");
  });

  it("rejects other payloads", () => {
    expect(parseFrame(new Uint8Array([1, 2, 3, 4, 5, 6, 7]).buffer)).toBeNull();
    expect(parseFrame(new ArrayBuffer(2))).toBeNull();
  });
});

function joints(t: number, tick: number, extra: Partial<JointsMsg> = {}): JointsMsg {
  return {
    type: "joints",
    t,
    tick,
    arms: { follower: { "elbow_flex.pos": t, "gripper.pos": 50 } },
    clipped: [],
    loop: { fps: 30, tick_ms_p95: 20, overruns: 0, telemetry_forced: 0 },
    ...extra,
  };
}

describe("live store", () => {
  it("keeps a 10 s joint window of observed vs commanded values", () => {
    let h = appendJoints({ t: [], obs: {}, cmd: {}, clipped: {} }, joints(0, 0));
    for (let i = 1; i <= 40; i += 1) {
      h = appendJoints(
        h,
        joints(i * 0.5, i * 15, {
          sent: { "elbow_flex.pos": i },
          clipped: i === 40 ? ["elbow_flex.pos"] : [],
        }),
      );
    }
    expect(h.t[0]).toBeGreaterThanOrEqual(20 - JOINT_WINDOW_S);
    expect(h.obs.elbow_flex?.length).toBe(h.t.length);
    expect(h.cmd.elbow_flex?.at(-1)).toBe(40);
    expect(h.clipped.elbow_flex).toEqual([20]);
  });

  it("tracks telemetry, temperature peaks and active alerts", () => {
    const store = new StationStore();
    const tel = (temp: number, t: number): TelemetryMsg => ({
      type: "telemetry",
      t,
      arm: "follower",
      group: "thermal",
      forced: false,
      limits: {
        max_temp_c: 70,
        min_voltage_v: 4,
        max_voltage_v: 14,
        nominal_voltage_v: 12,
        protection_current_a: {},
      },
      motors: {
        elbow_flex: {
          temp_c: temp,
          voltage_v: 12,
          current_a: 0.3,
          load_pct: 10,
          status: [],
          level: tempLevel(temp),
          stale: false,
        },
      },
    });
    store.handle(tel(48, 0));
    store.handle(tel(55, 0.5));
    store.handle(tel(52, 1));
    expect(store.getSnapshot().peaks["follower.elbow_flex"]).toBe(55);
    expect(store.getSnapshot().tempHist.follower?.elbow_flex?.v).toEqual([48, 55, 52]);
    const alert = {
      type: "alert" as const,
      id: "a1",
      t: 1,
      level: "warn" as const,
      kind: "temperature" as const,
      arm: "follower" as const,
      motor: "elbow_flex",
      camera: null,
      value: 51,
      message_key: "motor.temp.warn",
      params: {},
      active: true,
    };
    store.handle(alert);
    expect(store.getSnapshot().alerts).toHaveLength(1);
    store.handle({ ...alert, active: false });
    expect(store.getSnapshot().alerts).toHaveLength(0);
    expect(store.getSnapshot().alertCount).toBe(1);
  });

  it("accepts hello / state in both wrapped and flat form", () => {
    const store = new StationStore();
    const status = new MockStation({ connected: true }).status();
    store.handle({ type: "hello", v: 1, status });
    expect(store.getSnapshot().status?.state).toBe("idle");
    store.handle({ type: "state", ...status, state: "teleop" });
    expect(store.getSnapshot().status?.state).toBe("teleop");
  });
});

describe("control socket (§5.3)", () => {
  it("says hello, sends the 250 ms dead-man heartbeat and reconnects with backoff", async () => {
    vi.useFakeTimers();
    try {
      const sim = new MockStation({ connected: true });
      const store = new StationStore();
      const sock = new ControlSocket("ws://x/api/v1/ws", store, sim.socketFactory);
      sock.start();
      await vi.advanceTimersByTimeAsync(1);
      expect(store.getSnapshot().conn).toBe("open");
      expect(store.getSnapshot().status?.state).toBe("idle");
      const [mock] = sim.controlSockets;
      expect(JSON.parse(mock?.sent[0] ?? "{}")).toMatchObject({ type: "hello", v: 1, heartbeat: true });
      await vi.advanceTimersByTimeAsync(HEARTBEAT_MS * 4);
      expect(mock?.sent.filter((s) => s.includes("heartbeat")).length).toBeGreaterThanOrEqual(4);
      mock?.drop();
      expect(store.getSnapshot().conn).toBe("reconnecting");
      await vi.advanceTimersByTimeAsync(backoffMs(0) + 5);
      expect(store.getSnapshot().conn).toBe("open");
      expect(sim.controlSockets).toHaveLength(1);
      expect(sock.estop()).toBe(true);
      expect(sim.state).toBe("estopped");
      sock.stop();
    } finally {
      vi.useRealTimers();
    }
  });

  it("backoff grows and is capped at 5 s", () => {
    expect(backoffMs(0)).toBe(250);
    expect(backoffMs(3)).toBe(2000);
    expect(backoffMs(20)).toBe(5000);
  });
});

describe("mock station ThermalGuard", () => {
  it("needs two consecutive critical samples, then stops safely with torque off", () => {
    const sim = new MockStation({ connected: true, startTemp: 36 });
    sim.startSession("teleop", { fps: 30 });
    sim.temps.follower.elbow_flex = 66;
    sim.step(0.5);
    expect(sim.state).toBe("teleop");
    sim.step(0.5);
    expect(sim.state).toBe("estopped");
    expect(sim.reason).toBe("thermal");
    expect(sim.torque).toBe(false);
    expect(() => sim.estopReset()).toThrow();
  });
});

describe("real arm draft (field report 0.2.1: demo profile left active)", () => {
  it("fills the detected USB ports, follower first, skipping ports in use", () => {
    const port = (device: string, inUse: string | null = null) => ({
      device,
      stable_path: null,
      vid_pid: "1a86:55d3",
      serial_number: null,
      description: "USB Single Serial",
      in_use_by: inUse,
    });
    const d = realArmDraft([port("COM3"), port("COM4"), port("COM5", "pid 7")]);
    expect(d.follower.type).toBe("so101_follower");
    expect(d.follower.port).toBe("COM3");
    expect(d.leader?.port).toBe("COM4");
    expect(realArmDraft([{ ...port("/dev/ttyS0"), vid_pid: null }]).follower.port).toBe("");
  });
});

describe("leader / follower voltage hints", () => {
  const probe = (v: number | null, hint: "leader" | "follower" | null) => ({
    device: "COM3",
    voltage_v: v,
    motors: 6,
    model_number: 777,
    firmware: "3.10",
    role_hint: hint,
    error: null,
    in_use_by: null,
  });
  it("warns for a ~5 V follower or a >= 7 V leader, never otherwise", () => {
    expect(roleWarnings(probe(12.1, "follower"), probe(5.0, "leader"))).toEqual([]);
    expect(roleWarnings(probe(5.0, "leader"), probe(7.4, "follower"))).toEqual([
      { slot: "follower", looks_like: "leader", voltage_v: 5.0 },
      { slot: "leader", looks_like: "follower", voltage_v: 7.4 },
    ]);
    expect(roleWarnings(probe(6.2, null), undefined)).toEqual([]);
    expect(roleWarnings(probe(null, null), probe(null, null))).toEqual([]);
  });
});

describe("wizard rail", () => {
  it("locks steps until their prerequisite is met", () => {
    const sim = new MockStation({ connected: false });
    let steps = wizardSteps(sim.status(), { robots: 1, datasets: [], models: 0 });
    expect(steps.find((s) => s.key === "calibrate")?.lock).toBe("connect_first");
    expect(steps.find((s) => s.key === "upload")?.lock).toBe("record_first");
    expect(steps.find((s) => s.key === "robot")?.done).toBe(true);
    sim.doConnect("desk_so101");
    sim.calibrated.leader = false;
    steps = wizardSteps(sim.status(), { robots: 1, datasets: [{ episodes: 2, uploaded: false }], models: 1 });
    expect(steps.find((s) => s.key === "teleop")?.lock).toBe("calibrate_leader");
    expect(steps.find((s) => s.key === "run")?.lock).toBeNull();
    expect(steps.find((s) => s.key === "upload")?.lock).toBeNull();
    expect(steps.find((s) => s.key === "train")?.lock).toBe("pair_first");
  });

  it("says why a step is locked: the Station's own reason (field report 0.2.1)", () => {
    const sim = new MockStation({ connected: false });
    sim.doConnect("desk_so101");
    const st = sim.status();
    const robot = st.robot!;
    const issue =
      "no calibration file /c/robots/so_follower/desk_follower.json; calibration files found: my_follower";
    const status = {
      ...st,
      robot: {
        ...robot,
        arms: { ...robot.arms, follower: { ...robot.arms.follower, calibrated: false, issue } },
      },
    };
    let steps = wizardSteps(status, { robots: 1, datasets: [], models: 1 });
    expect(steps.find((s) => s.key === "teleop")?.lock).toBe("calibrate_first");
    expect(steps.find((s) => s.key === "teleop")?.why).toBe(issue);
    expect(steps.find((s) => s.key === "run")?.why).toBe(issue);
    const err = {
      ...st,
      state: "error" as const,
      robot: null,
      reason: "bus_lost",
      detail: "follower: motor ID 3 timed out",
    };
    steps = wizardSteps(err, { robots: 1, datasets: [], models: 0 });
    expect(steps.find((s) => s.key === "calibrate")?.why).toBe("follower: motor ID 3 timed out");
    const stopped = {
      ...st,
      state: "estopped" as const,
      reason: "electrical",
      detail: "follower elbow_flex 4.1 V",
    };
    steps = wizardSteps(stopped, { robots: 1, datasets: [], models: 1 });
    expect(steps.find((s) => s.key === "teleop")?.lock).toBe("estopped");
    expect(steps.find((s) => s.key === "teleop")?.why).toBe("follower elbow_flex 4.1 V");
  });
});

// ------------------------------------------------------------------ i18n
function flatKeys(o: Record<string, unknown>, prefix = ""): string[] {
  return Object.entries(o).flatMap(([k, v]) =>
    typeof v === "object" && v !== null
      ? flatKeys(v as Record<string, unknown>, `${prefix}${k}.`)
      : [`${prefix}${k}`],
  );
}

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return f === "test" || f === "mock" ? [] : sources(p);
    return /\.tsx?$/.test(f) && !f.includes(".test.") && !f.endsWith(".d.ts") ? [p] : [];
  });
}

describe("station i18n", () => {
  const enKeys = flatKeys(en);
  it("vi and en have the same keys", () => {
    expect(flatKeys(vi_).sort()).toEqual([...enKeys].sort());
  });

  it("every literal key used in the station UI exists", () => {
    const root = join(process.cwd(), "src/station/");
    const tops = new Set(Object.keys(en));
    const missing: string[] = [];
    const files = sources(root);
    expect(files.length).toBeGreaterThan(20);
    for (const file of files) {
      const src = readFileSync(file, "utf8");
      for (const m of src.matchAll(/"([a-z_]+)\.([a-z_0-9]+)"/g)) {
        const [, top, rest] = m;
        if (!top || !rest || !tops.has(top)) continue;
        const key = `${top}.${rest}`;
        if (!enKeys.includes(key)) missing.push(`${file.slice(root.length)}: ${key}`);
      }
    }
    expect(missing).toEqual([]);
  });
});
