import { act, render } from "@testing-library/react";
import type { ReactElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { server } from "@/test/server";
import { testQueryClient } from "@/test/render";
import { registerStationI18n } from "../i18n";
import { stationHandlers } from "../mock/handlers";
import { MockStation, type MockOptions } from "../mock/sim";
import { StationProviders, stationRoutes } from "../StationApp";
import { createRuntime, type StationRuntime } from "../ws/StationProvider";

export interface StationHarness {
  sim: MockStation;
  runtime: StationRuntime;
}

export function setupStation(opts: MockOptions = {}): StationHarness {
  registerStationI18n();
  const sim = new MockStation({ connected: true, ...opts });
  server.use(...stationHandlers(sim));
  const runtime = createRuntime(sim.socketFactory);
  return { sim, runtime };
}

/** Render the full station route tree at `url`. */
export function renderStation(url: string, h: StationHarness) {
  const router = createMemoryRouter(stationRoutes, {
    initialEntries: [url],
    future: { v7_relativeSplatPath: true },
  });
  const client = testQueryClient();
  const result = render(
    <StationProviders runtime={h.runtime} client={client}>
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
    </StationProviders>,
  );
  return { ...result, router, client };
}

/** Render one element inside the station providers (no router needed). */
export function renderWithStation(el: ReactElement, h: StationHarness) {
  const router = createMemoryRouter([{ path: "*", element: el }], { initialEntries: ["/"] });
  return render(
    <StationProviders runtime={h.runtime} client={testQueryClient()}>
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
    </StationProviders>,
  );
}

/** Advance the simulated station by `seconds` in 50 ms steps, inside act(). */
export async function advance(sim: MockStation, seconds: number): Promise<void> {
  await act(async () => {
    const n = Math.round(seconds / 0.05);
    for (let i = 0; i < n; i += 1) sim.step(0.05);
    await new Promise((r) => setTimeout(r, 0));
  });
}

/** Let the mock sockets open (they connect on the next macrotask). */
export async function settle(): Promise<void> {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 5));
  });
}
