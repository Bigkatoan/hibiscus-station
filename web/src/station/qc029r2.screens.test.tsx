/**
 * QC 0.2.9 round 2 (docs/qc/QC-0.2.9-r2.md) against the mock Station: no raw values on the
 * Cameras and Sessions pages, the end card of a record session that kept no episode, a finished
 * program run whose time stays put, and the wording defects.
 */
import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { i18n } from "@/lib/i18n";
import { server } from "@/test/server";
import type { DiscoveredCamera } from "./api/types";
import { renderStation, settle, setupStation } from "./test/utils";

afterEach(async () => {
  await i18n.changeLanguage("en");
});

const HELD_MOCK: DiscoveredCamera = {
  type: "held",
  id: "mock:front",
  stable_path: null,
  name: "front",
  default: null,
  in_use_by: "front",
};

describe("Cameras: discovered devices (QD-15)", () => {
  it("shows a held demo camera as in use, never 'held' or 'None'", async () => {
    const h = setupStation();
    server.use(
      http.get(`${window.location.origin}/api/v1/cameras/discover`, () =>
        HttpResponse.json({
          cameras: [HELD_MOCK, { ...HELD_MOCK, id: "None", name: "wrist", in_use_by: "wrist" }],
        }),
      ),
    );
    renderStation("/cameras", h);
    const row = await screen.findByTestId("discovered-mock:front");
    expect(row).toHaveTextContent("used by front");
    for (const r of [row, screen.getByTestId("discovered-None")]) {
      expect(r).not.toHaveTextContent(/\bheld\b/);
      expect(r).not.toHaveTextContent("None");
      expect(r).not.toHaveTextContent("mock:");
    }
  });

  it("names the device type in words, in vi too", async () => {
    const h = setupStation();
    await i18n.changeLanguage("vi");
    renderStation("/cameras", h);
    const row = await screen.findByTestId("discovered-/dev/video4");
    expect(row).toHaveTextContent("camera USB");
    expect(row).toHaveTextContent("/dev/v4l/by-id/usb-Generic_USB2.0_Camera-video-index0");
    expect(row).not.toHaveTextContent("opencv");
  });
});

describe("Sessions page (QD-14)", () => {
  it("names every kind and outcome in words, in vi", async () => {
    const h = setupStation();
    const base = h.sim.sessionsHist[0]!;
    h.sim.sessionsHist = (["program", "rest", "traj_play", "traj_record"] as const).map((kind, i) => ({
      ...base,
      id: `s_${i}`,
      kind,
      outcome: "stopped",
      dataset: null,
    }));
    await i18n.changeLanguage("vi");
    renderStation("/sessions", h);
    await settle();
    const table = await screen.findByRole("table");
    await waitFor(() => {
      expect(within(table).getByText("Chương trình")).toBeInTheDocument();
    });
    for (const word of ["Về Home", "Phát quỹ đạo", "Ghi quỹ đạo"])
      expect(within(table).getByText(word)).toBeInTheDocument();
    expect(table).not.toHaveTextContent("session.kind_");
    expect(within(table).queryByText("stopped")).toBeNull();
    expect(within(table).getAllByText("đã dừng")).toHaveLength(4);
  });
});
