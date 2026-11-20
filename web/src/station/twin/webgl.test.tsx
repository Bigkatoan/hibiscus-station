/**
 * The WebGL probe and the real TwinCanvas / TwinScene on a browser without a WebGL 2 context:
 * no three.js renderer is created, nothing is logged at error level, and the canvas reports
 * "no-webgl" so the twin shows its calm note (CI: headless Firefox has no WebGL 2).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithStation, settle, setupStation } from "../test/utils";
import TwinCanvas from "./TwinCanvas";
import { TwinScene } from "./scene";
import { createWebGL2Context, hasWebGL, resetWebGLProbe, WebGLUnavailableError } from "./webgl";

const hadWebGL2 = "WebGL2RenderingContext" in window;

function stubGetContext(impl: (type: string) => unknown) {
  return vi
    .spyOn(HTMLCanvasElement.prototype, "getContext")
    .mockImplementation(impl as unknown as HTMLCanvasElement["getContext"]);
}

beforeEach(() => {
  Object.assign(window, { WebGL2RenderingContext: Object });
  resetWebGLProbe();
});
afterEach(() => {
  vi.restoreAllMocks();
  if (!hadWebGL2) delete (window as { WebGL2RenderingContext?: unknown }).WebGL2RenderingContext;
  resetWebGLProbe();
});

describe("hasWebGL (throwaway canvas probe)", () => {
  it("is false when getContext('webgl2') returns null, and logs nothing", () => {
    const error = vi.spyOn(console, "error");
    const gc = stubGetContext(() => null);
    expect(hasWebGL()).toBe(false);
    expect(gc).toHaveBeenCalledWith("webgl2", expect.objectContaining({ antialias: true }));
    expect(error).not.toHaveBeenCalled();
  });

  it("is false when getContext throws", () => {
    stubGetContext(() => {
      throw new Error("blocklisted");
    });
    expect(hasWebGL()).toBe(false);
    expect(createWebGL2Context(document.createElement("canvas"))).toBeNull();
  });

  it("is false without the WebGL 2 API, without touching a canvas", () => {
    delete (window as { WebGL2RenderingContext?: unknown }).WebGL2RenderingContext;
    const gc = stubGetContext(() => ({}));
    expect(hasWebGL()).toBe(false);
    expect(gc).not.toHaveBeenCalled();
  });

  it("is true with a context, gives the throwaway context back, and probes once", () => {
    const loseContext = vi.fn();
    const gc = stubGetContext(() => ({ getExtension: () => ({ loseContext }) }));
    expect(hasWebGL()).toBe(true);
    expect(hasWebGL()).toBe(true);
    expect(gc).toHaveBeenCalledTimes(1);
    expect(loseContext).toHaveBeenCalledTimes(1);
  });
});

describe("TwinScene / TwinCanvas without a WebGL 2 context", () => {
  it("TwinScene throws WebGLUnavailableError before three.js tries (no error logged)", () => {
    const error = vi.spyOn(console, "error");
    stubGetContext(() => null);
    const host = document.createElement("div");
    expect(() => new TwinScene(host)).toThrow(WebGLUnavailableError);
    expect(host.childElementCount).toBe(0);
    expect(error).not.toHaveBeenCalled();
  });

  it("TwinCanvas reports no-webgl (not error) and logs nothing", async () => {
    const error = vi.spyOn(console, "error");
    stubGetContext(() => null);
    const h = setupStation();
    const onState = vi.fn();
    renderWithStation(
      <TwinCanvas ghost={null} levels={{}} theme="light" resetKey={0} label="3D" onState={onState} />,
      h,
    );
    await settle();
    expect(onState).toHaveBeenCalledWith("no-webgl");
    expect(onState).not.toHaveBeenCalledWith("error");
    expect(error).not.toHaveBeenCalled();
  });
});
