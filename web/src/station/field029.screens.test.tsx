/**
 * Field report 0.2.8 → 0.2.9 against the mock Station: leader telemetry that reads as connected
 * ("not measured" with its reason, never a bare dash), the record Stop that ends the episode at
 * once, CR-1 (Stop holds, then "Return Home" / "Relax") and CR-2 ("Home").
 */
import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MotorHealthPanel } from "./components/MotorHealthPanel";
import { advance, renderWithStation, settle, setupStation } from "./test/utils";

beforeEach(() => {
  vi.stubGlobal(
    "createImageBitmap",
    vi.fn(() => Promise.resolve({ width: 320, height: 240, close: vi.fn() })),
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
