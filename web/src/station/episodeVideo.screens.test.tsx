/**
 * F-72 / CR-1: the camera video of each recorded episode, in the dataset detail, on one clock
 * with the telemetry chart. jsdom plays no media: these tests drive the <video> events by hand.
 */
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { server } from "@/test/server";
import { stationBase } from "./api/client";
import type { EpisodeCamera } from "./api/types";
import { formatOrder, videoUrl } from "./components/EpisodeViewer";
import { i18n } from "@/lib/i18n";
import { episodeReviewable, episodeSeconds } from "./pages/DatasetsPage";
import { renderStation, settle, setupStation } from "./test/utils";

let play: MockInstance<() => Promise<void>>;

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    () => ({ drawImage: vi.fn() }) as unknown as CanvasRenderingContext2D,
  );
  play = vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(() => Promise.resolve());
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
});

const cam = (over: Partial<EpisodeCamera> = {}): EpisodeCamera => ({
  camera: "front",
  codec: "av1",
  mime: 'video/mp4; codecs="av01.0.05M.08"',
  duration_s: 30,
  error: null,
  formats: ["source", "vp9", "h264"],
  ...over,
});

describe("format choice (ADR-14)", () => {
  it("plays the recorded AV1 where the browser decodes it (Chrome, Firefox)", () => {
    expect(formatOrder(cam(), () => "probably")).toEqual(["source", "h264", "vp9"]);
  });

  it("stock Windows Edge (no AV1 Video Extension) gets H.264, then VP9", () => {
    const edge = (m: string) => (m.includes("av01") ? "" : "maybe");
    expect(formatOrder(cam(), edge)).toEqual(["h264", "vp9", "source"]);
  });

  it("Windows N (no Media Foundation: no H.264) gets VP9 first", () => {
    const n = (m: string) => (m.includes("vp9") ? "probably" : "");
    expect(formatOrder(cam(), n)).toEqual(["vp9", "source", "h264"]);
  });

  it("a browser that says no to all still tries every format", () => {
    expect(formatOrder(cam(), () => "")).toEqual(["source", "h264", "vp9"]);
    expect(formatOrder(cam({ formats: [] }), () => "probably")).toEqual([]);
  });

  it("builds an escaped URL under /api/v1", () => {
    expect(videoUrl("pick n", 2, "wrist", "vp9")).toBe(
      `${stationBase()}/datasets/pick%20n/episodes/2/videos/wrist?format=vp9`,
    );
  });

  it("opens the viewer only for a written episode (hotfix 0.2.10 EpisodeSummary.state)", () => {
    expect(episodeReviewable({ index: 0 })).toBe(true); // a Station before the hotfix
    expect(episodeReviewable({ index: 0, state: "saved" })).toBe(true);
    expect(episodeReviewable({ index: 0, state: "saving" })).toBe(false);
    expect(episodeReviewable({ index: 0, state: "unreadable" })).toBe(false);
    expect(episodeReviewable(undefined)).toBe(false);
  });

  it("puts the chart on the video's clock: frame index / fps", () => {
    expect(episodeSeconds([100, 100.5, 101], [0, 15, 30], 30)).toEqual([0, 0.5, 1]);
    // telemetry from before F-72: seconds since the episode's first line
    expect(episodeSeconds([100, 100.5], [], 30)).toEqual([0, 0.5]);
  });
});

function videoOf(name: string): HTMLVideoElement {
  const v = screen.getByTestId(`episode-video-${name}`).querySelector("video");
  if (!v) throw new Error(`no <video> for ${name}`);
  return v;
}

async function openEpisode(n = 1) {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: `#${String(n)}` }));
  await screen.findByTestId("episode-player");
  return user;
}

describe("Dataset detail: episode video (F-72)", () => {
  it("clicking an episode shows every camera with play, scrubber and time", async () => {
    const h = setupStation();
    renderStation("/datasets/picknplace_red", h);
    await settle();
    expect(await screen.findByText("Pick an episode.")).toBeInTheDocument();
    await openEpisode(2);
    expect(screen.getByText("Episode 2: cameras")).toBeInTheDocument();
    for (const c of ["wrist", "front"]) {
      const tile = screen.getByTestId(`episode-video-${c}`);
      expect(tile).toHaveAttribute("data-state", "loading");
      expect(within(tile).getByText("Preparing the video…")).toBeInTheDocument();
      // jsdom's canPlayType says "" to everything: the recorded cut is tried first
      expect(videoOf(c).getAttribute("src")).toBe(videoUrl("picknplace_red", 1, c, "source"));
      expect(videoOf(c).muted).toBe(true);
    }
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Time in the episode" })).toHaveAttribute("max", "30");
    expect(screen.getByTestId("episode-time")).toHaveTextContent("0.0 / 30.0 s");
    expect(screen.getByTestId("episode-telemetry")).toBeInTheDocument();
  });

  it("play / pause drive every camera; the scrubber seeks them all", async () => {
    const h = setupStation();
    renderStation("/datasets/picknplace_red", h);
    await settle();
    const user = await openEpisode(1);
    for (const c of ["wrist", "front"]) fireEvent.loadedData(videoOf(c));
    expect(screen.getByTestId("episode-video-front")).toHaveAttribute("data-state", "ready");
    expect(screen.getByTestId("episode-video-front")).toHaveTextContent("AV1, as recorded");
    play.mockClear();
    await user.click(screen.getByRole("button", { name: "Play" }));
    expect(play).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Pause" }));
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("slider"), { target: { value: "12.5" } });
    expect(videoOf("wrist").currentTime).toBeCloseTo(12.5);
    expect(videoOf("front").currentTime).toBeCloseTo(12.5);
    expect(screen.getByTestId("episode-time")).toHaveTextContent("12.5 / 30.0 s");
  });

  it("a format the browser cannot play falls through to H.264, then VP9", async () => {
    const h = setupStation();
    server.use(
      http.get(
        `${stationBase()}/datasets/:name/episodes/:i/videos/:cam`,
        () => new HttpResponse(null, { status: 200 }),
      ),
    );
    renderStation("/datasets/picknplace_red", h);
    await settle();
    await openEpisode(1);
    fireEvent.error(videoOf("front"));
    await waitFor(() => {
      expect(videoOf("front").getAttribute("src")).toBe(videoUrl("picknplace_red", 0, "front", "h264"));
    });
    fireEvent.error(videoOf("front"));
    await waitFor(() => {
      expect(videoOf("front").getAttribute("src")).toBe(videoUrl("picknplace_red", 0, "front", "vp9"));
    });
    fireEvent.error(videoOf("front"));
    const tile = screen.getByTestId("episode-video-front");
    await waitFor(() => {
      expect(tile).toHaveAttribute("data-state", "error");
    });
    expect(tile).toHaveTextContent("This browser cannot play this camera's video.");
    // the other camera is not affected
    fireEvent.loadedData(videoOf("wrist"));
    expect(screen.getByTestId("episode-video-wrist")).toHaveAttribute("data-state", "ready");
  });

  it("a camera without a file says so, in Vietnamese too", async () => {
    const h = setupStation();
    server.use(
      http.get(`${stationBase()}/datasets/:name/episodes/:i/videos/:cam`, () =>
        HttpResponse.json(
          { code: "video_missing", status: 404, title: "x", detail: "x", type: "x", request_id: "" },
          { status: 404 },
        ),
      ),
    );
    await act(async () => {
      await i18n.changeLanguage("vi");
    });
    try {
      renderStation("/datasets/picknplace_red", h);
      await settle();
      await openEpisode(1);
      fireEvent.error(videoOf("wrist"));
      const tile = screen.getByTestId("episode-video-wrist");
      await waitFor(() => {
        expect(tile).toHaveAttribute("data-state", "error");
      });
      expect(tile).toHaveTextContent("Camera này không có tệp video cho tập này.");
      expect(screen.getByRole("button", { name: "Phát" })).toBeInTheDocument();
    } finally {
      await act(async () => {
        await i18n.changeLanguage("en");
      });
    }
  });

  it("an error the Station already knows per camera shows without a request", async () => {
    const h = setupStation();
    server.use(
      http.get(`${stationBase()}/datasets/:name/episodes/:i/videos`, () =>
        HttpResponse.json({
          dataset: "picknplace_red",
          episode: 0,
          fps: 30,
          length_s: 30,
          cameras: [
            cam({ camera: "wrist" }),
            cam({ camera: "front", error: "video_unavailable", formats: [] }),
          ],
        }),
      ),
    );
    renderStation("/datasets/picknplace_red", h);
    await settle();
    await openEpisode(1);
    const tile = screen.getByTestId("episode-video-front");
    expect(tile).toHaveAttribute("data-state", "error");
    expect(tile.querySelector("video")).toBeNull();
    expect(tile).toHaveTextContent("This camera's video cannot be read.");
  });

  it("a dataset being recorded says its videos open when the recording ends", async () => {
    const h = setupStation();
    server.use(
      http.get(`${stationBase()}/datasets/:name/episodes/:i/videos`, () =>
        HttpResponse.json(
          {
            code: "episode_saving",
            status: 409,
            title: "x",
            detail: "x",
            type: "x",
            request_id: "",
            params: { dataset: "picknplace_red" },
          },
          { status: 409 },
        ),
      ),
    );
    renderStation("/datasets/picknplace_red", h);
    await settle();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "#1" }));
    expect(
      await screen.findByText(
        "This dataset is still being recorded. Its videos open when the recording ends.",
      ),
    ).toBeInTheDocument();
  });
});
