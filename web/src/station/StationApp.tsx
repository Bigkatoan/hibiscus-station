import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { RouterProvider, createBrowserRouter, type RouteObject } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/lib/theme";
import { CalibratePage } from "./pages/CalibratePage";
import { CamerasPage } from "./pages/CamerasPage";
import { DatasetDetailPage, DatasetsPage, DatasetsPageError } from "./pages/DatasetsPage";
import { ProgramsPage } from "./pages/programs/ProgramsPage";
import { ModelsPage, SessionsPage, SettingsPage, TrainPage, WelcomePage } from "./pages/OtherPages";
import { RecordPage } from "./pages/RecordPage";
import { RobotPage } from "./pages/RobotPage";
import { RunModelPage } from "./pages/RunModelPage";
import { ReplayPage, TeleopPage } from "./pages/TeleopPage";
import { StationShell } from "./StationShell";
import { StationApiError } from "./api/client";
import { LockGate } from "./components/LockGate";
import { StationProvider, type StationRuntime } from "./ws/StationProvider";

export const stationRoutes: RouteObject[] = [
  {
    path: "/",
    element: <StationShell />,
    children: [
      { index: true, element: <WelcomePage /> },
      { path: "robot", element: <RobotPage /> },
      {
        path: "calibrate",
        element: (
          <LockGate step="calibrate">
            <CalibratePage />
          </LockGate>
        ),
      },
      {
        path: "cameras",
        element: (
          <LockGate step="cameras">
            <CamerasPage />
          </LockGate>
        ),
      },
      {
        path: "teleop",
        element: (
          <LockGate step="teleop">
            <TeleopPage />
          </LockGate>
        ),
      },
      {
        path: "record",
        element: (
          <LockGate step="record">
            <RecordPage />
          </LockGate>
        ),
      },
      { path: "replay", element: <ReplayPage /> },
      {
        path: "upload",
        element: (
          <LockGate step="upload">
            <DatasetsPage />
          </LockGate>
        ),
        errorElement: <DatasetsPageError />,
      },
      { path: "datasets", element: <DatasetsPage />, errorElement: <DatasetsPageError /> },
      { path: "datasets/:name", element: <DatasetDetailPage />, errorElement: <DatasetsPageError /> },
      {
        path: "train",
        element: (
          <LockGate step="train">
            <TrainPage />
          </LockGate>
        ),
      },
      {
        path: "run",
        element: (
          <LockGate step="run">
            <RunModelPage />
          </LockGate>
        ),
      },
      { path: "programs", element: <ProgramsPage /> },
      { path: "models", element: <ModelsPage /> },
      { path: "sessions", element: <SessionsPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "*", element: <WelcomePage /> },
    ],
  },
];

export function StationProviders({
  runtime,
  client,
  children,
}: {
  runtime: StationRuntime;
  client: QueryClient;
  children: ReactNode;
}) {
  return (
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <TooltipProvider delayDuration={200}>
          <StationProvider runtime={runtime}>{children}</StationProvider>
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

/** One retry for network and server errors; a 4xx answer (not found, refused) never changes on a retry. */
export function retryOnce(failures: number, error: unknown): boolean {
  if (error instanceof StationApiError && error.status >= 400 && error.status < 500) return false;
  return failures < 1;
}

export function StationApp({ runtime }: { runtime: StationRuntime }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { retry: retryOnce, refetchOnWindowFocus: false, staleTime: 2000 } },
      }),
  );
  const [router] = useState(() =>
    createBrowserRouter(stationRoutes, { future: { v7_relativeSplatPath: true } }),
  );
  return (
    <StationProviders runtime={runtime} client={client}>
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
    </StationProviders>
  );
}
