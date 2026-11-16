/// <reference types="vitest/config" />
/**
 * Hibiscus Station UI (docs/spec/station.md §6).
 *
 *   vite                 dev server on 127.0.0.1:18211, proxies /api (+ WebSockets) and /auth to 127.0.0.1:18210
 *   vite --mode mock     dev without a backend (MSW + the in-page mock station)
 *   vite build           → dist/ (bundled into the wheel as hibiscus_station/static by hatch_build.py)
 *   vitest               unit and screen tests (jsdom)
 */
import { readFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig, type HttpProxy, type Plugin } from "vite";

const stationTarget = process.env.HIBISCUS_STATION_API ?? "http://127.0.0.1:18210";

/** Mock mode only: serve/emit MSW's service worker without committing it to public/. */
function mswWorker(): Plugin {
  const file = fileURLToPath(new URL("./node_modules/msw/lib/mockServiceWorker.js", import.meta.url));
  return {
    name: "station-msw-worker",
    configureServer(server) {
      server.middlewares.use("/mockServiceWorker.js", (_req, res) => {
        res.setHeader("Content-Type", "text/javascript");
        res.end(readFileSync(file));
      });
    },
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "mockServiceWorker.js", source: readFileSync(file) });
    },
  };
}

/** Present proxied requests (HTTP and WebSocket upgrades) as coming from the Station origin. */
function sameOrigin(proxy: HttpProxy.Server): void {
  const origin = new URL(stationTarget).origin;
  proxy.on("proxyReq", (req) => {
    if (req.getHeader("origin")) req.setHeader("origin", origin);
  });
  proxy.on("proxyReqWs", (req) => {
    req.setHeader("origin", origin);
  });
}

export default defineConfig(({ mode }) => {
  const mock = mode === "mock";
  return {
    plugins: mock ? [react(), mswWorker()] : [react()],
    define: mock ? { "import.meta.env.VITE_STATION_MOCK": JSON.stringify("1") } : {},
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: {
      host: "127.0.0.1",
      port: 18211,
      strictPort: true,
      // Station only accepts its own Host and Origin (§8): the proxy rewrites both to the target, so
      // log in through the dev server with http://127.0.0.1:18211/auth?t=<token> (`hibiscus-station url`).
      proxy: mock
        ? {}
        : {
            "/api": { target: stationTarget, changeOrigin: true, ws: true, configure: sameOrigin },
            "/auth": { target: stationTarget, changeOrigin: true, configure: sameOrigin },
          },
    },
    preview: { host: "127.0.0.1", port: 18212, strictPort: true },
    build: {
      outDir: mock ? "dist-mock" : "dist",
      emptyOutDir: true,
      sourcemap: false,
      target: "es2022",
      chunkSizeWarningLimit: 900,
      // The 3D twin links its licence texts and fetches its meshes: keep them as files, not data: URLs.
      assetsInlineLimit: (file: string) => (/\.(txt|stl)$/.test(file) ? false : undefined),
      rollupOptions: {
        output: {
          manualChunks: {
            // Own chunk, imported first by the entry: it must run before uPlot reads
            // navigator.language at module load (`en-US@posix` under LANG=C would throw there).
            "locale-guard": ["./src/lib/localeGuard.ts"],
            react: ["react", "react-dom", "react-router-dom"],
            query: ["@tanstack/react-query"],
            charts: ["uplot"],
          },
        },
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      include: ["src/**/*.test.{ts,tsx}"],
      css: false,
      restoreMocks: true,
      testTimeout: 20000,
      coverage: {
        provider: "v8",
        include: ["src/**/*.{ts,tsx}"],
        exclude: [
          "src/station/api/schema.d.ts",
          "src/test/**",
          "src/**/*.test.{ts,tsx}",
          "src/station/main.tsx",
          "src/vite-env.d.ts",
        ],
        reporter: ["text-summary", "json-summary"],
      },
    },
  };
});
