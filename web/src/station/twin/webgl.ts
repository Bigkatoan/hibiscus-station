/**
 * WebGL support, probed without three.js. three.js r163+ draws only on WebGL 2, and when it cannot
 * create a context it logs at error level before throwing. Many real PCs have no WebGL 2: remote
 * desktop, virtual machines, old GPUs, a GPU on the browser's blocklist, headless browsers. So the
 * twin asks the browser itself (try/catch, nothing logged) and shows a calm note instead.
 */

/** The context attributes three.js would ask for with `{ antialias: true, powerPreference }`. */
export const TWIN_CONTEXT: WebGLContextAttributes = {
  alpha: true,
  depth: true,
  stencil: false,
  antialias: true,
  premultipliedAlpha: true,
  preserveDrawingBuffer: false,
  powerPreference: "low-power",
  failIfMajorPerformanceCaveat: false,
};

/** A WebGL 2 context on `canvas`, or null when the browser cannot make one. Never throws or logs. */
export function createWebGL2Context(
  canvas: HTMLCanvasElement,
  attrs: WebGLContextAttributes = TWIN_CONTEXT,
): WebGL2RenderingContext | null {
  try {
    if (typeof window === "undefined" || typeof window.WebGL2RenderingContext === "undefined") return null;
    return canvas.getContext("webgl2", attrs);
  } catch {
    return null;
  }
}

let probed: boolean | null = null;

function probe(): boolean {
  if (typeof document === "undefined") return false;
  const gl = createWebGL2Context(document.createElement("canvas"));
  if (!gl) return false;
  try {
    // Give the throwaway context back now; browsers cap the number of live contexts.
    gl.getExtension("WEBGL_lose_context")?.loseContext();
  } catch {
    /* the probe answered already */
  }
  return true;
}

/** True when this browser can draw the 3D twin (WebGL 2). Probed once per page load. */
export function hasWebGL(): boolean {
  probed ??= probe();
  return probed;
}

/** Forget the probe result (tests, or after the browser lost its GPU). */
export function resetWebGLProbe(): void {
  probed = null;
}

/** Thrown by the twin scene when the renderer cannot get a WebGL 2 context. */
export class WebGLUnavailableError extends Error {
  constructor(cause?: unknown) {
    super("WebGL 2 is not available", cause === undefined ? undefined : { cause });
    this.name = "WebGLUnavailableError";
  }
}
