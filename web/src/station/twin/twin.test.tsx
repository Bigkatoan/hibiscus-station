import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MotorSample } from "../api/types";
import { DEFAULT_THRESHOLDS } from "../health";
import { advance, renderWithStation, settle, setupStation } from "../test/utils";
import { keptWindow } from "./GhostPreview";
import {
  GRIPPER_OPEN_RAD,
  jointToUrdf,
  LEVEL_COLOR,
  levelColor,
  motorLevels,
  REST_POSE,
  sampleSeries,
  seriesDuration,
  toUrdfPose,
  UNKNOWN_COLOR,
  URDF_LIMITS,
} from "./mapping";
import { RobotTwin } from "./RobotTwin";
import { TwinDock, TwinSection } from "./TwinDock";
import type { TwinCanvasProps } from "./TwinCanvas";
import { resetWebGLProbe } from "./webgl";

// The WebGL canvas is replaced by a recorder: jsdom has no WebGL. The props it receives are real.
const canvasProps: TwinCanvasProps[] = [];
/** What the fake canvas reports once mounted (a real one reports "no-webgl" when the context fails). */
let canvasOutcome: "ready" | "no-webgl" = "ready";
vi.mock("./TwinCanvas", async () => {
  const { useEffect } = await import("react");
  return {
    default: function FakeTwinCanvas(props: TwinCanvasProps) {
      canvasProps.push(props);
      const { onState } = props;
      useEffect(() => {
        onState(canvasOutcome);
      }, [onState]);
      return <div data-testid="twin-canvas" data-ghost={props.ghost ? JSON.stringify(props.ghost) : ""} />;
    },
  };
});

const DEG = Math.PI / 180;

describe("twin joint mapping (Station degrees / % → URDF radians)", () => {
  it("maps arm joints 1:1 in degrees (0° = middle of the calibrated range = URDF zero)", () => {
    expect(jointToUrdf("shoulder_pan", 0)).toBe(0);
    expect(jointToUrdf("shoulder_pan", 45)).toBeCloseTo(45 * DEG);
    expect(jointToUrdf("shoulder_lift", -30)).toBeCloseTo(-30 * DEG);
    expect(jointToUrdf("elbow_flex", 90)).toBeCloseTo(90 * DEG);
    expect(jointToUrdf("wrist_flex", -12.5)).toBeCloseTo(-12.5 * DEG);
    expect(jointToUrdf("wrist_roll", 120)).toBeCloseTo(120 * DEG);
  });

  it("maps the gripper 0–100 % onto the jaw: 0 % closed, 100 % open", () => {
    expect(jointToUrdf("gripper", 0)).toBe(0);
    expect(jointToUrdf("gripper", 50)).toBeCloseTo(GRIPPER_OPEN_RAD / 2);
    expect(jointToUrdf("gripper", 100)).toBeCloseTo(GRIPPER_OPEN_RAD);
  });

  it("clamps to the URDF limits", () => {
    expect(jointToUrdf("elbow_flex", 400)).toBe(URDF_LIMITS.elbow_flex[1]);
    expect(jointToUrdf("shoulder_lift", -400)).toBe(URDF_LIMITS.shoulder_lift[0]);
    expect(jointToUrdf("gripper", 150)).toBe(URDF_LIMITS.gripper[1]);
    expect(jointToUrdf("gripper", -50)).toBe(URDF_LIMITS.gripper[0]);
  });

  it("reads `.pos` keys and bare names, skipping missing and non-finite values", () => {
    expect(toUrdfPose({ "shoulder_pan.pos": 90, elbow_flex: -45, "gripper.pos": 100 })).toEqual({
      shoulder_pan: 90 * DEG,
      elbow_flex: -45 * DEG,
      gripper: GRIPPER_OPEN_RAD,
    });
    expect(toUrdfPose({ "wrist_flex.pos": Number.NaN, "wrist_roll.pos": null })).toEqual({});
    expect(toUrdfPose(null)).toEqual({});
  });

  it("folds the arm for the usual SO-101 rest reading (lift −100°, elbow +97°)", () => {
    const pose = toUrdfPose({ "shoulder_lift.pos": -100, "elbow_flex.pos": 97, "wrist_flex.pos": 70 });
    expect(pose.shoulder_lift).toBeCloseTo(URDF_LIMITS.shoulder_lift[0], 3); // leaning back on its stop
    expect(pose.elbow_flex).toBeCloseTo(97 * DEG); // forearm folded down over the upper arm
    expect(Object.values(REST_POSE).every((v) => v === 0)).toBe(true);
  });
});

function sample(temp: number | null, extra: Partial<MotorSample> = {}): MotorSample {
  return {
    temp_c: temp,
    level: "ok",
    stale: false,
    status: [],
    load_pct: 0,
    current_a: 0,
    voltage_v: 7.4,
    ...extra,
  };
}

describe("twin temperature colours", () => {
  it("uses the profile thresholds: warn ≥ 50 °C, hot ≥ 60 °C", () => {
    const levels = motorLevels(
      {
        shoulder_pan: sample(30),
        shoulder_lift: sample(50),
        elbow_flex: sample(59.9),
        wrist_flex: sample(60),
        wrist_roll: sample(66),
        gripper: sample(40, { stale: true }),
      },
      DEFAULT_THRESHOLDS,
    );
    expect(levels).toEqual({
      shoulder_pan: "ok",
      shoulder_lift: "warn",
      elbow_flex: "warn",
      wrist_flex: "hot",
      wrist_roll: "critical",
      gripper: null,
    });
    expect(levelColor("ok")).toBe(LEVEL_COLOR.ok);
    expect(levelColor("hot")).toBe(LEVEL_COLOR.hot);
    expect(levelColor(null)).toBe(UNKNOWN_COLOR);
    expect(new Set(Object.values(LEVEL_COLOR)).size).toBe(4);
  });

  it("follows custom thresholds and the server level", () => {
    const th = { temp_warn_c: 40, temp_hot_c: 45, temp_critical_c: 55 };
    expect(motorLevels({ elbow_flex: sample(46) }, th).elbow_flex).toBe("hot");
    expect(motorLevels({ elbow_flex: sample(30, { level: "hot" }) }, th).elbow_flex).toBe("hot");
    expect(motorLevels(undefined, th).elbow_flex).toBeNull();
  });
});

describe("ghost playback sampling", () => {
  const s = { t: [0, 1, 2], joints: { "elbow_flex.pos": [0, 10, 30], "gripper.pos": [100, 50, 0] } };

  it("interpolates between samples and holds at both ends", () => {
    expect(sampleSeries(s, 0)).toEqual({ "elbow_flex.pos": 0, "gripper.pos": 100 });
    expect(sampleSeries(s, 0.5)).toEqual({ "elbow_flex.pos": 5, "gripper.pos": 75 });
    expect(sampleSeries(s, 1.5)).toEqual({ "elbow_flex.pos": 20, "gripper.pos": 25 });
    expect(sampleSeries(s, 9)).toEqual({ "elbow_flex.pos": 30, "gripper.pos": 0 });
    expect(sampleSeries(s, -1)).toEqual({ "elbow_flex.pos": 0, "gripper.pos": 100 });
    expect(seriesDuration(s)).toBe(2);
  });

  it("spreads a t-less preview evenly over its duration", () => {
    const p = { joints: { "wrist_roll.pos": [0, 20, 40, 60, 80] } };
    expect(sampleSeries(p, 2, 4)).toEqual({ "wrist_roll.pos": 40 });
    expect(sampleSeries(p, 3.5, 4)).toEqual({ "wrist_roll.pos": 70 });
    expect(seriesDuration(p, 4)).toBe(4);
    expect(sampleSeries({ joints: {} }, 1)).toEqual({});
  });

  it("plays only the kept part of a take (drafts use the suggested trim)", () => {
    const base = {
      raw_duration_s: 10,
      trim: { start_s: 1, end_s: 2 },
      suggested_trim: { start_s: 3, end_s: 3 },
    };
    expect(keptWindow({ ...base, status: "ready" })).toEqual({ start: 1, end: 8 });
    expect(keptWindow({ ...base, status: "draft" })).toEqual({ start: 3, end: 7 });
  });
});

/** jsdom has no WebGL: give it the WebGL 2 API, and a context or none from getContext. */
const hadWebGL2 = "WebGL2RenderingContext" in window;
function fakeWebGL(context: boolean) {
  Object.assign(window, { WebGL2RenderingContext: Object });
  const spy = vi
    .spyOn(HTMLCanvasElement.prototype, "getContext")
    .mockImplementation(((type: string) =>
      type === "webgl2" && context
        ? { getExtension: () => ({ loseContext: vi.fn() }) }
        : null) as unknown as HTMLCanvasElement["getContext"]);
  resetWebGLProbe();
  return spy;
}
function noWebGLApi(): void {
  delete (window as { WebGL2RenderingContext?: unknown }).WebGL2RenderingContext;
  resetWebGLProbe();
}

describe("RobotTwin component", () => {
  beforeEach(() => {
    canvasProps.length = 0;
    canvasOutcome = "ready";
    fakeWebGL(true);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    if (!hadWebGL2) noWebGLApi();
  });

  it("feeds motor levels from live telemetry and shows them in the legend", async () => {
    const h = setupStation();
    Object.assign(h.sim.temps.follower, { elbow_flex: 61, shoulder_lift: 52 });
    renderWithStation(<RobotTwin />, h);
    await settle();
    await advance(h.sim, 1.0);
    await waitFor(() => {
      expect(screen.getByTestId("robot-twin")).toHaveAttribute("data-state", "ready");
    });
    await waitFor(() => {
      expect(canvasProps.at(-1)?.levels.elbow_flex).toBe("hot");
    });
    expect(canvasProps.at(-1)?.levels.shoulder_lift).toBe("warn");
    expect(canvasProps.at(-1)?.levels.shoulder_pan).toBe("ok");
    const legend = screen.getByTestId("twin-legend");
    expect(legend.querySelector('[data-motor="elbow_flex"]')).toHaveAttribute("data-level", "hot");
    expect(screen.getByTestId("twin-source")).toHaveTextContent("Mock arm");
    // Reset view bumps the key the canvas watches.
    fireEvent.click(screen.getByRole("button", { name: "Reset view" }));
    expect(canvasProps.at(-1)?.resetKey).toBe(1);
  });

  it("passes the ghost pose through", async () => {
    const h = setupStation();
    renderWithStation(<RobotTwin ghost={{ elbow_flex: 0.5 }} legend={false} />, h);
    await settle();
    await waitFor(() => {
      expect(screen.getByTestId("twin-canvas")).toHaveAttribute("data-ghost", '{"elbow_flex":0.5}');
    });
    expect(screen.queryByTestId("twin-legend")).toBeNull();
  });

  it("explains instead of crashing when the browser has no WebGL", async () => {
    noWebGLApi();
    const h = setupStation();
    renderWithStation(<RobotTwin />, h);
    await settle();
    expect(screen.getByTestId("robot-twin")).toHaveAttribute("data-state", "no-webgl");
    expect(screen.getByRole("note")).toHaveTextContent("WebGL");
    expect(screen.queryByTestId("twin-canvas")).toBeNull();
  });

  it("shows the note, without loading three.js, when getContext gives no WebGL 2 context", async () => {
    const getContext = fakeWebGL(false);
    const error = vi.spyOn(console, "error");
    const h = setupStation();
    renderWithStation(<RobotTwin />, h);
    await settle();
    expect(getContext).toHaveBeenCalledWith("webgl2", expect.anything());
    expect(screen.getByTestId("robot-twin")).toHaveAttribute("data-state", "no-webgl");
    expect(screen.getByTestId("twin-no-webgl")).toHaveTextContent(
      "This computer cannot show the 3D model (the browser does not support WebGL). Everything else still works.",
    );
    expect(canvasProps).toHaveLength(0); // the three.js chunk is never mounted
    expect(screen.queryByRole("button", { name: "Reset view" })).toBeNull();
    expect(screen.queryByTestId("twin-legend")).toBeNull();
    expect(error).not.toHaveBeenCalled();
  });

  it("falls back the same way when the probe passed but the renderer's context fails", async () => {
    canvasOutcome = "no-webgl";
    const h = setupStation();
    renderWithStation(<RobotTwin />, h);
    await settle();
    await waitFor(() => {
      expect(screen.getByTestId("robot-twin")).toHaveAttribute("data-state", "no-webgl");
    });
    expect(screen.getByTestId("twin-no-webgl")).toHaveTextContent("3D model");
    expect(screen.queryByTestId("twin-canvas")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull(); // calm note, not the "could not be loaded" error
  });
});

describe("twin placement (dock / section)", () => {
  const realMatchMedia = window.matchMedia.bind(window);
  function setDesktop(desktop: boolean): void {
    window.matchMedia = (query: string) =>
      ({
        matches: desktop && query.includes("min-width"),
        media: query,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
      }) as unknown as MediaQueryList;
  }
  beforeEach(() => {
    fakeWebGL(true);
  });
  afterEach(() => {
    window.matchMedia = realMatchMedia;
    vi.restoreAllMocks();
    if (!hadWebGL2) noWebGLApi();
  });

  it("docks on desktop, collapses and remembers it, and hides while a page shows one inline", async () => {
    setDesktop(true);
    const h = setupStation();
    const view = renderWithStation(
      <>
        <TwinDock />
        <TwinSection />
      </>,
      h,
    );
    await settle();
    expect(screen.getByTestId("twin-dock")).toBeInTheDocument();
    expect(screen.queryByTestId("twin-section")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Hide Robot 3D" }));
    expect(screen.queryByTestId("twin-dock")).toBeNull();
    expect(window.localStorage.getItem("hibiscus.station.twin.dock")).toBe("0");
    fireEvent.click(screen.getByRole("button", { name: "Show Robot 3D" }));
    expect(screen.getByTestId("twin-dock")).toBeInTheDocument();
    view.unmount();

    // An inline twin on the page hides the dock.
    renderWithStation(
      <>
        <TwinDock />
        <RobotTwin />
      </>,
      h,
    );
    await settle();
    expect(screen.getAllByTestId("robot-twin")).toHaveLength(1);
    expect(screen.queryByTestId("twin-dock")).toBeNull();
  });

  it("is a closed 'Robot 3D' section on narrow screens", async () => {
    setDesktop(false);
    const h = setupStation();
    renderWithStation(
      <>
        <TwinDock />
        <TwinSection />
      </>,
      h,
    );
    await settle();
    expect(screen.queryByTestId("twin-dock")).toBeNull();
    const toggle = screen.getByRole("button", { name: /Robot 3D/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("robot-twin")).toBeNull();
    act(() => {
      toggle.click();
    });
    expect(screen.getByTestId("robot-twin")).toBeInTheDocument();
    expect(window.localStorage.getItem("hibiscus.station.twin.section")).toBe("1");
  });
});
