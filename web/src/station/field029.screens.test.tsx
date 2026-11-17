/**
 * Field report 0.2.8 → 0.2.9 against the mock Station: leader telemetry that reads as connected
 * ("not measured" with its reason, never a bare dash), the record Stop that ends the episode at
 * once, CR-1 (Stop holds, then "Return Home" / "Relax") and CR-2 ("Home").
 */
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MotorHealthPanel } from "./components/MotorHealthPanel";
import { MAX_EXTRAPOLATE_S, extrapolate } from "./components/SessionWidgets";
import { advance, renderStation, renderWithStation, settle, setupStation } from "./test/utils";

beforeEach(() => {
  vi.stubGlobal(
    "createImageBitmap",
    vi.fn(() => Promise.resolve({ width: 320, height: 240, close: vi.fn() })),
  );
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    () =>
      ({
        drawImage: vi.fn(),
        measureText: (s: string) => ({ width: s.length * 7 }),
        font: "",
      }) as unknown as CanvasRenderingContext2D,
  );
  return () => {
    vi.unstubAllGlobals();
  };
});

describe("Leader telemetry (field report 2)", () => {
  it("says the leader is connected and its 5 V servos do not measure temperature or current", async () => {
    const h = setupStation();
    renderWithStation(<MotorHealthPanel />, h);
    await settle();
    await advance(h.sim, 1.0);
    const row = await screen.findByTestId("motor-leader-gripper");
    expect(row).not.toHaveTextContent("–");
    const unmeasured = within(row).getAllByTestId("not-measured");
    expect(unmeasured).toHaveLength(2); // temperature and current
    for (const el of unmeasured) {
      expect(el).toHaveTextContent("not measured");
      expect(el).toHaveAttribute("title", expect.stringContaining("connected") as string);
    }
    expect(within(row).getByText("5.0")).toBeInTheDocument();
    expect(screen.getByTestId("leader-connected")).toHaveTextContent("Connected · 6/6 motors answer");
    // the follower keeps its measured values
    const f = screen.getByTestId("motor-follower-gripper");
    expect(within(f).queryByTestId("not-measured")).toBeNull();
    await waitFor(() => {
      expect(within(f).getByText(/°C/)).toBeInTheDocument();
    });
  });
});

describe("Record Stop (field report 1)", () => {
  it("ends the episode at the press: the timer stops, the page says it saves, then the end card", async () => {
    const h = setupStation({ paired: true });
    h.sim.startSession("record", {
      dataset: "cube",
      task: "Pick",
      num_episodes: 1,
      episode_time_s: 30,
      reset_time_s: 0,
      countdown_s: 0.1,
    });
    renderStation("/record", h);
    await settle();
    await advance(h.sim, 5.2);
    expect(await screen.findByText(/Episode 1 \/ 1 · recording/)).toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(await screen.findByText("Saving episode 1…")).toBeInTheDocument();
    expect(screen.getByTestId("record-saving")).toHaveTextContent("holds its position");
    expect(screen.getByTestId("session-timer")).toHaveTextContent(/00:05\s*\/\s*00:30/);
    await advance(h.sim, 0.5);
    expect(screen.getByTestId("session-timer")).toHaveTextContent(/00:05\s*\/\s*00:30/);
    await advance(h.sim, 0.7);
    const done = await screen.findByTestId("record-done");
    expect(done).toHaveTextContent("1 episode saved");
  });
});

describe("Episode timer", () => {
  it("never runs more than 2 s ahead of the last message from the Station", () => {
    expect(extrapolate(5, 0, 1000, true, 30)).toBeCloseTo(6);
    expect(extrapolate(5, 0, 25_000, true, 30)).toBeCloseTo(5 + MAX_EXTRAPOLATE_S);
    expect(extrapolate(29.5, 0, 5000, true, 30)).toBe(30);
    expect(extrapolate(5, 0, 5000, false, 30)).toBe(5);
  });
});

const HOME = { "shoulder_pan.pos": 0, "shoulder_lift.pos": -90, "elbow_flex.pos": 90 };

/** The only program: start → go Home, saved while the robot had a Home (stored issues: none). */
function homeProgram(h: ReturnType<typeof setupStation>) {
  h.sim.programs.programs = [];
  const prog = h.sim.programs.putProgram("go_home_test", {
    name: "Go Home test",
    editor: {
      blocks: {
        languageVersion: 0,
        blocks: [
          {
            type: "hb_start",
            id: "start",
            x: 40,
            y: 40,
            inputs: { DO: { block: { type: "hb_go_home", id: "gh" } } },
          },
        ],
      },
    },
    buttons: [],
  });
  prog.issues = [];
  return prog;
}

describe("CR-1: Stop holds, then Return Home / Relax", () => {
  it("after a Stop the banner says the arm holds and Relax asks to support the arm first", async () => {
    const h = setupStation();
    const p = h.sim.profiles[0];
    if (p) p.follower.rest_pose = { ...HOME };
    const user = userEvent.setup();
    renderStation("/teleop", h);
    await settle();
    h.sim.startSession("teleop", {});
    h.sim.controlAction("stop");
    const banner = await screen.findByTestId("rest-banner");
    expect(banner).toHaveTextContent("Stopped. The arm holds its position.");
    expect(within(banner).getByRole("button", { name: /Return Home/ })).toBeEnabled();
    await user.click(within(banner).getByRole("button", { name: "Relax" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Support the arm");
    expect(h.sim.torque).toBe(true); // nothing happens before the confirmation
    await user.click(within(dialog).getByRole("button", { name: "I am holding it, relax" }));
    await waitFor(() => {
      expect(h.sim.torque).toBe(false);
    });
    expect(await screen.findByTestId("support-arm")).toHaveTextContent("Support the arm");
    // QC 0.2.9 QD-4: once relaxed the headline never says the arm holds, nor offers a Relax it hides
    expect(banner).toHaveAttribute("data-torque", "off");
    expect(screen.getByTestId("rest-headline")).toHaveTextContent(
      "Stopped. Torque is off: the arm is limp and does not hold its position.",
    );
    expect(banner).not.toHaveTextContent("holds its position");
    expect(banner).not.toHaveTextContent(/Relax/);
    expect(within(banner).queryByRole("button", { name: "Relax" })).toBeNull();
  });

  it("a double Space (relax) then reset: the stop card says torque off, in vi too (QD-4)", async () => {
    const h = setupStation();
    const p = h.sim.profiles[0];
    if (p) p.follower.rest_pose = { ...HOME };
    const user = userEvent.setup();
    renderStation("/teleop", h);
    await settle();
    h.sim.startSession("teleop", {});
    h.sim.estop("user");
    h.sim.estop("user"); // second press within 2 s: torque off
    expect(h.sim.torque).toBe(false);
    const dock = await screen.findByTestId("estop-dock");
    await user.click(within(dock).getByRole("button", { name: "I'm clear, reset" }));
    const banner = await screen.findByTestId("rest-banner");
    expect(banner).toHaveTextContent("Stopped. Torque is off");
    expect(banner).toHaveTextContent("Support the arm. Torque is off.");
    expect(banner).not.toHaveTextContent("holds its position");
    expect(within(banner).getByRole("button", { name: /Return Home/ })).toBeEnabled();
    const { i18n } = await import("@/lib/i18n");
    await i18n.changeLanguage("vi");
    try {
      await waitFor(() => {
        expect(screen.getByTestId("rest-headline")).toHaveTextContent("Mô-men đã tắt");
      });
      expect(banner).not.toHaveTextContent("giữ nguyên vị trí");
    } finally {
      await i18n.changeLanguage("en");
    }
  });

  it("a thermal safe stop never says the arm is held (QD-4)", async () => {
    const h = setupStation();
    renderStation("/teleop", h);
    await settle();
    h.sim.startSession("teleop", {});
    h.sim.temps.follower.elbow_flex = 66;
    await advance(h.sim, 1.1);
    expect(h.sim.state).toBe("estopped");
    const banner = await screen.findByTestId("critical-banner");
    expect(banner).toHaveTextContent("Support the arm. Torque is off.");
    expect(banner).not.toHaveTextContent("held in place");
  });

  it("after a user e-stop the dock offers Return Home, which resets the latch and moves Home", async () => {
    const h = setupStation();
    const p = h.sim.profiles[0];
    if (p) p.follower.rest_pose = { ...HOME };
    const user = userEvent.setup();
    renderStation("/teleop", h);
    await settle();
    h.sim.startSession("teleop", {});
    h.sim.estop("user");
    const dock = await screen.findByTestId("estop-dock");
    await user.click(within(dock).getByRole("button", { name: /Return Home/ }));
    await waitFor(() => {
      expect(h.sim.state).toBe("playing");
    });
    await advance(h.sim, 3.2);
    await waitFor(() => {
      expect(h.sim.state).toBe("idle");
    });
  });

  it("never offers Return Home after a thermal stop, and a second press says to support the arm", async () => {
    const h = setupStation();
    const p = h.sim.profiles[0];
    if (p) p.follower.rest_pose = { ...HOME };
    renderStation("/teleop", h);
    await settle();
    h.sim.startSession("teleop", {});
    h.sim.estop("thermal");
    const dock = await screen.findByTestId("estop-dock");
    expect(within(dock).queryByRole("button", { name: /Return Home/ })).toBeNull();
    h.sim.estop("user"); // second press within 2 s: torque off (D-6)
    expect(await screen.findByTestId("estop-support-arm")).toHaveTextContent("Support the arm");
  });
});

describe("CR-2: Home", () => {
  it("is set from the top bar and the Robot 3D panel and used by Return Home", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    renderStation("/teleop", h);
    await settle();
    const bar = await screen.findByTestId("home-bar");
    expect(within(bar).getByRole("button", { name: "Return Home" })).toBeDisabled();
    await user.click(within(bar).getByRole("button", { name: "Set Home at current position" }));
    await waitFor(() => {
      expect(h.sim.profiles[0]?.follower.rest_pose).toBeTruthy();
    });
    await waitFor(() => {
      expect(within(bar).getByRole("button", { name: "Return Home" })).toBeEnabled();
    });
    // Robot 3D carries the same pair; replacing Home asks first
    const panel = screen.getAllByTestId("home-panel")[0];
    if (!panel) throw new Error("no Robot 3D Home controls");
    await user.click(within(panel).getByRole("button", { name: /Set Home at current position/ }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("Replace Home?");
  });

  it("is asked for right after calibration when the robot has none", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    renderStation("/calibrate", h);
    await settle();
    const prompt = await screen.findByTestId("home-prompt");
    expect(prompt).toHaveTextContent("Set this robot's Home");
    await user.click(within(prompt).getByRole("button", { name: /Set Home at current position/ }));
    await waitFor(() => {
      expect(screen.queryByTestId("home-prompt")).toBeNull();
    });
  });

  it("a program block blocked by a missing Home offers Set Home now in place, then re-checks", async () => {
    const h = setupStation();
    homeProgram(h);
    const user = userEvent.setup();
    renderStation("/programs?tab=programs", h);
    await settle();
    const list = await screen.findByTestId("program-issues");
    expect(list).toHaveTextContent("Set Home for this robot first.");
    await user.click(within(list).getByRole("button", { name: "Set Home now" }));
    await waitFor(() => {
      expect(h.sim.profiles[0]?.follower.rest_pose).toBeTruthy();
    });
    expect(await screen.findByTestId("program-ok")).toBeInTheDocument();
  });
});

describe("Program problems on open (QC 0.2.9 QD-2)", () => {
  it("lists what the robot is missing without pressing Check, and never says 'No problems found' first", async () => {
    const h = setupStation();
    homeProgram(h); // this robot has no Home
    const seen: string[] = [];
    renderStation("/programs?tab=programs", h);
    const observer = new MutationObserver(() => {
      if (document.querySelector('[data-testid="program-ok"]')) seen.push("ok");
    });
    observer.observe(document.body, { childList: true, subtree: true });
    try {
      await settle();
      const list = await screen.findByTestId("program-issues");
      expect(list).toHaveTextContent("Set Home for this robot first.");
      expect(seen).toEqual([]);
      expect(screen.queryByTestId("program-ok")).toBeNull();
    } finally {
      observer.disconnect();
    }
  });
});

describe("Replay page (QC 0.2.9 QD-5)", () => {
  it("says it replays an episode, never 'recording', and drops the approach note after the approach", async () => {
    const h = setupStation();
    renderStation("/replay", h);
    await settle();
    h.sim.startSession("replay", { dataset: "cube_demo", episode: 2 });
    expect(await screen.findByText("Moving to the start of episode 3…")).toBeInTheDocument();
    expect(screen.getByTestId("approach-note")).toHaveTextContent(
      "Follower moving slowly to the first pose of the episode…",
    );
    await advance(h.sim, 2.0);
    expect(await screen.findByText(/^Replaying episode 3 · /)).toBeInTheDocument();
    expect(screen.queryByTestId("approach-note")).toBeNull();
    expect(document.body).not.toHaveTextContent("recording");
    expect(document.body).not.toHaveTextContent("leader pose");
  });
});
