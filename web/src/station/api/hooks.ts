import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useEffect } from "react";
import { useRuntime } from "../ws/StationProvider";
import { api } from "./client";
import type {
  BlockCatalog,
  CalibrationCheck,
  CalibrationFile,
  CompatReport,
  Detector,
  DiscoveredCamera,
  Job,
  LocalDataset,
  LocalDatasetDetail,
  ModelEntry,
  Port,
  Pose,
  Program,
  ProgramRunLog,
  ProgramRunSummary,
  ProgramState,
  ProgramSummary,
  RobotProfile,
  ServerDataset,
  ServerLink,
  ServerModel,
  ServerRun,
  Session,
  SessionSummary,
  Settings,
  Signal,
  Status,
  TelemetrySeries,
  TrajectoryDetail,
  TrajectorySummary,
} from "./types";

export const qk = {
  status: ["station", "status"],
  settings: ["station", "settings"],
  robots: ["station", "robots"],
  ports: ["station", "ports"],
  calibrations: ["station", "calibrations"],
  calibrationCheck: ["station", "calibrations", "check"],
  discover: ["station", "cameras", "discover"],
  datasets: ["station", "datasets"],
  dataset: (name: string) => ["station", "datasets", name],
  episodeTelemetry: (name: string, i: number) => ["station", "datasets", name, "episodes", i],
  models: ["station", "models"],
  compat: (key: string, robot: string) => ["station", "models", key, "compat", robot],
  jobs: ["station", "jobs"],
  sessions: ["station", "sessions"],
  sessionTelemetry: (id: string) => ["station", "sessions", id, "telemetry"],
  server: ["station", "server"],
  serverDatasets: ["station", "server", "datasets"],
  serverModels: ["station", "server", "models"],
  serverRuns: (datasetId: string) => ["station", "server", "runs", datasetId],
  trajectories: ["station", "trajectories"],
  trajectory: (id: string) => ["station", "trajectories", id],
  poses: ["station", "poses"],
  detectors: ["station", "detectors"],
  signals: ["station", "signals"],
  blocks: ["station", "programs", "blocks"],
  programs: ["station", "programs"],
  program: (id: string) => ["station", "programs", "item", id],
  programRuns: (id: string) => ["station", "programs", "item", id, "runs"],
  programRun: (id: string, run: string) => ["station", "programs", "item", id, "runs", run],
  programState: (id: string) => ["station", "programs", "item", id, "state"],
} as const;

/** GET /status, mirrored into the live store (the WS keeps it fresh afterwards). */
export function useStatusQuery() {
  const { store } = useRuntime();
  const q = useQuery({ queryKey: qk.status, queryFn: () => api.get<Status>("/status") });
  useEffect(() => {
    if (q.data) store.setStatus(q.data);
  }, [q.data, store]);
  return q;
}

export const useSettings = () =>
  useQuery({ queryKey: qk.settings, queryFn: () => api.get<Settings>("/settings") });

export const useRobots = () =>
  useQuery({
    queryKey: qk.robots,
    queryFn: () => api.get<{ robots: RobotProfile[]; active: string | null }>("/robots"),
  });

export const usePorts = () =>
  useQuery({ queryKey: qk.ports, queryFn: () => api.get<{ ports: Port[] }>("/ports") });

/** Per connected arm: calibrated? which file on disk do its motors carry? (reads the EEPROM) */
export const useCalibrationCheck = (enabled: boolean) =>
  useQuery({
    queryKey: qk.calibrationCheck,
    queryFn: () => api.get<CalibrationCheck>("/calibration/check"),
    enabled,
    retry: false,
  });

export const useCalibrations = () =>
  useQuery({
    queryKey: qk.calibrations,
    queryFn: () => api.get<{ files: CalibrationFile[] }>("/calibrations"),
  });

export const useDiscoverCameras = (enabled = true) =>
  useQuery({
    queryKey: qk.discover,
    queryFn: () => api.get<{ cameras: DiscoveredCamera[] }>("/cameras/discover"),
    enabled,
  });

export const useDatasets = () =>
  useQuery({ queryKey: qk.datasets, queryFn: () => api.get<{ datasets: LocalDataset[] }>("/datasets") });

export const useDataset = (name: string) =>
  useQuery({
    queryKey: qk.dataset(name),
    queryFn: () => api.get<LocalDatasetDetail>(`/datasets/${encodeURIComponent(name)}`),
  });

export const useEpisodeTelemetry = (name: string, index: number | null) =>
  useQuery({
    queryKey: qk.episodeTelemetry(name, index ?? -1),
    queryFn: () =>
      api.get<TelemetrySeries>(`/datasets/${encodeURIComponent(name)}/episodes/${String(index)}/telemetry`),
    enabled: index !== null,
  });

export const useModels = () =>
  useQuery({
    queryKey: qk.models,
    queryFn: () => api.get<{ models: ModelEntry[]; loaded: string | null }>("/models"),
  });

export const useCompat = (key: string | null, robot: string | null) =>
  useQuery({
    queryKey: qk.compat(key ?? "", robot ?? ""),
    queryFn: () =>
      api.get<CompatReport>(`/models/${encodeURIComponent(key ?? "")}/compat`, {
        query: { robot: robot ?? undefined },
      }),
    enabled: key !== null,
  });

export const useJobs = () => {
  const { store } = useRuntime();
  const q = useQuery({ queryKey: qk.jobs, queryFn: () => api.get<{ jobs: Job[] }>("/jobs") });
  useEffect(() => {
    for (const j of q.data?.jobs ?? []) store.setJob(j);
  }, [q.data, store]);
  return q;
};

export const useSessions = () =>
  useQuery({
    queryKey: qk.sessions,
    queryFn: () => api.get<{ sessions: SessionSummary[] }>("/sessions"),
  });

export const useServer = () =>
  useQuery({ queryKey: qk.server, queryFn: () => api.get<ServerLink>("/server") });

export const useServerDatasets = (enabled: boolean) =>
  useQuery({
    queryKey: qk.serverDatasets,
    queryFn: () => api.get<{ datasets: ServerDataset[] }>("/server/datasets"),
    enabled,
  });

export const useServerModels = (enabled: boolean) =>
  useQuery({
    queryKey: qk.serverModels,
    queryFn: () => api.get<{ models: ServerModel[] }>("/server/models"),
    enabled,
  });

export const useServerRuns = (datasetId: string | null) =>
  useQuery({
    queryKey: qk.serverRuns(datasetId ?? ""),
    queryFn: () => api.get<{ runs: ServerRun[] }>("/server/runs", { query: { dataset_id: datasetId ?? "" } }),
    enabled: datasetId !== null,
  });

function isStatus(v: unknown): v is Status {
  return typeof v === "object" && v !== null && "state" in v && "station" in v;
}

function isProgramState(v: unknown): v is ProgramState {
  return typeof v === "object" && v !== null && "run_id" in v && "program_id" in v && "variables" in v;
}

function isJob(v: unknown): v is Job {
  return typeof v === "object" && v !== null && "kind" in v && "status" in v && "progress" in v;
}

/**
 * Mutation that mirrors Status / Job responses into the live store and invalidates queries.
 * Hardware commands answer once the owner accepted the transition (§5.1), so the returned
 * Status is already the new state.
 */
export function useStationMutation<TVars, TRes>(
  fn: (vars: TVars) => Promise<TRes>,
  invalidate: QueryKey[] = [],
) {
  const qc = useQueryClient();
  const { store } = useRuntime();
  return useMutation({
    mutationFn: fn,
    onSuccess: (res) => {
      if (isStatus(res)) {
        store.setStatus(res);
        qc.setQueryData(qk.status, res);
      } else if (isJob(res)) store.setJob(res);
      else if (isProgramState(res)) store.setProgram(res);
      else if (res && typeof res === "object" && "kind" in res && "controls" in res)
        store.setSession(res as unknown as Session);
      for (const key of invalidate) void qc.invalidateQueries({ queryKey: key });
    },
  });
}

// ------------------------------------------------------------------ trajectories, poses, detectors, programs
const enc = encodeURIComponent;

export const useTrajectories = () =>
  useQuery({
    queryKey: qk.trajectories,
    queryFn: () => api.get<{ trajectories: TrajectorySummary[] }>("/trajectories"),
  });

export const useTrajectory = (id: string | null) =>
  useQuery({
    queryKey: qk.trajectory(id ?? ""),
    queryFn: () => api.get<TrajectoryDetail>(`/trajectories/${enc(id ?? "")}`),
    enabled: id !== null,
  });

export const usePoses = () =>
  useQuery({ queryKey: qk.poses, queryFn: () => api.get<{ poses: Pose[] }>("/poses") });

export const useDetectors = () =>
  useQuery({ queryKey: qk.detectors, queryFn: () => api.get<{ detectors: Detector[] }>("/detectors") });

export const useSignals = () =>
  useQuery({ queryKey: qk.signals, queryFn: () => api.get<{ signals: Signal[] }>("/signals") });

/** The block catalogue never changes while Station runs. */
export const useBlockCatalog = () =>
  useQuery({
    queryKey: qk.blocks,
    queryFn: () => api.get<BlockCatalog>("/programs/blocks"),
    staleTime: Infinity,
  });

export const usePrograms = () =>
  useQuery({ queryKey: qk.programs, queryFn: () => api.get<{ programs: ProgramSummary[] }>("/programs") });

export const useProgram = (id: string | null) =>
  useQuery({
    queryKey: qk.program(id ?? ""),
    queryFn: () => api.get<Program>(`/programs/${enc(id ?? "")}`),
    enabled: id !== null,
  });

export const useProgramRuns = (id: string | null) =>
  useQuery({
    queryKey: qk.programRuns(id ?? ""),
    queryFn: () => api.get<{ runs: ProgramRunSummary[] }>(`/programs/${enc(id ?? "")}/runs`),
    enabled: id !== null,
  });

export const useProgramRun = (id: string | null, runId: string | null) =>
  useQuery({
    queryKey: qk.programRun(id ?? "", runId ?? ""),
    queryFn: () => api.get<ProgramRunLog>(`/programs/${enc(id ?? "")}/runs/${enc(runId ?? "")}`),
    enabled: id !== null && runId !== null,
  });

/** The current run of a program (also mirrored into the live store; the WS keeps it fresh). */
export function useProgramStateQuery(id: string | null) {
  const { store } = useRuntime();
  const q = useQuery({
    queryKey: qk.programState(id ?? ""),
    queryFn: () => api.get<ProgramState>(`/programs/${enc(id ?? "")}/state`),
    enabled: id !== null,
    retry: false,
  });
  useEffect(() => {
    if (q.data) store.setProgram(q.data);
  }, [q.data, store]);
  return q;
}
