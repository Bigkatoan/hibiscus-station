/** Hibiscus Station UI entry (index.html → dist/, bundled into the wheel as hibiscus_station/static). */
import "@/lib/localeGuard";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { initI18n } from "@/lib/i18n";
import { registerStationI18n } from "./i18n";
import { StationApp } from "./StationApp";
import type { SocketFactory } from "./ws/control";
import { createRuntime } from "./ws/StationProvider";
import "@/index.css";
import "./station.css";

async function boot(): Promise<void> {
  let factory: SocketFactory | undefined;
  // Mock mode only (vite --mode mock); statically false and tree-shaken otherwise.
  if (import.meta.env.VITE_STATION_MOCK === "1") {
    const { startStationMock } = await import("./mock/browser");
    factory = await startStationMock();
  }
  initI18n();
  registerStationI18n();
  document.title = "Hibiscus Station";
  const runtime = createRuntime(factory);
  const root = document.getElementById("root");
  if (root) {
    createRoot(root).render(
      <StrictMode>
        <StationApp runtime={runtime} />
      </StrictMode>,
    );
  }
}

void boot();
