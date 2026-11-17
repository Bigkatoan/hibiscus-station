/**
 * QC 0.2.9 round 3 (docs/qc/QC-0.2.9-r3.md) against the mock Station: a record session that kept
 * no episode never asks for the dataset it removed (QD-18), and the stop banners never show the
 * Station's English detail (QD-19).
 */
import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { i18n } from "@/lib/i18n";
import { server } from "@/test/server";
import { advance, renderStation, settle, setupStation } from "./test/utils";

afterEach(async () => {
  await i18n.changeLanguage("en");
});

/** Every GET the page sends to `/api/v1/datasets/<name>` (the dataset itself, not the list). */
function datasetRequests(name: string): { at: () => number; urls: string[] } {
  const urls: string[] = [];
  const path = `/api/v1/datasets/${encodeURIComponent(name)}`;
  server.events.on("request:start", ({ request }) => {
    if (new URL(request.url).pathname === path) urls.push(request.url);
  });
  return { at: () => urls.length, urls };
}

describe("Record: a session that kept no episode asks nothing of its removed dataset (QD-18)", () => {
  const REC = { dataset: "qr3_t404", task: "Pick", reset_time_s: 0, countdown_s: 0.1 };

  it("an e-stop in episode 1 sends no request for the dataset", async () => {
    const h = setupStation({ paired: true });
    const reqs = datasetRequests(REC.dataset);
    h.sim.startSession("record", { ...REC, num_episodes: 1, episode_time_s: 30 });
    renderStation("/record", h);
    await settle();
    await advance(h.sim, 3);
    h.sim.estop("user");
    await screen.findByTestId("record-none");
    await settle();
    await advance(h.sim, 0.5);
    expect(h.sim.datasets.some((d) => d.name === REC.dataset)).toBe(false);
    expect(reqs.urls).toEqual([]);
    server.events.removeAllListeners();
  });

  it("a Stop in the countdown sends no request for the dataset", async () => {
    const h = setupStation({ paired: true });
    const reqs = datasetRequests(REC.dataset);
    h.sim.startSession("record", { ...REC, num_episodes: 1, episode_time_s: 30, countdown_s: 5 });
    renderStation("/record", h);
    await settle();
    await advance(h.sim, 1);
    h.sim.controlAction("stop");
    await screen.findByTestId("record-none");
    await settle();
    expect(reqs.urls).toEqual([]);
    server.events.removeAllListeners();
  });

  it("a kept episode still refreshes the saved-episode strip", async () => {
    const h = setupStation({ paired: true });
    const reqs = datasetRequests(REC.dataset);
    h.sim.startSession("record", { ...REC, num_episodes: 2, episode_time_s: 2 });
    renderStation("/record", h);
    await settle();
    await advance(h.sim, 3.2);
    await settle();
    expect(reqs.at()).toBeGreaterThan(0); // episode 1 saved: the strip asks for it
    h.sim.estop("user");
    await screen.findByTestId("record-done");
    server.events.removeAllListeners();
  });
});

/** Put the mock Station in a state with the Station's own English detail line. */
function setState(h: ReturnType<typeof setupStation>, state: string, reason: string, detail: string): void {
  (h.sim as unknown as { setState: (s: string, x: { reason: string; detail: string }) => void }).setState(
    state,
    { reason, detail },
  );
}

const HEARTBEAT = "no heartbeat from the UI for 1.0 s";

describe("Stop banners and locked steps never show the Station's English detail (QD-19)", () => {
  it("vi: the dead-man stop is explained in Vietnamese only, on the banner and the locked step", async () => {
    const h = setupStation({ paired: true });
    await i18n.changeLanguage("vi");
    h.sim.estop("ui_lost", HEARTBEAT);
    renderStation("/teleop", h);
    const banner = await screen.findByTestId("state-banner");
    expect(banner).toHaveTextContent("Robot đã dừng: mất kết nối giao diện.");
    expect(banner).toHaveTextContent("Trang không gửi tín hiệu nào trong 1 giây");
    const gate = await screen.findByTestId("lock-gate");
    expect(gate).toHaveTextContent("Trang không gửi tín hiệu nào trong 1 giây");
    expect(screen.getByTestId("lock-why-teleop")).toHaveTextContent("Trang không gửi tín hiệu nào");
    expect(document.body).not.toHaveTextContent(/heartbeat/i);
  });

  it("en: the dead-man stop reads in words, not as the server line", async () => {
    const h = setupStation({ paired: true });
    h.sim.estop("ui_lost", HEARTBEAT);
    renderStation("/teleop", h);
    const banner = await screen.findByTestId("state-banner");
    expect(banner).toHaveTextContent("This page sent no sign of life for 1 s");
    expect(document.body).not.toHaveTextContent(/heartbeat/i);
  });

  it("vi: a motor stop names the arm and the motor in words", async () => {
    const h = setupStation({ paired: true });
    await i18n.changeLanguage("vi");
    setState(h, "estopped", "electrical", "follower elbow_flex status voltage,overload");
    renderStation("/teleop", h);
    const gate = await screen.findByTestId("lock-gate");
    expect(gate).toHaveTextContent("Tay follower elbow_flex báo: điện áp, quá tải.");
    expect(gate).not.toHaveTextContent("status voltage");
  });

  it("an unknown detail stays behind a closed 'Chi tiết kỹ thuật'", async () => {
    const h = setupStation({ paired: true });
    await i18n.changeLanguage("vi");
    setState(h, "error", "bus_lost", "follower: motor ID 3 timed out");
    renderStation("/teleop", h);
    const banner = await screen.findByTestId("state-banner");
    const tech = within(banner).getByTestId("tech-details");
    expect(tech.tagName).toBe("DETAILS");
    expect(tech).not.toHaveAttribute("open");
    expect(within(tech).getByText("Chi tiết kỹ thuật")).toBeInTheDocument();
    expect(within(tech).getByText("follower: motor ID 3 timed out")).not.toBeVisible();
    // the wizard rail never shows the server line
    expect(screen.getByRole("navigation", { name: "Các bước Station" })).not.toHaveTextContent("timed out");
  });
});
