import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { RouterProvider, createBrowserRouter, type RouteObject } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/lib/theme";
import { CalibratePage } from "./pages/CalibratePage";
import { CamerasPage } from "./pages/CamerasPage";
import { DatasetDetailPage, DatasetsPage } from "./pages/DatasetsPage";
import { ProgramsPage } from "./pages/programs/ProgramsPage";
import { ModelsPage, SessionsPage, SettingsPage, TrainPage, WelcomePage } from "./pages/OtherPages";
import { RecordPage } from "./pages/RecordPage";
import { RobotPage } from "./pages/RobotPage";
import { RunModelPage } from "./pages/RunModelPage";
import { ReplayPage, TeleopPage } from "./pages/TeleopPage";
import { StationShell } from "./StationShell";
import { StationProvider, type StationRuntime } from "./ws/StationProvider";

export const stationRoutes: RouteObject[] = [
  {
    path: "/",
    element: <StationShell />,
    children: [
      { index: true, element: <WelcomePage /> },
      { path: "robot", element: <RobotPage /> },
      { path: "calibrate", element: <CalibratePage /> },
      { path: "cameras", element: <CamerasPage /> },
      { path: "teleop", element: <TeleopPage /> },
      { path: "record", element: <RecordPage /> },
      { path: "replay", element: <ReplayPage /> },
      { path: "upload", element: <DatasetsPage /> },
      { path: "datasets", element: <DatasetsPage /> },
      { path: "datasets/:name", element: <DatasetDetailPage /> },
      { path: "train", element: <TrainPage /> },
      { path: "run", element: <RunModelPage /> },
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

export function StationApp({ runtime }: { runtime: StationRuntime }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 2000 } },
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
