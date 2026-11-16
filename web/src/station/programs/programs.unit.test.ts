/**
 * The live store's handling of the programs WS messages (§7) and the mock Station's behaviour for
 * trajectories and block programs (§3, §5, §11): what the UI tests and the mock build rely on.
 */
import { describe, expect, it } from "vitest";
import type { ProgramState, ServerMessage } from "../api/types";
import { MockStation } from "../mock/sim";
import i18next from "i18next";
import vi from "../i18n/vi.json";
import { emptyRefs } from "../programs/blockly/refs";
import { blockDetail, logLineText, programMood } from "../pages/programs/shared";
import { hibiMood } from "../StationShell";
import { suggestTrim } from "../mock/programs";
import { PROGRAM_LOG_MAX, StationStore } from "../ws/store";

const A = "t_20261116_101500_a1b2";

async function wired(opts: ConstructorParameters<typeof MockStation>[0] = {}) {
  const sim = new MockStation({ connected: true, ...opts });
  const store = new StationStore();
  const sock = sim.socketFactory("ws://127.0.0.1/api/v1/ws");
  sock.onmessage = (ev: MessageEvent) => {
    store.handle(JSON.parse(String(ev.data)) as ServerMessage);
  };
  await new Promise((r) => setTimeout(r, 0));
  return { sim, store };
}

function run(sim: MockStation, seconds: number): void {
  for (let i = 0; i < Math.round(seconds / 0.05); i += 1) sim.step(0.05);
}

function state(over: Partial<ProgramState> = {}): ProgramState {
  return {
    run_id: "r_20261116_100000_aaaa",
    program_id: "p",
    version: 1,
    dry_run: true,
    status: "running",
    block_id: "b1",
    block_kind: "wait",
    t: 1,
    steps: 1,
    variables: {},
    conditions: [],
    waiting: null,
    ask: null,
    buttons: [],
    keys: [],
    message: null,
    ...over,
  };
}

describe("store: program messages", () => {
  it("keeps the newest state of a run and drops a late older one", () => {
    const s = new StationStore();
    s.handle({ type: "program_state", ...state({ t: 2, block_id: "b2" }) });
    s.handle({ type: "program_state", ...state({ t: 1, block_id: "b1" }) });
    expect(s.getSnapshot().program?.block_id).toBe("b2");
    s.handle({ type: "program_state", ...state({ t: 1.5, status: "stopped" }) });
    expect(s.getSnapshot().program?.status).toBe("stopped");
  });

  it("collects log lines per run, without duplicates, capped", () => {
    const s = new StationStore();
    s.handle({ type: "program_state", ...state() });
    for (let i = 0; i < PROGRAM_LOG_MAX + 20; i += 1) {
      s.handle({
        type: "program_log",
        run_id: "r_20261116_100000_aaaa",
        seq: i,
        t: i,
        level: "info",
        kind: "block",
        block_id: null,
        message: `m${i}`,
        data: {},
      });
    }
    s.handle({
      type: "program_log",
      run_id: "r_20261116_100000_aaaa",
      seq: PROGRAM_LOG_MAX + 19,
      t: 0,
      level: "info",
      kind: "block",
      block_id: null,
      message: "dup",
      data: {},
    });
    const log = s.getSnapshot().programLog;
    expect(log).toHaveLength(PROGRAM_LOG_MAX);
    expect(log[log.length - 1]?.message).toBe(`m${PROGRAM_LOG_MAX + 19}`);
    // A new run starts a new log (lines of that run that arrived first are kept).
    s.handle({
      type: "program_log",
      run_id: "r2",
      seq: 1,
      t: 0,
      level: "info",
      kind: "start",
      block_id: null,
      message: "go",
      data: {},
    });
    s.handle({ type: "program_state", ...state({ run_id: "r2", t: 0 }) });
    expect(s.getSnapshot().programLog.map((l) => l.message)).toEqual(["go"]);
  });

  it("Status.program restores the run after a reconnect; a vanished live run is cleared", async () => {
    const { store, sim } = await wired();
    sim.programs.startRun("sort_cubes", { dry_run: true, confirm: [], fps: 30 });
    store.setStatus(sim.status());
    expect(store.getSnapshot().program?.program_id).toBe("sort_cubes");
    store.setStatus({ ...sim.status(), program: null });
    expect(store.getSnapshot().program).toBeNull();
  });

  it("the REST answer of a hardware run keeps the live run the WS already sent", async () => {
    // The Station's session `state` goes out before the run is registered (program: null), then
    // `program_state` arrives, then the POST /run answer. During a long motion no further
    // program_state comes, so dropping the run here left the panel "not running" for seconds.
    const { store, sim } = await wired();
    const answer = sim.programs.startRun("sort_cubes", { dry_run: true, confirm: [], fps: 30 });
    const live = sim.status().program;
    if (!live) throw new Error("no run");
    store.setStatus({ ...sim.status(), state: "programming", program: null });
    store.handle({ type: "program_state", ...live, dry_run: false });
    expect(store.getSnapshot().program?.run_id).toBe(live.run_id);
    store.setSession(answer);
    expect(store.getSnapshot().program?.run_id).toBe(live.run_id);
    expect(store.getSnapshot().status?.session).toEqual(answer);
    expect(store.getSnapshot().lastSession).toEqual(answer);
  });

  it("a status without the run, then with it again, keeps the run's log lines", async () => {
    // The Station's session `state` (program: null) can land after the run's first program_state
    // and log lines; the follow-up `state` carries the run again, and its log must still be there.
    const { store, sim } = await wired();
    sim.programs.startRun("sort_cubes", { dry_run: true, confirm: [], fps: 30 });
    const live = sim.status().program;
    if (!live) throw new Error("no run");
    store.handle({ type: "program_state", ...live });
    store.handle({
      type: "program_log",
      run_id: live.run_id,
      seq: 900,
      t: 0,
      level: "info",
      kind: "start",
      block_id: null,
      message: "start",
      data: {},
    });
    store.setStatus({ ...sim.status(), program: null });
    expect(store.getSnapshot().program).toBeNull();
    store.setStatus(sim.status());
    expect(store.getSnapshot().program?.run_id).toBe(live.run_id);
    expect(store.getSnapshot().programLog.some((l) => l.seq === 900)).toBe(true);
  });

  it("stores trajectory_record progress and signals", () => {
    const s = new StationStore();
    s.handle({
      type: "trajectory_record",
      session_id: "s1",
      phase: "capture",
      elapsed_s: 1,
      limit_s: 60,
      samples: 30,
      trajectory_id: null,
      ended: false,
    });
    expect(s.getSnapshot().trajRecord?.samples).toBe(30);
    s.handle({ type: "signal", name: "door", value: "open", source: "http", at: "x", seq: 3 });
    expect(s.getSnapshot().signals.door?.value).toBe("open");
  });
});

describe("mock station: trajectories", () => {
  it("records a take with the leader: countdown, capture, stop → a draft with an idle trim suggestion", async () => {
    const { sim, store } = await wired();
    sim.programs.startRecord({ name: "Take A", fps: 30, limit_s: 60, countdown_s: 3, keyframe_hz: 1 });
    expect(sim.state).toBe("recording_traj");
    expect(sim.sub).toBe("countdown");
    run(sim, 3.1);
    expect(sim.sub).toBe("capture");
    run(sim, 4);
    expect(store.getSnapshot().trajRecord?.phase).toBe("capture");
    const draft = sim.programs.stopRecord();
    expect(sim.state).toBe("idle");
    expect(draft.status).toBe("draft");
    expect(draft.name).toBe("Take A");
    expect(draft.suggested_trim.start_s).toBeGreaterThan(0.5);
    expect(store.getSnapshot().trajRecord).toMatchObject({ ended: true, trajectory_id: draft.id });
  });

  it("stops a take on its time limit", () => {
    const sim = new MockStation({ connected: true });
    sim.programs.startRecord({ fps: 30, limit_s: 2, countdown_s: 0, keyframe_hz: 0 });
    run(sim, 2.5);
    expect(sim.state).toBe("idle");
    expect(sim.programs.takes[0]?.meta.status).toBe("draft");
  });

  it("replays at 50 %: approach, then twice the duration; refuses > 100 % without the profile flag", () => {
    const sim = new MockStation({ connected: true });
    const dur = sim.programs.take(A).meta.duration_s;
    expect(() => sim.programs.startPlay(A, { speed_pct: 150 })).toThrow("fast_replay_not_allowed");
    sim.programs.startPlay(A, { speed_pct: 50 });
    expect(sim.state).toBe("playing");
    expect(sim.sub).toBe("approach");
    run(sim, 1.1);
    expect(sim.sub).toBe("replay");
    run(sim, dur * 2 - 0.3);
    expect(sim.state).toBe("playing");
    run(sim, 0.5);
    expect(sim.state).toBe("idle");
  });

  it("e-stop mid-replay drops the player within the step", () => {
    const sim = new MockStation({ connected: true });
    sim.programs.startPlay(A, { speed_pct: 100 });
    run(sim, 2);
    sim.estop("user");
    expect(sim.state).toBe("estopped");
    expect(sim.programs.play).toBeNull();
  });

  it("needs_check: only a 25 % check replay, then confirm", () => {
    const sim = new MockStation({ connected: true });
    const old = "t_20261110_090000_e5f6";
    expect(() => sim.programs.startPlay(old, { speed_pct: 100 })).toThrow("needs_check");
    expect(() => sim.programs.confirmTrajectory(old)).toThrow("needs_check");
    sim.programs.startPlay(old, { check: true });
    expect(sim.programs.play?.speed).toBe(25);
    run(sim, 30);
    expect(sim.programs.confirmTrajectory(old).status).toBe("ready");
  });

  it("suggests no trim when the take moves from the first sample", () => {
    const t = [0, 0.1, 0.2, 0.3];
    expect(suggestTrim(t, [[0], [5], [10], [15]])).toEqual({ start_s: 0, end_s: 0 });
  });
});

describe("mock station: programs", () => {
  it("the A/B program runs with keys 1/2 in a dry run, without leaving idle, with a trace", async () => {
    const { sim, store } = await wired();
    sim.programs.startRun("sort_cubes", { dry_run: true, confirm: [], fps: 30 });
    expect(sim.state).toBe("idle");
    run(sim, 0.5);
    expect(store.getSnapshot().program).toMatchObject({ status: "waiting", keys: ["1", "2"], dry_run: true });
    sim.programs.input("sort_cubes", { kind: "key", value: "1" });
    run(sim, 0.3);
    expect(store.getSnapshot().program?.block_id).toBe("play_a");
    run(sim, 12);
    sim.programs.input(null, { kind: "key", value: "2" });
    run(sim, 0.3);
    expect(store.getSnapshot().program?.block_id).toBe("play_b");
    const log = store.getSnapshot().programLog;
    expect(log.some((l) => l.kind === "motion" && l.block_id === "play_a")).toBe(true);
    expect(log.some((l) => l.kind === "input" && l.message === "key 2")).toBe(true);
  });

  it("a fake camera label picks the branch in a dry run", () => {
    const sim = new MockStation({ connected: true });
    sim.programs.startRun("sort_cubes", { dry_run: true, confirm: [], fps: 30 });
    sim.programs.fake("sort_cubes", {
      detectors: { cube_color: { label: "blue", confidence: 1 } },
      clear: false,
    });
    run(sim, 0.5);
    expect(sim.programs.run?.state.block_id).toBe("play_b");
  });

  it("a hardware run needs a passed dry run of the version, then enters programming", () => {
    const sim = new MockStation({ connected: true });
    expect(() => sim.programs.startRun("sort_cubes", { dry_run: false, confirm: [], fps: 30 })).toThrow(
      "dry_run_required",
    );
    sim.programs.startRun("sort_cubes", { dry_run: true, confirm: [], fps: 30 });
    run(sim, 0.3);
    sim.programs.stopProgram("sort_cubes");
    sim.programs.startRun("sort_cubes", { dry_run: false, confirm: [], fps: 30 });
    expect(sim.state).toBe("programming");
    expect(sim.status().session?.kind).toBe("program");
  });

  it("pause waits for the motion block to finish; resume continues", () => {
    const sim = new MockStation({ connected: true });
    sim.programs.startRun("sort_cubes", { dry_run: true, confirm: [], fps: 30 });
    run(sim, 0.2);
    sim.programs.input("sort_cubes", { kind: "key", value: "1" });
    run(sim, 1);
    expect(sim.programs.run?.state.waiting?.kind).toBe("motion");
    sim.programs.pause("sort_cubes");
    expect(sim.programs.run?.state.status).toBe("pausing");
    run(sim, 10);
    expect(sim.programs.run?.state.status).toBe("paused");
    sim.programs.resume("sort_cubes");
    run(sim, 0.3);
    expect(["running", "waiting"]).toContain(sim.programs.run?.state.status);
  });

  it("e-stop aborts a hardware run and a dry run within one step; it never resumes", () => {
    const sim = new MockStation({ connected: true });
    sim.programs.startRun("sort_cubes", { dry_run: true, confirm: [], fps: 30 });
    run(sim, 0.3);
    sim.estop("user");
    expect(sim.programs.run).toBeNull();
    expect(sim.programs.stateOf("sort_cubes").status).toBe("estopped");
    sim.estopReset();
    run(sim, 1);
    expect(sim.programs.run).toBeNull();
  });

  it("the dead-man stops a hardware program when the UI goes away", () => {
    const sim = new MockStation({ connected: true, deadman: true });
    const p = sim.programs.program("sort_cubes");
    p.dry_run_version = p.version;
    sim.programs.startRun("sort_cubes", { dry_run: false, confirm: [], fps: 30 });
    run(sim, 1.2);
    expect(sim.state).toBe("estopped");
    expect(sim.programs.stateOf("sort_cubes").status).toBe("estopped");
  });

  it("check flags busy loops, missing trajectories, fast replays (confirm) and unreachable stacks", () => {
    const sim = new MockStation({ connected: true });
    const doc = {
      blocks: {
        blocks: [
          {
            type: "hb_start",
            id: "s",
            inputs: {
              DO: {
                block: {
                  type: "hb_repeat_forever",
                  id: "f",
                  inputs: {
                    DO: {
                      block: {
                        type: "hb_log",
                        id: "l",
                        inputs: { TEXT: { block: { type: "text", id: "t", fields: { TEXT: "x" } } } },
                      },
                    },
                  },
                  next: {
                    block: {
                      type: "hb_play_trajectory",
                      id: "p",
                      fields: { TRAJECTORY: "t_20990101_000000_dead", SPEED: 120 },
                    },
                  },
                },
              },
            },
          },
          { type: "hb_go_home", id: "lonely" },
        ],
      },
    };
    const codes = sim.programs.check(doc, []).map((i) => `${i.code}:${i.block_id ?? ""}:${i.severity}`);
    expect(codes).toEqual(
      expect.arrayContaining([
        "busy_loop:f:error",
        "unknown_trajectory:p:error",
        "fast_replay_not_allowed:p:error",
        "unreachable:lonely:warning",
      ]),
    );
    const p = sim.programs.putProgram("bad", { name: "Bad", editor: doc, buttons: [] });
    expect(p.ast).toBeNull();
    expect(() => sim.programs.startRun("bad", { dry_run: true, confirm: [], fps: 30 })).toThrow(
      "program_invalid",
    );
  });

  it("ask operator stores the answer in the text variable", () => {
    const sim = new MockStation({ connected: true });
    sim.programs.putProgram("ask", {
      name: "Ask",
      buttons: [],
      editor: {
        variables: [{ name: "answer", id: "va", type: "String" }],
        blocks: {
          blocks: [
            {
              type: "hb_start",
              id: "s",
              inputs: {
                DO: {
                  block: {
                    type: "hb_ask_operator",
                    id: "q",
                    fields: { QUESTION: "Which?", CHOICES: "left, right", VAR: { id: "va" }, TIMEOUT: "" },
                  },
                },
              },
            },
          ],
        },
      },
    });
    sim.programs.startRun("ask", { dry_run: true, confirm: [], fps: 30 });
    run(sim, 0.2);
    expect(sim.programs.run?.state.ask).toEqual({
      block_id: "q",
      question: "Which?",
      choices: ["left", "right"],
    });
    sim.programs.input("ask", { kind: "answer", value: "right" });
    run(sim, 0.2);
    expect(sim.programs.stateOf("ask")).toMatchObject({
      status: "completed",
      variables: { answer: "right" },
    });
  });
});

describe("Hibi mood (programs §8)", () => {
  it("works while a program runs, sleeps while it waits, is sad after a fault or e-stop", () => {
    const sim = new MockStation({ connected: true });
    const p = sim.programs.program("sort_cubes");
    p.dry_run_version = p.version;
    // Look where the mock camera shows no cube, so the program waits for a key.
    const det = sim.programs.detector("cube_color");
    if (det.spec.kind === "color") det.spec.roi = { x: 0, y: 0, w: 0.1, h: 0.1 };
    sim.programs.startRun("sort_cubes", { dry_run: false, confirm: [], fps: 30 });
    run(sim, 0.3);
    expect(sim.sub).toBe("waiting");
    expect(hibiMood(sim.status())).toBe("sleep");
    sim.programs.input("sort_cubes", { kind: "key", value: "1" });
    run(sim, 0.2);
    expect(hibiMood(sim.status())).toBe("working");
    expect(programMood(state({ status: "running" }))).toBe("working");
    expect(programMood(state({ status: "waiting" }))).toBe("sleep");
    expect(programMood(state({ status: "estopped" }))).toBe("sad");
    expect(programMood(state({ status: "failed" }))).toBe("sad");
    expect(programMood(state({ status: "completed" }))).toBe("happy");
  });
});

describe("run log and block labels in the operator's language (programs §5.1, §8)", () => {
  const label = (id: string) => ({ c_red: "camera thấy red", play_a: "phát quỹ đạo A" })[id] ?? id;
  async function viT() {
    const i = i18next.createInstance();
    await i.init({ lng: "vi", ns: ["station"], defaultNS: "station", resources: { vi: { station: vi } } });
    return i.getFixedT("vi", "station");
  }
  const line = (kind: string, block_id: string | null, message: string, data: Record<string, unknown> = {}) =>
    ({ kind, block_id, message, data }) as Parameters<typeof logLineText>[0];

  it("words the Station's machine lines (block ids, True/False, kinds) in Vietnamese", async () => {
    const t = await viT();
    expect(logLineText(line("condition", "c_red", "c_red = True", { value: true }), t, label)).toBe(
      "điều kiện · camera thấy red = đúng",
    );
    expect(
      logLineText(line("motion", "play_a", "play_trajectory completed", { outcome: "completed" }), t, label),
    ).toBe("chuyển động · phát quỹ đạo A · xong");
    expect(logLineText(line("motion", "play_a", "play_trajectory start"), t, label)).toBe(
      "chuyển động · phát quỹ đạo A · bắt đầu",
    );
    expect(
      logLineText(line("start", null, "program ab v2 (dry run)", { version: 2, dry_run: true }), t, label),
    ).toBe("bắt đầu · v2 · chạy thử");
    expect(logLineText(line("end", null, "e-stop", { outcome: "estopped" }), t, label)).toBe(
      "kết thúc · Dừng khẩn cấp",
    );
    expect(logLineText(line("input", null, "key 1", { kind: "key", value: "1" }), t, label)).toBe(
      "thao tác · Phím 1",
    );
  });

  it("keeps user text and fault details as written", async () => {
    const t = await viT();
    expect(logLineText(line("log", "l1", "xin chào"), t, label)).toBe("nhật ký · xin chào");
    expect(
      logLineText(line("end", null, "wait until timed out after 30 s", { outcome: "timeout" }), t, label),
    ).toBe("kết thúc · Hết thời gian · wait until timed out after 30 s");
  });

  it("names what a block works on: trajectory name, detector label, key, button", () => {
    const refs = {
      ...emptyRefs(),
      trajectories: [{ value: "t_1", label: "A" }],
      buttons: [{ value: "go", label: "Bắt đầu" }],
    };
    expect(blockDetail({ TRAJECTORY: "t_1", SPEED: 100 }, refs)).toBe("A");
    expect(blockDetail({ DETECTOR: "cube", LABEL: "blue", CAMERA: "" }, refs)).toBe("blue");
    expect(blockDetail({ KEY: "a" }, refs)).toBe("A");
    expect(blockDetail({ BUTTON: "go" }, refs)).toBe("Bắt đầu");
    expect(blockDetail({ SECONDS: 3 }, refs)).toBeNull();
  });
});
