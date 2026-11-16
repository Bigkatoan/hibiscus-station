import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CameraGrid } from "./components/CameraGrid";
import { EStopButton } from "./components/EStopButton";
import { MotorHealthPanel } from "./components/MotorHealthPanel";
import { advance, renderWithStation, settle, setupStation } from "./test/utils";

describe("MotorHealthPanel (R1)", () => {
  it("colours every motor by its temperature level, for follower and leader", async () => {
    const h = setupStation();
    Object.assign(h.sim.temps.follower, {
      shoulder_pan: 45,
      shoulder_lift: 52,
      elbow_flex: 61,
      wrist_flex: 66,
    });
    renderWithStation(<MotorHealthPanel />, h);
    await settle();
    await advance(h.sim, 1.0);
    const row = (arm: string, m: string) => screen.getByTestId(`motor-${arm}-${m}`);
    await waitFor(() => {
      expect(row("follower", "shoulder_pan")).toHaveAttribute("data-level", "ok");
    });
    expect(row("follower", "shoulder_lift")).toHaveAttribute("data-level", "warn");
    expect(row("follower", "elbow_flex")).toHaveAttribute("data-level", "hot");
    expect(row("follower", "wrist_flex")).toHaveAttribute("data-level", "critical");
    expect(within(row("follower", "elbow_flex")).getByText("61°C")).toBeInTheDocument();
    expect(within(row("follower", "wrist_flex")).getByText("Critical")).toBeInTheDocument();
    expect(row("leader", "gripper")).toHaveAttribute("data-level", "ok");
    expect(within(row("follower", "elbow_flex")).getByText("12.1")).toBeInTheDocument();
  });
});

describe("EStopButton (§4.7, §6.0)", () => {
  it("Space anywhere triggers the e-stop (not inside text fields), Esc does inside them", async () => {
    const h = setupStation();
    h.sim.startSession("teleop", { fps: 30 });
    renderWithStation(
      <div>
        <label>
          note
          <input aria-label="note" />
        </label>
        <EStopButton />
      </div>,
      h,
    );
    await settle();
    expect(await screen.findByRole("button", { name: "Emergency stop (Space)" })).toBeInTheDocument();

    const input = screen.getByLabelText("note");
    input.focus();
    fireEvent.keyDown(input, { key: " ", code: "Space" });
    expect(h.sim.state).toBe("teleop");

    fireEvent.keyDown(input, { key: "Escape", code: "Escape" });
    await waitFor(() => {
      expect(h.sim.state).toBe("estopped");
    });
    expect(h.sim.torque).toBe(true); // first press freezes with torque on
  });

  it("a second Space within 2 s turns torque off; Reset needs a cool robot", async () => {
    const h = setupStation();
    h.sim.startSession("teleop", { fps: 30 });
    renderWithStation(<EStopButton />, h);
    await settle();
    await screen.findByRole("button", { name: "Emergency stop (Space)" });
    const ev = fireEvent.keyDown(document.body, { key: " ", code: "Space" });
    expect(ev).toBe(false); // default prevented: the page never scrolls
    await waitFor(() => {
      expect(h.sim.state).toBe("estopped");
    });
    expect(await screen.findByRole("button", { name: "Relax (torque off)" })).toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: " ", code: "Space" });
    await waitFor(() => {
      expect(h.sim.torque).toBe(false);
    });
    await userEvent.click(await screen.findByRole("button", { name: "I'm clear, reset" }));
    await waitFor(() => {
      expect(h.sim.state).toBe("idle");
    });
  });

  it("is hidden while idle", async () => {
    const h = setupStation();
    renderWithStation(<EStopButton />, h);
    await settle();
    expect(screen.queryByRole("button", { name: "Emergency stop (Space)" })).not.toBeInTheDocument();
  });
});

describe("CameraGrid (R2, §5.4)", () => {
  const drawImage = vi.fn();
  beforeEach(() => {
    drawImage.mockReset();
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn(() => Promise.resolve({ width: 320, height: 240, close: vi.fn() })),
    );
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
      () => ({ drawImage }) as unknown as CanvasRenderingContext2D,
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("decodes binary frames onto a canvas and stamps the policy-input tick", async () => {
    const h = setupStation();
    h.sim.loaded = h.sim.models[0]?.key ?? null;
    h.sim.startSession("run", {
      model: h.sim.loaded,
      task: "t",
      fps: 30,
      episode_time_s: 30,
      num_episodes: 1,
      reset_time_s: 0,
      camera_map: {},
      max_relative_target: 5,
      reset_with_leader: false,
      record: false,
      dataset: null,
    });
    renderWithStation(<CameraGrid />, h);
    await settle();
    await screen.findByTestId("camera-wrist");
    await settle();
    await advance(h.sim, 0.2);
    await waitFor(() => {
      expect(drawImage).toHaveBeenCalled();
    });
    const tile = screen.getByTestId("camera-front");
    await waitFor(() => {
      expect(tile.getAttribute("data-tick")).not.toBe("");
    });
    expect(within(tile).getByText("policy input · 640×480 → 320×240")).toBeInTheDocument();
    expect(within(tile).getByText(`frame tick ${tile.getAttribute("data-tick") ?? ""}`)).toBeInTheDocument();
    // The subscription covers every configured camera.
    const video = [...(h.sim as unknown as { video: Map<unknown, { cameras: string[] }> }).video.values()];
    expect(video[0]?.cameras).toEqual(["front", "wrist"]);
  });

  it("shows no frame tick outside a session (the Station sends tick -1 there)", async () => {
    const h = setupStation();
    Object.defineProperty(h.sim, "tick", { get: () => -1, set: () => undefined, configurable: true });
    renderWithStation(<CameraGrid />, h);
    await settle();
    await screen.findByTestId("camera-front");
    await settle();
    await advance(h.sim, 0.2);
    const tile = screen.getByTestId("camera-front");
    await waitFor(() => {
      expect(tile).toHaveAttribute("data-tick", "-1");
    });
    expect(within(tile).queryByText(/frame tick/)).toBeNull();
  });

  it("shows a striped stale overlay on camera_error", async () => {
    const h = setupStation();
    // Point a profile camera at a name the mock station does not have.
    h.sim.profiles = h.sim.profiles.map((p) => ({ ...p, cameras: { ...p.cameras } }));
    renderWithStation(<CameraGrid names={["ghost"]} />, h);
    await settle();
    await settle();
    await act(async () => {
      h.sim.step(0.1);
      await new Promise((r) => setTimeout(r, 0));
    });
    const tile = screen.getByTestId("camera-ghost");
    await waitFor(() => {
      expect(tile).toHaveAttribute("data-stale", "true");
    });
    expect(within(tile).getByText("Camera unavailable")).toBeInTheDocument();
  });
});
