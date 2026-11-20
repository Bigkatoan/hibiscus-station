import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useSyncExternalStore, type ReactNode } from "react";
import { api, stationWsUrl } from "../api/client";
import { qk } from "../api/hooks";
import type { Job, Status } from "../api/types";
import { ControlSocket, browserSocket, type SocketFactory } from "./control";
import { StationStore, type StationSnapshot } from "./store";
import { VideoHub } from "./video";

export interface StationRuntime {
  store: StationStore;
  control: ControlSocket;
  video: VideoHub;
}

const Ctx = createContext<StationRuntime | null>(null);

export function createRuntime(factory: SocketFactory = browserSocket): StationRuntime {
  const store = new StationStore();
  const control = new ControlSocket(stationWsUrl("/ws"), store, factory, () => {
    // §5.2: the UI reloads the full snapshot on load and after every WS reconnect.
    api
      .get<Status>("/status")
      .then((s) => {
        store.setStatus(s);
      })
      .catch(() => undefined);
  });
  const video = new VideoHub(stationWsUrl("/ws/video"), factory);
  return { store, control, video };
}

/** REST caches a finished job or session changes (jobs and sessions end over the WS, §5.3). */
function jobInvalidates(kind: Job["kind"]): readonly (readonly string[])[] {
  return kind === "upload" ? [qk.datasets] : [qk.models]; // import, pull, load
}

export function StationProvider({ runtime, children }: { runtime: StationRuntime; children: ReactNode }) {
  const client = useQueryClient();
  useEffect(() => {
    runtime.control.start();
    return () => {
      runtime.control.stop();
      runtime.video.close();
    };
  }, [runtime]);
  useEffect(() => {
    const done = new Set<string>();
    let hadSession = false;
    return runtime.store.subscribe(() => {
      const snap = runtime.store.getSnapshot();
      for (const job of Object.values(snap.jobs)) {
        if (done.has(job.id) || job.status === "queued" || job.status === "running") continue;
        done.add(job.id);
        for (const key of jobInvalidates(job.kind)) void client.invalidateQueries({ queryKey: key });
      }
      const hasSession = Boolean(snap.status?.session);
      if (hadSession && !hasSession) {
        // The list refetches now; one dataset's detail only when it is next shown. A session that
        // kept no episode removed its new dataset, and a page still showing it (the record strip,
        // unmounting) must not ask for it again (QC 0.2.9 QD-18: a 404 in the console).
        void client.invalidateQueries({ queryKey: qk.datasets, exact: true });
        void client.invalidateQueries({ queryKey: qk.datasets, refetchType: "none" });
        void client.invalidateQueries({ queryKey: qk.sessions });
      }
      hadSession = hasSession;
    });
  }, [runtime, client]);
  return <Ctx.Provider value={runtime}>{children}</Ctx.Provider>;
}

export function useRuntime(): StationRuntime {
  const rt = useContext(Ctx);
  if (!rt) throw new Error("useRuntime must be used inside StationProvider");
  return rt;
}

/** Subscribe to one slice of the live snapshot. The selector must return stored references. */
export function useStation<T>(select: (s: StationSnapshot) => T): T {
  const { store } = useRuntime();
  return useSyncExternalStore(store.subscribe, () => select(store.getSnapshot()));
}

export function useStatus(): Status | null {
  return useStation((s) => s.status);
}

export function useStationState(): Status["state"] | null {
  return useStation((s) => s.status?.state ?? null);
}

/** Memoised list of moving joints from the latest joint message. */
export function useJointNames(): string[] {
  const joints = useStation((s) => s.joints);
  return useMemo(
    () => Object.keys(joints?.arms.follower ?? {}).map((k) => (k.endsWith(".pos") ? k.slice(0, -4) : k)),
    [joints?.arms.follower],
  );
}
