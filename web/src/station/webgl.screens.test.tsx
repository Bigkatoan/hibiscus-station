/**
 * A PC whose browser has the WebGL 2 API but cannot make a context (remote desktop, a VM, an old
 * or blocklisted GPU, headless Firefox in CI): every page with the Robot 3D view shows a calm note
 * in its place, the rest of the page works, and nothing is logged at error level (QD-18 guard).
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { i18n } from "@/lib/i18n";
import { resetWebGLProbe } from "./twin/webgl";
import { advance, renderStation, settle, setupStation } from "./test/utils";

const TEXT = {
  en: "This computer cannot show the 3D model (the browser does not support WebGL). Everything else still works.",
  vi: "Máy này không hiển thị được mô hình 3D (trình duyệt không hỗ trợ WebGL). Mọi chức năng khác vẫn dùng được.",
} as const;

let getContext: MockInstance;
let consoleError: MockInstance;
const hadWebGL2 = "WebGL2RenderingContext" in window;

beforeEach(() => {
  vi.stubGlobal(
    "createImageBitmap",
    vi.fn(() => Promise.resolve({ width: 320, height: 240, close: vi.fn() })),
  );
  // The WebGL 2 API exists, but the browser gives no context; 2D canvases (cameras, Blockly) work.
  Object.assign(window, { WebGL2RenderingContext: Object });
  getContext = vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(((type: string) =>
    type === "2d"
      ? {
          drawImage: vi.fn(),
          measureText: (s: string) => ({ width: s.length * 7 }),
          font: "",
        }
      : null) as unknown as HTMLCanvasElement["getContext"]);
  consoleError = vi.spyOn(console, "error");
  resetWebGLProbe();
});

afterEach(async () => {
  vi.unstubAllGlobals();
  if (!hadWebGL2) delete (window as { WebGL2RenderingContext?: unknown }).WebGL2RenderingContext;
  resetWebGLProbe();
  await i18n.changeLanguage("en");
});

function webglErrors(): unknown[][] {
  return consoleError.mock.calls.filter((args) => args.some((a) => /webgl/i.test(String(a))));
}

describe("Robot 3D on a PC without WebGL", () => {
  it.each(["en", "vi"] as const)("Teleop shows the note in place of the 3D view (%s)", async (lang) => {
    await i18n.changeLanguage(lang);
    const h = setupStation();
    const user = userEvent.setup();
    renderStation("/teleop", h);
    await settle();
    await user.click(
      await screen.findByRole("button", { name: lang === "en" ? "Start teleop" : "Bắt đầu điều khiển" }),
    );
    await advance(h.sim, 1.0);
    const twin = await screen.findByTestId("robot-twin");
    expect(twin).toHaveAttribute("data-state", "no-webgl");
    const note = within(twin).getByTestId("twin-no-webgl");
    expect(note).toHaveAttribute("role", "note");
    expect(note).toHaveTextContent(TEXT[lang]);
    expect(note.querySelector("svg.px-icon")).not.toBeNull();
    expect(within(twin).queryByTestId("twin-canvas")).toBeNull();
    expect(
      within(twin).queryByRole("button", { name: i18n.t("twin.reset_view", { ns: "station" }) }),
    ).toBeNull();
    // The rest of the live view still works.
    expect(screen.getByTestId("joint-panel")).toBeInTheDocument();
    expect(getContext).toHaveBeenCalledWith("webgl2", expect.anything());
    expect(webglErrors()).toEqual([]);
  });

  it.each(["en", "vi"] as const)("the Programs run panel shows the same note (%s)", async (lang) => {
    await i18n.changeLanguage(lang);
    const h = setupStation();
    renderStation("/programs?tab=programs", h);
    await settle();
    // the Blockly chunk loads lazily: the first test to open it waits for the import (as field029)
    await screen.findByTestId("blockly-editor", {}, { timeout: 15000 });
    const twin = await screen.findByTestId("robot-twin");
    expect(twin).toHaveAttribute("data-state", "no-webgl");
    expect(within(twin).getByTestId("twin-no-webgl")).toHaveTextContent(TEXT[lang]);
    await waitFor(() => {
      expect(document.querySelector('[data-id="play_a"]')).not.toBeNull();
    });
    expect(webglErrors()).toEqual([]);
  });
});
