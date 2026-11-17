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
import { advance, renderStation, settle, setupStation } from "./test/utils";

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

describe("Record: a session that kept no episode (QD-12)", () => {
  const REC = { dataset: "qr_redstop", task: "Pick", reset_time_s: 0, countdown_s: 0.1 };

  it("an e-stop in episode 1 says the episode was not kept and offers no Upload", async () => {
    const h = setupStation({ paired: true });
    h.sim.startSession("record", { ...REC, num_episodes: 1, episode_time_s: 30 });
    renderStation("/record", h);
    await settle();
    await advance(h.sim, 3);
    h.sim.estop("user");
    const card = await screen.findByTestId("record-none");
    expect(card).toHaveTextContent("No episode was saved.");
    expect(card).toHaveTextContent("Episode 1 was stopped (e-stop pressed), so it was not kept.");
    expect(card).toHaveTextContent("Nothing was written: the dataset qr_redstop was not created.");
    expect(card).not.toHaveTextContent(/0 episodes/);
    expect(within(card).queryByRole("link", { name: "Upload" })).toBeNull();
    expect(screen.queryByTestId("record-done")).toBeNull();
    expect(h.sim.datasets.some((d) => d.name === "qr_redstop")).toBe(false);
  });

  it("a Stop in the countdown says nothing was recorded, in vi too", async () => {
    const h = setupStation({ paired: true });
    await i18n.changeLanguage("vi");
    h.sim.startSession("record", { ...REC, num_episodes: 1, episode_time_s: 30, countdown_s: 5 });
    renderStation("/record", h);
    await settle();
    await advance(h.sim, 1);
    h.sim.controlAction("stop");
    const card = await screen.findByTestId("record-none");
    expect(card).toHaveTextContent("Chưa lưu tập nào.");
    expect(card).toHaveTextContent("Bạn đã dừng trước khi ghi tập đầu tiên.");
    expect(card).toHaveTextContent("bộ dữ liệu qr_redstop chưa được tạo");
    expect(within(card).queryByRole("link")).toBeNull();
    expect(within(card).getByRole("button", { name: "Ghi lại" })).toBeEnabled();
  });

  it("an e-stop in episode 2 keeps episode 1 and says episode 2 was not kept", async () => {
    const h = setupStation({ paired: true });
    h.sim.startSession("record", { ...REC, num_episodes: 2, episode_time_s: 2 });
    renderStation("/record", h);
    await settle();
    await advance(h.sim, 3.2);
    h.sim.estop("user");
    const done = await screen.findByTestId("record-done");
    expect(done).toHaveTextContent("1 episode saved in dataset qr_redstop");
    expect(screen.getByTestId("record-dropped")).toHaveTextContent(
      "Episode 2 was stopped (e-stop pressed), so it was not kept.",
    );
    expect(within(done).getByRole("link", { name: "Upload" })).toBeInTheDocument();
  });
});

describe("Dataset page for a dataset that is gone (QD-12)", () => {
  it("says so plainly: no stale numbers, no Delete, no Upload, no server text", async () => {
    const h = setupStation({ paired: true });
    renderStation("/datasets/qr_redstop5?upload=1", h);
    const card = await screen.findByTestId("dataset-missing");
    expect(card).toHaveTextContent("There is no dataset qr_redstop5 on this computer.");
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
    expect(screen.queryByText("no dataset qr_redstop5")).toBeNull(); // the raw server detail
    expect(screen.queryByText("Not found.")).toBeNull();
    expect(screen.queryByText(/0 episodes/)).toBeNull();
  });
});
