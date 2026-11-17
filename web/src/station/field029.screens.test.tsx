/**
 * Field report 0.2.8 → 0.2.9 against the mock Station: leader telemetry that reads as connected
 * ("not measured" with its reason, never a bare dash), the record Stop that ends the episode at
 * once, CR-1 (Stop holds, then "Return Home" / "Relax") and CR-2 ("Home").
 */
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
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
    expect(done).toHaveTextContent("1 episodes saved");
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
