/**
 * The "Chương trình / Programs" screen against the mock Station (station-programs.md §8): the three
 * tabs, recording and replaying a trajectory, a detector test, and the program editor + run panel
 * (dry run with keys, live highlight, pause/resume/stop, e-stop), plus a11y basics.
 */
import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import * as Blockly from "blockly/core";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { advance, renderStation, settle, setupStation, type StationHarness } from "./test/utils";
import { createRuntime } from "./ws/StationProvider";

beforeEach(() => {
  vi.stubGlobal(
    "createImageBitmap",
    vi.fn(() => Promise.resolve({ width: 320, height: 240, close: vi.fn() })),
  );
  // Blockly measures text on a canvas; the camera tiles draw on one.
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

async function axeViolations(): Promise<string[]> {
  // Blockly's own SVG workspace and its body-level helpers are third-party DOM with their own ARIA
  // tree; color-contrast needs layout (checked through the tokens instead).
  const res = await axe.run(
    {
      include: [document.body],
      exclude: [
        [".hb-blockly"],
        [".blocklyComputeCanvas"],
        [".blocklyWidgetDiv"],
        [".blocklyDropDownDiv"],
        [".blocklyTooltipDiv"],
      ],
    },
    { rules: { "color-contrast": { enabled: false } } },
  );
  return res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

async function openTab(h: StationHarness, tab: "trajectories" | "detection" | "programs") {
  renderStation(`/programs?tab=${tab}`, h);
  await settle();
}

describe("Programs screen", () => {
  it("is in the navigation and has the three tabs (en)", async () => {
    const h = setupStation();
    renderStation("/", h);
    await settle();
    const link = await screen.findByRole("link", { name: "Programs" });
    await userEvent.setup().click(link);
    const tabs = await screen.findByRole("tablist", { name: "Programs" });
    expect(
      within(tabs)
        .getAllByRole("tab")
        .map((t) => t.textContent?.trim()),
    ).toEqual(["Trajectories", "Detection", "Programs"]);
    expect(await axeViolations()).toEqual([]);
  });

  it("records a trajectory with the leader: countdown, capture, stop, review, save", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    await openTab(h, "trajectories");
    await user.type(await screen.findByLabelText("Name"), "Pick red");
    await user.click(screen.getByRole("button", { name: "Record" }));
    await waitFor(() => {
      expect(h.sim.state).toBe("recording_traj");
    });
    expect(await screen.findByText(/Starting in/)).toBeInTheDocument();
    await advance(h.sim, 3.2);
    await advance(h.sim, 3);
    expect(await screen.findByText(/Recording · /)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stop recording" }));
    const editor = await screen.findByTestId("traj-editor");
    expect(within(editor).getByText("Review the new take")).toBeInTheDocument();
    expect(within(editor).getByRole("img", { name: /Joint positions of Pick red/ })).toBeInTheDocument();
    expect(Number(within(editor).getByLabelText<HTMLInputElement>("Cut start (s)").value)).toBeGreaterThan(0);
    await user.click(within(editor).getByRole("button", { name: "Save take" }));
    await waitFor(() => {
      expect(screen.queryByTestId("traj-editor")).toBeNull();
    });
    const saved = h.sim.programs.takes.find((x) => x.meta.name === "Pick red");
    expect(saved?.meta.status).toBe("ready");
    expect(await screen.findByTestId(`traj-${saved?.meta.id ?? ""}`)).toBeInTheDocument();
  });

  it("plays a trajectory at 50 % with the moving-to-start phase and stops it", async () => {
    const h = setupStation({ deadman: false });
    const user = userEvent.setup();
    await openTab(h, "trajectories");
    const card = await screen.findByTestId("traj-t_20261116_101500_a1b2");
    expect(within(card).getByRole("option", { name: "150 %" })).toBeDisabled();
    await user.selectOptions(within(card).getByLabelText("Speed"), "50");
    await user.click(within(card).getByRole("button", { name: "Play" }));
    expect(await screen.findByText("Moving to the start pose…")).toBeInTheDocument();
    expect(h.sim.programs.play?.speed).toBe(50);
    await advance(h.sim, 1.2);
    expect(await screen.findByText("Replaying")).toBeInTheDocument();
    await user.click(within(screen.getByTestId("traj-playing")).getByRole("button", { name: "Stop" }));
    await waitFor(() => {
      expect(h.sim.state).toBe("idle");
    });
  });

  it("a trajectory that needs a check offers only the 25 % check replay and the confirm", async () => {
    const h = setupStation();
    await openTab(h, "trajectories");
    const card = await screen.findByTestId("traj-t_20261110_090000_e5f6");
    expect(within(card).getByText("Needs check")).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Play" })).toBeNull();
    expect(within(card).getByRole("button", { name: "Check at 25 %" })).toBeEnabled();
  });

  it("tests a colour detector on the live frame and edits its region", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    await openTab(h, "detection");
    await screen.findByRole("heading", { name: "Cube colour" });
    const editor = screen.getByTestId("detector-editor");
    await user.click(within(editor).getByRole("button", { name: "Test now" }));
    expect(await within(editor).findByText("Sees: red")).toBeInTheDocument();
    const left = within(editor).getByLabelText("Left %");
    fireEvent.change(left, { target: { value: "5" } });
    expect(within(editor).getByTestId("roi-box").style.left).toBe("5%");
    await user.click(within(editor).getByRole("button", { name: "Test now" }));
    expect(await within(editor).findByText("Nothing recognised")).toBeInTheDocument();
    expect(await axeViolations()).toEqual([]);
  });
});

describe("Program editor and run panel", () => {
  async function openEditor(h: StationHarness) {
    await openTab(h, "programs");
    await screen.findByTestId("blockly-editor");
    await waitFor(() => {
      expect(document.querySelector('[data-id="play_a"]')).not.toBeNull();
    });
  }

  it("shows the program in the Blockly editor with the toolbox categories", async () => {
    const h = setupStation();
    await openEditor(h);
    const names = [...document.querySelectorAll(".blocklyToolboxCategoryLabel, .blocklyTreeLabel")].map(
      (e) => e.textContent,
    );
    expect(names).toEqual(["Motion", "AI", "Control", "Conditions", "Data", "Output"]);
    expect(screen.getByTestId("program-ok")).toBeInTheDocument();
    expect(await axeViolations()).toEqual([]);
  });

  it("refuses a hardware run before a dry run of this version", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    await openEditor(h);
    await user.click(screen.getByRole("button", { name: "Run on the robot" }));
    expect(await screen.findByText("Do a dry run of this version first.")).toBeInTheDocument();
    expect(h.sim.state).toBe("idle");
  });

  it("dry run: waiting (Hibi sleeps), key 1 plays A with the block highlighted, pause, resume, stop", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    const scrolled = vi.spyOn(Blockly.WorkspaceSvg.prototype, "scrollBoundsIntoView");
    await openEditor(h);
    expect(screen.getByText("A hardware run needs a passed dry run of this version.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Dry run" }));
    const panel = screen.getByTestId("run-panel");
    await advance(h.sim, 0.4);
    await waitFor(() => {
      expect(within(panel).getByTestId("program-status")).toHaveTextContent("Waiting · dry run");
    });
    expect(panel.querySelector("[data-hibi]")).toHaveAttribute("data-hibi", "sleep");
    expect(h.sim.state).toBe("idle");
    // The e-stop is armed during a dry run too.
    expect(screen.getByRole("button", { name: "Emergency stop (Space)" })).toBeInTheDocument();
    // The editor is read-only while the program runs.
    expect(screen.getByTestId("blockly-editor")).toHaveAttribute("data-readonly", "true");

    await user.click(within(panel).getByRole("button", { name: /Key 1/ }));
    await advance(h.sim, 0.3);
    await waitFor(() => {
      expect(within(panel).getByTestId("program-now")).toHaveTextContent("play trajectory");
    });
    expect(panel.querySelector("[data-hibi]")).toHaveAttribute("data-hibi", "working");
    const block = document.querySelector('[data-id="play_a"]');
    expect(block?.getAttribute("class")).toMatch(/blockly(Selected|Highlighted)/);
    // The running block is scrolled into view (a narrow screen shows only part of the program).
    expect(scrolled).toHaveBeenCalled();
    expect(
      within(screen.getByTestId("program-log")).getAllByText(/^motion · play trajectory .* · started$/)
        .length,
    ).toBeGreaterThan(0);

    await user.click(within(panel).getByRole("button", { name: "Pause" }));
    await waitFor(() => {
      expect(within(panel).getByTestId("program-status")).toHaveTextContent("Pausing after this motion");
    });
    await advance(h.sim, 12);
    await waitFor(() => {
      expect(within(panel).getByTestId("program-status")).toHaveTextContent("Paused");
    });
    await user.click(within(panel).getByRole("button", { name: "Resume" }));
    await advance(h.sim, 0.3);
    await waitFor(() => {
      expect(within(panel).getByTestId("program-status")).not.toHaveTextContent("Paused");
    });
    await user.click(within(panel).getByRole("button", { name: "Stop program" }));
    await waitFor(() => {
      expect(within(panel).getByTestId("program-status")).toHaveTextContent("Stopped");
    });
    expect(screen.getByTestId("blockly-editor")).toHaveAttribute("data-readonly", "false");
    // A dry run the operator stopped passes (a repeat-forever program never completes): the
    // screen asks the Station and drops the "dry run first" hint without a reload.
    expect(await screen.findByText("This version passed a dry run.")).toBeInTheDocument();
    expect(screen.queryByText("A hardware run needs a passed dry run of this version.")).toBeNull();
    // The badge says "Stopped"; the Station's English reason is not repeated under it.
    expect(within(panel).queryByText("stopped by the operator")).toBeNull();
  });

  it("operator keys work from the keyboard; the dry-run fakes pick the camera branch", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    await openEditor(h);
    await user.click(screen.getByRole("button", { name: "Dry run" }));
    await advance(h.sim, 0.4);
    const panel = screen.getByTestId("run-panel");
    const fakes = await within(panel).findByRole("group", { name: "Camera Cube colour sees" });
    await user.click(within(fakes).getByRole("button", { name: "blue" }));
    await advance(h.sim, 0.4);
    expect(h.sim.programs.run?.state.block_id).toBe("play_b");
    // Condition values are words of the UI language, not JavaScript booleans.
    const conds = within(panel).getByRole("region", { name: "Last condition values" });
    await waitFor(() => {
      expect(within(conds).getAllByText(/^(yes|no)$/).length).toBeGreaterThan(0);
    });
    await advance(h.sim, 12);
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "2" }));
    });
    await advance(h.sim, 0.1);
    expect(h.sim.programs.run?.lines.some((l) => l.kind === "input" && l.message === "key 2")).toBe(true);
  });

  it("after a reload mid-run the panel shows the run and its earlier log lines", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    await openEditor(h);
    await user.click(screen.getByRole("button", { name: "Dry run" }));
    await advance(h.sim, 0.4);
    await waitFor(() => {
      expect(within(screen.getByTestId("run-panel")).getByTestId("program-status")).toHaveTextContent(
        "Waiting",
      );
    });
    const before = within(screen.getByTestId("program-log")).getAllByRole("listitem").length;
    expect(before).toBeGreaterThan(1);
    // A reload: a fresh store and sockets; the WS only sends what happens from now on.
    cleanup();
    const reloaded = { sim: h.sim, runtime: createRuntime(h.sim.socketFactory) };
    await openEditor(reloaded);
    const panel = screen.getByTestId("run-panel");
    await waitFor(() => {
      expect(within(panel).getByTestId("program-status")).toHaveTextContent("Waiting");
    });
    await waitFor(() => {
      expect(within(screen.getByTestId("program-log")).getAllByRole("listitem")).toHaveLength(before);
    });
    expect(within(screen.getByTestId("program-log")).queryByText("No log lines yet.")).toBeNull();
  });

  it("an e-stop aborts the dry run at once and Hibi is sad", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    await openEditor(h);
    await user.click(screen.getByRole("button", { name: "Dry run" }));
    await advance(h.sim, 0.3);
    await user.click(screen.getByRole("button", { name: "Emergency stop (Space)" }));
    await waitFor(() => {
      expect(within(screen.getByTestId("run-panel")).getByTestId("program-status")).toHaveTextContent(
        "E-stopped",
      );
    });
    expect(screen.getByTestId("run-panel").querySelector("[data-hibi]")).toHaveAttribute("data-hibi", "sad");
    expect(h.sim.programs.run).toBeNull();
    // Nothing runs until the e-stop is reset, dry runs included: the hint says so.
    const panel = screen.getByTestId("run-panel");
    expect(within(panel).getByText("The e-stop is on: reset it before running the program.")).toBeVisible();
    expect(within(panel).queryByText("The robot is not idle: dry runs only.")).toBeNull();
    expect(within(panel).getByRole("button", { name: "Dry run" })).toBeDisabled();
  });

  it("saving an edit bumps the version and shows the server's issues", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    await openEditor(h);
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Sort v2");
    expect(screen.getByTestId("unsaved")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => {
      expect(screen.getByText("Version 2")).toBeInTheDocument();
    });
    expect(h.sim.programs.program("sort_cubes").name).toBe("Sort v2");
    expect(screen.queryByTestId("unsaved")).toBeNull();
  });

  it("creates a new program with a single start block", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    await openEditor(h);
    await user.click(screen.getByRole("button", { name: "New program" }));
    await user.type(
      screen.getByLabelText("Name", { selector: "input:not([value='Sort cubes A/B'])" }),
      "Chào robot",
    );
    await user.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => {
      expect(h.sim.programs.programs.some((p) => p.id === "chao_robot")).toBe(true);
    });
    await waitFor(() => {
      expect(document.querySelector('[data-id="start"]')).not.toBeNull();
    });
    expect(document.querySelector('[data-id="play_a"]')).toBeNull();
  });
});
