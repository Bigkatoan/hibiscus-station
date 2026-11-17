/**
 * QC 0.2.9 round 4 (docs/qc/QC-0.2.9-r4.md), QD-23: the red thermal-stop banner stayed on the open
 * page after the motor cooled and the e-stop was reset, and the vi countdown said "Khoảng 0 giây
 * nữa". The class check: after a scripted sequence the UI store says what a fresh GET /status says.
 */
import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { i18n } from "@/lib/i18n";
import { advance, renderStation, settle, setupStation } from "./test/utils";

afterEach(async () => {
  await i18n.changeLanguage("en");
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
