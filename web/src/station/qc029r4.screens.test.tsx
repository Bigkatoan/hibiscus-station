/**
 * QC 0.2.9 round 4 (docs/qc/QC-0.2.9-r4.md), QD-23: the red thermal-stop banner stayed on the open
 * page after the motor cooled and the e-stop was reset, and the vi countdown said "Khoảng 0 giây
 * nữa". The class check: after a scripted sequence the UI store says what a fresh GET /status says.
 */
import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { i18n } from "@/lib/i18n";
import type { AlertMsg } from "./api/types";
import { StationStore } from "./ws/store";
import { advance, renderStation, settle, setupStation } from "./test/utils";

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
    const { type: _type, ...asStatus } = critical;
    store.handle({ type: "hello", v: 1, status: { ...h.sim.status(), alerts: [asStatus] } });
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
