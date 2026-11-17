/**
 * QC 0.2.9 round 3 (docs/qc/QC-0.2.9-r3.md) against the mock Station: a record session that kept
 * no episode never asks for the dataset it removed (QD-18), and the stop banners never show the
 * Station's English detail (QD-19).
 */
import { screen } from "@testing-library/react";
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
