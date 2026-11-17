/**
 * QC 0.2.9 round 4 (docs/qc/QC-0.2.9-r4.md), QD-23: the red thermal-stop banner stayed on the open
 * page after the motor cooled and the e-stop was reset, and the vi countdown said "Khoảng 0 giây
 * nữa". The class check: after a scripted sequence the UI store says what a fresh GET /status says.
 */
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { i18n } from "@/lib/i18n";
import { omit, type AlertMsg, type Status } from "./api/types";
import { StationStore } from "./ws/store";
import { advance, renderStation, settle, setupStation, type StationHarness } from "./test/utils";

afterEach(async () => {
  await i18n.changeLanguage("en");
});

const critical: AlertMsg = {
  type: "alert",
  id: "temperature:motor.critical.stopped",
  t: 1,
  level: "critical",
  kind: "temperature",
  arm: "follower",
  motor: "elbow_flex",
  camera: null,
  value: 66,
  message_key: "motor.critical.stopped",
  params: {},
  active: true,
};

/** What the pages show from the store, next to the same from a fresh GET /status. */
function uiView(status: Status | null, alerts: readonly { id: string; level: string }[]) {
  return {
    state: status?.state,
    reason: status?.reason ?? null,
    connected: status?.robot?.connected ?? null,
    torque: status?.robot?.follower_torque ?? null,
    session: Boolean(status?.session),
    interrupted: status?.interrupted ?? null,
    alerts: alerts.map((a) => `${a.id}:${a.level}`).sort(),
  };
}

function expectStoreMatchesStatus(h: StationHarness, step: string): void {
  const snap = h.runtime.store.getSnapshot();
  const fresh = h.sim.status();
  expect({ step, ...uiView(snap.status, snap.alerts) }).toEqual({ step, ...uiView(fresh, fresh.alerts) });
}

describe("the store follows the Station's alerts (QD-23)", () => {
  it("a hello (reload or reconnect) replaces the alerts with the Station's own", () => {
    const h = setupStation();
    const store = new StationStore();
    store.handle(critical);
    expect(store.getSnapshot().alerts).toHaveLength(1);
    // The reset happened while the socket was down: the next hello no longer has the alert.
    store.handle({ type: "hello", v: 1, status: { ...h.sim.status(), alerts: [] } });
    expect(store.getSnapshot().alerts).toEqual([]);
    // A page opened during a thermal stop shows its alert at once.
    store.handle({ type: "hello", v: 1, status: { ...h.sim.status(), alerts: [omit(critical, "type")] } });
    expect(store.getSnapshot().alerts.map((a) => a.id)).toEqual([critical.id]);
    expect(store.getSnapshot().alerts[0]?.type).toBe("alert");
  });
});

describe("the cooling countdown never reads 0 s (QD-23)", () => {
  for (const [lng, zero] of [
    ["vi", /\b0 giây/],
    ["en", /about 0 s/],
  ] as const) {
    it(`${lng}: a cooled motor shows no countdown on the critical banner`, async () => {
      await i18n.changeLanguage(lng);
      const h = setupStation({ paired: true });
      renderStation("/", h);
      await settle();
      h.sim.temps.follower.elbow_flex = 66;
      await advance(h.sim, 1.1);
      await screen.findByTestId("critical-banner");
      h.sim.temps.follower.elbow_flex = 40;
      await advance(h.sim, 12);
      expect(screen.getByTestId("critical-banner")).not.toHaveTextContent(zero);
    });
  }
});

describe("thermal stop → cool → reset on one open page (QD-23)", () => {
  it("the banner goes at once, the vi countdown never says 0 s, and the store equals GET /status", async () => {
    await i18n.changeLanguage("vi");
    const h = setupStation({ paired: true });
    renderStation("/", h);
    await settle();
    expectStoreMatchesStatus(h, "connected");
    h.sim.temps.follower.elbow_flex = 66;
    await advance(h.sim, 1.1);
    expect(h.sim.state).toBe("estopped");
    const banner = await screen.findByTestId("critical-banner");
    expect(banner).toHaveTextContent("elbow_flex 66 °C");
    expectStoreMatchesStatus(h, "thermal stop");
    // The motor cools below "hot": the estimate reaches 0 and must not be read out as "0 s".
    h.sim.temps.follower.elbow_flex = 40;
    await advance(h.sim, 12);
    expect(screen.getByTestId("critical-banner")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/Khoảng 0 giây/);
    expect(document.body).not.toHaveTextContent(/\b0 giây nữa/);
    expectStoreMatchesStatus(h, "cooled");
    await userEvent.click(screen.getAllByRole("button", { name: "Đã an toàn, đặt lại" })[0]!);
    await waitFor(() => {
      expect(h.sim.state).toBe("idle");
    });
    expect(screen.queryByTestId("critical-banner")).toBeNull();
    expectStoreMatchesStatus(h, "reset");
    // A warm motor, then disconnect: every alert leaves the page with the robot.
    h.sim.temps.follower.gripper = 52;
    await advance(h.sim, 2);
    expect(h.runtime.store.getSnapshot().alerts.length).toBeGreaterThan(0);
    expectStoreMatchesStatus(h, "warm gripper");
    act(() => {
      h.sim.disconnect();
    });
    expectStoreMatchesStatus(h, "disconnect");
    expect(h.runtime.store.getSnapshot().alerts).toEqual([]);
  });
});

describe("device lost on an open page (QD-23 class)", () => {
  it("the gone bus's motor alerts leave the page with it", async () => {
    const h = setupStation({ paired: true });
    renderStation("/", h);
    await settle();
    h.sim.temps.follower.gripper = 52;
    await advance(h.sim, 2);
    expect(h.runtime.store.getSnapshot().alerts.some((a) => a.motor === "gripper")).toBe(true);
    act(() => {
      h.sim.loseDevice("follower", false);
    });
    expectStoreMatchesStatus(h, "device lost");
    expect(h.runtime.store.getSnapshot().alerts.some((a) => a.motor === "gripper")).toBe(false);
  });
});
