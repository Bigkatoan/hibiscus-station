/**
 * Field report 0.2.9 (customer check_ver_2.9, 2026-11-18) against the mock Station.
 *
 * D-24: "the first motion starts far from the arm" stayed on the program as a warning after the
 * run. It is now information ("The arm will first move slowly to the start of this motion (X°
 * away)."), listed apart from the problems, never in the run confirmation, and it follows the arm:
 * it goes away once the arm is within the limit.
 *
 * D-25: Train looked locked ("This step is locked — Pair with a Hibiscus server first") while its
 * pairing form worked. Training needs no robot: the step shows a neutral prompt, no lock. The
 * pairing form refuses an address that is not http(s) or is a file-share link (the customer pasted
 * a OneDrive link).
 */
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@/lib/i18n";
import { MOTORS } from "./mock/fixtures";
import { renderStation, settle, setupStation, type StationHarness } from "./test/utils";

beforeEach(() => {
  vi.stubGlobal(
    "createImageBitmap",
    vi.fn(() => Promise.resolve({ width: 320, height: 240, close: vi.fn() })),
  );
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    () =>
      ({
        drawImage: vi.fn(),
        measureText: (s: string) => ({ width: s.length * 7 }),
        font: "",
      }) as unknown as CanvasRenderingContext2D,
  );
  return () => {
    vi.unstubAllGlobals();
  };
});

/** The start pose of "Pick A" (the sample program's first motion), as joint values. */
function startOfPickA(h: StationHarness): number[] {
  const take = h.sim.programs.takes.find((x) => x.meta.id === "t_20261116_101500_a1b2");
  if (!take) throw new Error("no Pick A");
  return MOTORS.map((m) => take.meta.start_pose[`${m}.pos`] ?? 0);
}

/** A live joint stream (20 Hz), as from a connected robot; stopped after each test. */
let stream: ReturnType<typeof setInterval> | null = null;
afterEach(() => {
  if (stream) clearInterval(stream);
  stream = null;
});

/** Hold the follower at `pose`, with the joint stream running. */
async function holdArm(h: StationHarness, pose: number[]): Promise<void> {
  h.sim.pinnedPose = pose;
  stream ??= setInterval(() => {
    act(() => {
      h.sim.step(0.05);
    });
  }, 50);
  await act(async () => {
    for (let i = 0; i < 4; i += 1) h.sim.step(0.05);
    await new Promise((r) => setTimeout(r, 0));
  });
}

/** The joint stream stops (robot unplugged, Station stalled): the store keeps the last pose. */
function stopStream(): void {
  if (stream) clearInterval(stream);
  stream = null;
}

async function openEditor(h: StationHarness) {
  renderStation("/programs?tab=programs", h);
  await settle();
  // The editor is a lazy chunk: the first test of the file loads it (slow on a busy CI runner).
  await screen.findByTestId("blockly-editor", {}, { timeout: 15000 });
  await waitFor(
    () => {
      expect(document.querySelector('[data-id="play_a"]')).not.toBeNull();
    },
    { timeout: 15000 },
  );
}

describe(
  "D-24: the first motion's slow approach is information that follows the arm",
  { timeout: 40000 },
  () => {
    it("is an information line, not a problem, and goes away once the arm is near", async () => {
      const h = setupStation();
      const start = startOfPickA(h);
      const far = start.map((v, i) => (i === 0 ? v + 60 : v));
      await holdArm(h, far);
      const user = userEvent.setup();
      await openEditor(h);
      await user.click(screen.getByRole("button", { name: "Check" }));
      const notes = await screen.findByTestId("program-notes");
      expect(notes).toHaveTextContent(
        "The arm will first move slowly to the start of this motion (60° away).",
      );
      expect(within(notes).getByRole("listitem")).toHaveAttribute("data-severity", "info");
      // Not a problem: no problem list, "No problems found." stays.
      expect(screen.queryByTestId("program-issues")).toBeNull();
      expect(screen.getByTestId("program-ok")).toBeInTheDocument();
      expect(screen.queryByText(/starts far from the arm/)).toBeNull();

      // The arm moves to 20° from the start (within the 30° limit): the line goes away by itself,
      // without pressing Check again.
      await holdArm(
        h,
        start.map((v, i) => (i === 0 ? v + 20 : v)),
      );
      await waitFor(
        () => {
          expect(screen.queryByTestId("program-notes")).toBeNull();
        },
        { timeout: 4000 },
      );

      // And comes back, with the new distance, when the arm moves away again.
      await holdArm(
        h,
        start.map((v, i) => (i === 0 ? v - 45 : v)),
      );
      await waitFor(
        () => {
          expect(screen.getByTestId("program-notes")).toHaveTextContent("(45° away)");
        },
        { timeout: 4000 },
      );
    });

    it("never asks for a confirmation before a run", async () => {
      const h = setupStation();
      const start = startOfPickA(h);
      await holdArm(
        h,
        start.map((v, i) => (i === 0 ? v + 60 : v)),
      );
      const user = userEvent.setup();
      await openEditor(h);
      await user.click(screen.getByRole("button", { name: "Dry run" }));
      await waitFor(() => {
        expect(h.sim.programs.run).not.toBeNull();
      });
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(screen.getByTestId("program-notes")).toHaveTextContent("(60° away)");
    });

    it("is in Vietnamese with the distance", async () => {
      const h = setupStation();
      const start = startOfPickA(h);
      await holdArm(
        h,
        start.map((v, i) => (i === 0 ? v + 60 : v)),
      );
      await act(async () => {
        await i18n.changeLanguage("vi");
      });
      try {
        const user = userEvent.setup();
        await openEditor(h);
        await user.click(screen.getByRole("button", { name: "Kiểm tra" }));
        expect(await screen.findByTestId("program-notes")).toHaveTextContent(
          "Tay sẽ đi chậm về điểm bắt đầu của chuyển động này (cách 60°).",
        );
      } finally {
        await act(async () => {
          await i18n.changeLanguage("en");
        });
      }
    });
  },
);

describe("QC F029 r1: QD-36 and the look of the information line", { timeout: 40000 }, () => {
  async function checkedFar(h: StationHarness, user: ReturnType<typeof userEvent.setup>) {
    const start = startOfPickA(h);
    await holdArm(
      h,
      start.map((v, i) => (i === 0 ? v + 60 : v)),
    );
    await openEditor(h);
    await user.click(screen.getByRole("button", { name: "Check" }));
    expect(await screen.findByTestId("program-notes")).toHaveTextContent("(60° away)");
  }

  it("QD-36: the line goes away when the robot disconnects, and comes back on reconnect", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    await checkedFar(h, user);
    act(() => {
      h.sim.disconnect();
    });
    await waitFor(
      () => {
        expect(screen.queryByTestId("program-notes")).toBeNull();
      },
      { timeout: 3000 },
    );
    // Still gone a while later (no stale check brings it back).
    await act(async () => {
      await new Promise((r) => setTimeout(r, 1700));
    });
    expect(screen.queryByTestId("program-notes")).toBeNull();
    act(() => {
      h.sim.doConnect("desk_so101");
    });
    await waitFor(
      () => {
        expect(screen.getByTestId("program-notes")).toHaveTextContent("(60° away)");
      },
      { timeout: 4000 },
    );
  });

  it("QD-36: the line goes away when the joint stream goes stale", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    await checkedFar(h, user);
    stopStream();
    await waitFor(
      () => {
        expect(screen.queryByTestId("program-notes")).toBeNull();
      },
      { timeout: 5000 },
    );
  });

  it("information has its own titled box, apart from warnings and confirmations (EN + VI)", async () => {
    const h = setupStation();
    // A stray "relax arm" block outside the start block: a warning (unreachable).
    const p = h.sim.programs.program("sort_cubes");
    const editor = structuredClone(p.editor) as { blocks: { blocks: Record<string, unknown>[] } };
    editor.blocks.blocks.push({ type: "hb_relax_arm", id: "lonely", x: 600, y: 40 });
    h.sim.programs.putProgram("sort_cubes", { name: p.name, editor, buttons: p.buttons });
    const user = userEvent.setup();
    await checkedFar(h, user);
    const problems = screen.getByTestId("program-issues");
    const warning = within(problems)
      .getAllByRole("listitem")
      .find((li) => li.getAttribute("data-severity") === "warning");
    if (!warning) throw new Error("no warning in the problem list");
    expect(within(warning).getByRole("img", { name: "Warning" })).toBeInTheDocument();
    const notes = screen.getByTestId("program-notes");
    expect(within(notes).getByRole("heading", { name: "Notes" })).toBeInTheDocument();
    expect(within(notes).queryByRole("img", { name: "Warning" })).toBeNull();
    expect(within(problems).queryByText(/move slowly/)).toBeNull();
    await act(async () => {
      await i18n.changeLanguage("vi");
    });
    try {
      expect(within(notes).getByRole("heading", { name: "Ghi chú" })).toBeInTheDocument();
      expect(within(problems).getAllByRole("img", { name: "Cảnh báo" }).length).toBeGreaterThan(0);
    } finally {
      await act(async () => {
        await i18n.changeLanguage("en");
      });
    }
  });
});

describe("D-25: Train needs a server, not a robot", () => {
  it("shows a neutral prompt, no lock, with or without a robot", async () => {
    for (const connected of [true, false]) {
      const h = setupStation({ connected });
      const { unmount } = renderStation("/train", h);
      await settle();
      const hint = await screen.findByTestId("step-hint");
      expect(hint).toHaveTextContent("Connect to a Hibiscus server to train (no robot needed).");
      expect(screen.queryByTestId("lock-gate")).toBeNull();
      expect(screen.queryByText("This step is locked")).toBeNull();
      expect(screen.queryByTestId("locked-content")).toBeNull();
      // The rail says the same, without a lock.
      expect(screen.getByTestId("step-hint-train")).toHaveTextContent(
        "Connect to a Hibiscus server to train (no robot needed).",
      );
      expect(screen.getByRole("link", { name: /Train/ })).toHaveAttribute(
        "title",
        "Connect to a Hibiscus server to train (no robot needed).",
      );
      unmount();
    }
  });

  it("the prompt goes away once paired", async () => {
    const h = setupStation({ paired: true });
    renderStation("/train", h);
    await settle();
    await screen.findByRole("heading", { name: "Train" });
    expect(screen.queryByTestId("step-hint")).toBeNull();
    expect(screen.queryByTestId("step-hint-train")).toBeNull();
  });

  it("the pairing form refuses a OneDrive link and a non-http address", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    renderStation("/train", h);
    await settle();
    const url = await screen.findByLabelText(/Server URL/);
    const pair = screen.getByRole("button", { name: "Pair" });
    await user.type(screen.getByLabelText(/Personal access token/), "hb_pat_123");
    await user.type(
      url,
      "https://onedrive.live.com/?redeem=aHR0cHM6Ly8xZHJ2Lm1zL2YvcyFBbXBsZQ&id=ABC%21123&cid=0123456789ABCDEF",
    );
    expect(
      screen.getByText(
        "This is not a Hibiscus server address. Paste the address of your Hibiscus site, for example https://hibiscus.example.org",
      ),
    ).toBeInTheDocument();
    expect(url).toHaveAttribute("aria-invalid", "true");
    expect(pair).toBeDisabled();

    // QD-35: the link the customer actually pasted (OneDrive on word.cloud.microsoft).
    await user.clear(url);
    await user.type(
      url,
      "https://word.cloud.microsoft/open/onedrive/?docId=0123456789ABCDEF%21s1a2b3c4d5e6f&driveId=0123456789ABCDEF",
    );
    expect(
      screen.getByText(
        "This is not a Hibiscus server address. Paste the address of your Hibiscus site, for example https://hibiscus.example.org",
      ),
    ).toBeInTheDocument();
    expect(pair).toBeDisabled();
    expect(screen.queryByRole("link", { name: /Create a token/ })).toBeNull();

    await user.clear(url);
    await user.type(url, "hibiscus server");
    await user.tab();
    expect(
      screen.getByText(
        "Enter an address that starts with http:// or https://, for example https://hibiscus.example.org",
      ),
    ).toBeInTheDocument();
    expect(pair).toBeDisabled();

    await user.clear(url);
    await user.type(url, "https://hibiscus.example.org");
    expect(url).not.toHaveAttribute("aria-invalid");
    expect(pair).toBeEnabled();
  });

  it("says it in Vietnamese", async () => {
    const h = setupStation();
    await act(async () => {
      await i18n.changeLanguage("vi");
    });
    try {
      const user = userEvent.setup();
      renderStation("/train", h);
      await settle();
      expect(await screen.findByTestId("step-hint")).toHaveTextContent(
        "Kết nối máy chủ Hibiscus để huấn luyện (không cần robot).",
      );
      await user.type(
        await screen.findByLabelText(/Địa chỉ máy chủ/),
        "https://contoso-my.sharepoint.com/:f:/g/personal/x/EabC?e=1",
      );
      expect(
        screen.getByText(
          "Đây không phải địa chỉ máy chủ Hibiscus. Hãy dán địa chỉ trang Hibiscus của bạn, ví dụ https://hibiscus.example.org",
        ),
      ).toBeInTheDocument();
    } finally {
      await act(async () => {
        await i18n.changeLanguage("en");
      });
    }
  });
});

describe("QC F029 r2: QD-37, QD-38, QD-39, QD-41", { timeout: 40000 }, () => {
  async function checkedFar(h: StationHarness, user: ReturnType<typeof userEvent.setup>) {
    const start = startOfPickA(h);
    await holdArm(
      h,
      start.map((v, i) => (i === 0 ? v + 60 : v)),
    );
    await openEditor(h);
    await user.click(screen.getByRole("button", { name: "Check" }));
    expect(await screen.findByTestId("program-notes")).toHaveTextContent("(60° away)");
  }

  it("QD-38: a reconnect within a second brings the line back without moving the arm", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    await checkedFar(h, user);
    act(() => {
      h.sim.disconnect();
    });
    await waitFor(
      () => {
        expect(screen.queryByTestId("program-notes")).toBeNull();
      },
      { timeout: 3000 },
    );
    await act(async () => {
      await new Promise((r) => setTimeout(r, 200));
    });
    act(() => {
      h.sim.doConnect("desk_so101");
    });
    await waitFor(
      () => {
        expect(screen.getByTestId("program-notes")).toHaveTextContent("(60° away)");
      },
      { timeout: 5000 },
    );
  });

  it("QD-37: error, warning and confirm have their own shape and colour", async () => {
    const h = setupStation();
    const profile = h.sim.profiles[0];
    if (profile) profile.follower.allow_fast_replay = true;
    const p = h.sim.programs.program("sort_cubes");
    const editor = structuredClone(p.editor) as { blocks: { blocks: Record<string, unknown>[] } };
    const speedUp = (b: unknown): void => {
      if (!b || typeof b !== "object") return;
      const o = b as Record<string, unknown>;
      if (o.id === "play_a") (o.fields as Record<string, unknown>).SPEED = 150; // confirm
      for (const v of Object.values(o)) {
        if (Array.isArray(v)) v.forEach(speedUp);
        else if (v && typeof v === "object") speedUp(v);
      }
    };
    speedUp(editor);
    editor.blocks.blocks.push({ type: "hb_relax_arm", id: "lonely", x: 600, y: 40 }); // warning
    editor.blocks.blocks.push({
      type: "hb_move_to_pose",
      id: "nowhere",
      x: 600,
      y: 200,
      fields: { POSE: "nope" },
    }); // error
    h.sim.programs.putProgram("sort_cubes", { name: p.name, editor, buttons: p.buttons });
    const user = userEvent.setup();
    await checkedFar(h, user);
    const problems = screen.getByTestId("program-issues");
    const badge = (sev: string) => {
      const el = problems.querySelector(`[data-badge="${sev}"]`);
      if (!el) throw new Error(`no ${sev} badge`);
      return el;
    };
    const shape = (sev: string) => badge(sev).querySelector("path")?.getAttribute("d") ?? "";
    expect(new Set([shape("error"), shape("warning"), shape("confirm")]).size).toBe(3);
    expect(badge("error")).toHaveClass("bg-sev-error");
    expect(badge("warning")).toHaveClass("bg-sev-warning");
    expect(badge("confirm")).toHaveClass("bg-sev-confirm");
    expect(within(problems).getByRole("img", { name: "Error" })).toBeInTheDocument();
    expect(within(problems).getAllByRole("img", { name: "Warning" }).length).toBeGreaterThan(0);
    expect(within(problems).getByRole("img", { name: "Needs your confirmation" })).toBeInTheDocument();
  });

  it("QD-39: in Vietnamese, a refusal from the Station shows only the Vietnamese sentence", async () => {
    const h = setupStation();
    const { server } = await import("@/test/server");
    const { http, HttpResponse } = await import("msw");
    const { stationBase } = await import("./api/client");
    server.use(
      http.post(`${stationBase()}/server/pair`, () =>
        HttpResponse.json(
          {
            type: "https://hibiscus.dev/problems/station/server_not_hibiscus",
            title: "This address did not answer as a Hibiscus server",
            status: 422,
            code: "server_not_hibiscus",
            detail: "https://hibiscus.example.org/api/v1 did not answer as a Hibiscus server: HTTP 404",
            request_id: "r",
          },
          { status: 422, headers: { "Content-Type": "application/problem+json" } },
        ),
      ),
    );
    await act(async () => {
      await i18n.changeLanguage("vi");
    });
    try {
      const user = userEvent.setup();
      renderStation("/train", h);
      await settle();
      await user.type(await screen.findByLabelText(/Địa chỉ máy chủ/), "https://hibiscus.example.org");
      await user.type(screen.getByLabelText(/Token truy cập cá nhân/), "hbp_AbCd1234_xxxxxxxxxxxx");
      await user.click(screen.getByRole("button", { name: "Ghép nối" }));
      expect(await screen.findByText(/^Địa chỉ này không phản hồi như một máy chủ Hibiscus\./)).toBeVisible();
      // The English detail is only in the closed "Chi tiết kỹ thuật".
      expect(screen.getByTestId("error-detail")).not.toBeVisible();
      expect(within(screen.getByTestId("error-details")).getByText("Chi tiết kỹ thuật")).toBeVisible();
    } finally {
      await act(async () => {
        await i18n.changeLanguage("en");
      });
    }
  });

  it("QD-41: a real server address with ?cid= or a file path is not refused by the hint", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    renderStation("/train", h);
    await settle();
    const url = await screen.findByLabelText(/Server URL/);
    await user.type(screen.getByLabelText(/Personal access token/), "hbp_pat_123");
    for (const ok of [
      "https://hibiscus.example.org/?cid=campaign1",
      "https://hibiscus.example.org/robots.txt",
    ]) {
      await user.clear(url);
      await user.type(url, ok);
      await user.tab();
      expect(url).not.toHaveAttribute("aria-invalid");
      expect(screen.getByRole("button", { name: "Pair" })).toBeEnabled();
    }
  });
});
