/**
 * Field report 0.2.9 → 0.2.10 (Windows, SO-101): "cannot see the video and the recorded episodes".
 * The dataset page while an episode is being saved, after the save, and for a dataset the Station
 * left unfinalized (closed mid-session): every episode shows, one by one, and the page never goes
 * blank.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { i18n } from "@/lib/i18n";
import { server } from "@/test/server";
import type { LocalDatasetDetail } from "./api/types";
import * as fx from "./mock/fixtures";
import { renderStation, settle, setupStation } from "./test/utils";

afterEach(async () => {
  await i18n.changeLanguage("en");
});

type Row = LocalDatasetDetail["episode_list"][number];

/** A dataset of 3 episodes: #1 saved, #2 `second`, #3 `third`. */
function withStates(second: string, third: string): LocalDatasetDetail {
  const d = fx.dataset("cube_live", 3);
  const states = ["saved", second, third];
  d.finalized = false;
  d.episode_list = d.episode_list.map((e, i) => {
    const row = { ...e, state: states[i] } as Row;
    if (states[i] !== "saved") Object.assign(row, { telemetry_lines: 0, max_temp_c: {} });
    if (states[i] === "unreadable") Object.assign(row, { frames: null, length_s: null, tasks: null });
    return row;
  });
  return d;
}

/** The episode row of #n (1-based, as on screen). */
async function row(n: number): Promise<HTMLElement> {
  const li = (await screen.findByRole("button", { name: `#${String(n)}` })).closest("li");
  if (!li) throw new Error(`no row #${String(n)}`);
  return li;
}

function telemetryRequests(): string[] {
  const urls: string[] = [];
  server.events.on("request:start", ({ request }) => {
    if (request.url.includes("/telemetry")) urls.push(new URL(request.url).pathname);
  });
  return urls;
}

describe("Dataset detail while episodes are saved (field report 0.2.10)", () => {
  it("shows the episode being saved as Saving…, the others as usual", async () => {
    const h = setupStation({ datasets: [withStates("saved", "saving")] });
    const user = userEvent.setup();
    const tel = telemetryRequests();
    renderStation("/datasets/cube_live", h);
    await settle();
    const saving = await row(3);
    expect(saving).toHaveTextContent("Saving…");
    expect(within(saving).getByRole("button", { name: "Replay" })).toBeDisabled();
    expect(within(saving).getByRole("button", { name: "#3" })).toBeDisabled();
    for (const n of [1, 2]) {
      expect(await row(n)).not.toHaveTextContent("Saving…");
      expect(await row(n)).toHaveTextContent("30.0 s");
    }
    await user.click(screen.getByRole("button", { name: "#2" }));
    expect(await screen.findByTestId("episode-telemetry")).toBeInTheDocument();
    expect(tel).toEqual(["/api/v1/datasets/cube_live/episodes/1/telemetry"]);
    server.events.removeAllListeners();
  });

  it("refreshes by itself: once the save is done the episode shows like the others", async () => {
    const d = withStates("saved", "saving");
    const h = setupStation({ datasets: [d] });
    renderStation("/datasets/cube_live", h);
    await settle();
    expect(await row(3)).toHaveTextContent("Saving…");
    h.sim.datasets = [{ ...fx.dataset("cube_live", 3), finalized: true }];
    await waitFor(
      async () => {
        expect(await row(3)).not.toHaveTextContent("Saving…");
      },
      { timeout: 4000 },
    );
    expect(await row(3)).toHaveTextContent("30.0 s");
    expect(within(await row(3)).getByRole("button", { name: "Replay" })).toBeEnabled();
  });

  it("an episode the Station never finished writing says so, in English and Vietnamese", async () => {
    const h = setupStation({ datasets: [withStates("unreadable", "unreadable")] });
    renderStation("/datasets/cube_live", h);
    await settle();
    const second = await row(2);
    expect(second).toHaveTextContent(
      "Cannot be read: the Station closed before this episode was fully saved. The other episodes are fine.",
    );
    expect(within(second).getByRole("button", { name: "Replay" })).toBeDisabled();
    expect(await row(1)).toHaveTextContent("30.0 s");
    await i18n.changeLanguage("vi");
    await waitFor(async () => {
      expect(await row(2)).toHaveTextContent(
        "Không đọc được: Station đã đóng trước khi lưu xong tập này. Các tập khác vẫn dùng được.",
      );
    });
    expect(await row(3)).toHaveTextContent("Không đọc được");
  });

  it("a page that cannot render keeps the Station shell and says so (no blank page)", async () => {
    const h = setupStation();
    server.use(
      http.get(`${window.location.origin}/api/v1/datasets/broken`, () =>
        HttpResponse.json({ ...fx.dataset("broken", 1), episode_list: null }),
      ),
    );
    renderStation("/datasets/broken", h);
    await settle();
    await waitFor(() => {
      expect(screen.queryByText(/Unexpected Application Error/)).not.toBeInTheDocument();
      expect(screen.getByTestId("page-error")).toHaveTextContent("This page could not be shown.");
    });
    expect(screen.getAllByRole("link", { name: "Datasets" }).length).toBeGreaterThan(0); // the nav is still there
  });
});

describe("Record: the saved-episode strip (field report 0.2.10)", () => {
  it("lists the saved episodes during the session, the one being saved as Saving…", async () => {
    const h = setupStation({ datasets: [withStates("saved", "saving")] });
    h.sim.startSession("record", {
      dataset: "cube_live",
      mode: "append",
      task: "Pick",
      num_episodes: 5,
      episode_time_s: 30,
      reset_time_s: 0,
      countdown_s: 0.1,
    });
    // the sim saved nothing yet in this session; the dataset already holds 3 episodes
    const ep = h.sim.session?.s.episode;
    if (ep) ep.saved = 3;
    renderStation("/record", h);
    await settle();
    const strip = await screen.findByRole("region", { name: "Saved episodes" });
    expect(within(strip).getAllByRole("listitem")).toHaveLength(3);
    expect(within(strip).getAllByRole("listitem")[2]).toHaveTextContent("Saving…");
  });
});

describe("Record: appending to a dataset the Station left unfinalized (field report 0.2.10)", () => {
  it("says so in words, keeps the data, and offers a new dataset with the same task", async () => {
    const crashed = { ...fx.dataset("cube_crash", 3), finalized: false, task: "Pick the cube" };
    const h = setupStation({ datasets: [crashed] });
    const user = userEvent.setup();
    const bodies: Record<string, unknown>[] = [];
    server.use(
      http.post(`${window.location.origin}/api/v1/sessions/record`, async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        bodies.push(body);
        if (body.mode === "append")
          return HttpResponse.json(
            {
              type: "https://hibiscus.dev/problems/station/dataset_not_finalized",
              title: "Dataset is not finalized",
              status: 409,
              code: "dataset_not_finalized",
              detail: "dataset cube_crash was never finalized",
              params: { dataset: "cube_crash", reasons: ["meta/episodes missing"], mode: "append" },
            },
            { status: 409 },
          );
        return HttpResponse.json(h.sim.startSession("record", body));
      }),
    );
    renderStation("/record", h);
    await settle();
    await user.selectOptions(await screen.findByLabelText(/^Dataset$/), "append");
    await user.selectOptions(screen.getByLabelText(/^Dataset name/), "cube_crash");
    await user.click(screen.getByRole("button", { name: "Start recording" }));
    const card = await screen.findByTestId("record-unfinalized");
    expect(card).toHaveTextContent(
      "cube_crash was not finished: the Station closed while it was being recorded, so no episode can be added to it. Its files are kept as they are. Record into a new dataset instead.",
    );
    expect(screen.queryByText(/Internal error/)).not.toBeInTheDocument();
    await i18n.changeLanguage("vi");
    await waitFor(() => {
      expect(screen.getByTestId("record-unfinalized")).toHaveTextContent(
        "Bộ dữ liệu cube_crash chưa hoàn tất: Station đã đóng khi đang ghi",
      );
    });
    await user.click(screen.getByRole("button", { name: "Ghi vào bộ dữ liệu mới" }));
    expect(screen.queryByTestId("record-unfinalized")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/^Tên bộ dữ liệu|^Dataset name/)).toHaveValue("cube_crash_2");
    expect(h.sim.datasets.find((d) => d.name === "cube_crash")?.episodes).toBe(3);
    expect(bodies.map((b) => b.mode)).toEqual(["append"]);
  });
});
