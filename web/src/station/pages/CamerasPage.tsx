/**
 * Cameras (§6.4): discovered devices with a probe snapshot and measured fps, an add form, and the
 * configured cameras of the profile with live previews. Names are the dataset / policy keys.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/common";
import { Field } from "@/components/Field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { Alert } from "@/components/ui/misc";
import { api } from "../api/client";
import { qk, useDiscoverCameras, useRobots, useStationMutation } from "../api/hooks";
import type { CameraConfig, DiscoveredCamera, ProbeResult, RobotProfile } from "../api/types";
import { CameraTile } from "../components/CameraGrid";
import { StationError } from "../components/StationError";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { useStatus } from "../ws/StationProvider";

export const FPS_WARN_RATIO = 0.9;

function configFor(d: DiscoveredCamera): CameraConfig {
  const def = d.default ?? { width: 640, height: 480, fps: 30, fourcc: null };
  const base = {
    width: def.width,
    height: def.height,
    fps: def.fps,
    rotation: 0 as const,
    index_or_path: null,
    serial_number_or_name: null,
    fourcc: null,
  };
  if (d.type === "realsense") return { ...base, type: "realsense", serial_number_or_name: d.id };
  if (d.type === "mock") return { ...base, type: "mock", index_or_path: d.id };
  return { ...base, type: "opencv", index_or_path: d.stable_path ?? d.id, fourcc: def.fourcc ?? "MJPG" };
}

/** lerobot's Cv2Rotation values; 270° is sent as -90. */
const ROTATIONS = [0, 90, 180, -90] as const;

function AddCamera({
  cam,
  profile,
  onDone,
}: {
  cam: DiscoveredCamera;
  profile: RobotProfile;
  onDone: () => void;
}) {
  const { t } = useTranslation("station");
  const [name, setName] = useState(Object.keys(profile.cameras).length === 0 ? "wrist" : "front");
  const [cfg, setCfg] = useState<CameraConfig>(configFor(cam));
  const probe = useStationMutation((c: CameraConfig) => api.post<ProbeResult>("/cameras/probe", c));
  const save = useStationMutation(
    (p: RobotProfile) => api.put<RobotProfile>(`/robots/${encodeURIComponent(p.id)}`, p),
    [qk.robots, qk.discover, qk.status],
  );
  const nameOk = /^[a-z][a-z0-9_]{0,31}$/.test(name) && !(name in profile.cameras);
  const slow = probe.data?.ok && probe.data.measured_fps < cfg.fps * FPS_WARN_RATIO;
  return (
    <div className="flex flex-col gap-3 border-t-2 border-frame/30 pt-3">
      <div className="grid gap-3 sm:grid-cols-3">
        <Field
          label={t("cameras.name")}
          description={t("cameras.name_hint")}
          {...(!nameOk && name ? { error: t("cameras.name_invalid") } : {})}
        >
          <Input
            value={name}
            onChange={(e) => {
              setName(e.target.value);
            }}
          />
        </Field>
        <Field label={t("cameras.resolution")}>
          <NativeSelect
            value={`${cfg.width}x${cfg.height}`}
            onChange={(e) => {
              const [w, h] = e.target.value.split("x").map(Number);
              setCfg({ ...cfg, width: w ?? 640, height: h ?? 480 });
            }}
          >
            {["320x240", "640x360", "640x480", "800x600", "1280x720", "1920x1080"].map((r) => (
              <option key={r} value={r}>
                {r.replace("x", "×")}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label={t("cameras.fps")}>
          <NativeSelect
            value={cfg.fps}
            onChange={(e) => {
              setCfg({ ...cfg, fps: Number(e.target.value) });
            }}
          >
            {[15, 30, 60].map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </NativeSelect>
        </Field>
        {cfg.type === "opencv" ? (
          <>
            <Field label={t("cameras.fourcc")}>
              <NativeSelect
                value={cfg.fourcc ?? "MJPG"}
                onChange={(e) => {
                  setCfg({ ...cfg, fourcc: e.target.value });
                }}
              >
                <option value="MJPG">MJPG</option>
                <option value="YUYV">YUYV</option>
              </NativeSelect>
            </Field>
            <Field label={t("cameras.rotation")}>
              <NativeSelect
                value={cfg.rotation}
                onChange={(e) => {
                  const r = ROTATIONS.find((x) => x === Number(e.target.value));
                  if (r !== undefined) setCfg({ ...cfg, rotation: r });
                }}
              >
                {ROTATIONS.map((r) => (
                  <option key={r} value={r}>
                    {r < 0 ? 360 + r : r}°
                  </option>
                ))}
              </NativeSelect>
            </Field>
          </>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          onClick={() => {
            probe.mutate(cfg);
          }}
          disabled={probe.isPending}
        >
          {t("cameras.probe")}
        </Button>
        <Button
          disabled={!nameOk || save.isPending}
          onClick={() => {
            save.mutate({ ...profile, cameras: { ...profile.cameras, [name]: cfg } }, { onSuccess: onDone });
          }}
        >
          {t("cameras.add")}
        </Button>
      </div>
      {probe.data ? (
        <div className="flex flex-wrap items-start gap-3" data-testid="probe-result">
          {probe.data.snapshot_jpeg_b64 ? (
            <img
              src={`data:image/jpeg;base64,${probe.data.snapshot_jpeg_b64}`}
              alt={t("cameras.snapshot_alt", { name: cam.name })}
              className="w-40 border-2 border-frame"
            />
          ) : null}
          <p className="text-sm">
            {probe.data.ok
              ? t("cameras.measured", {
                  fps: probe.data.measured_fps.toFixed(1),
                  w: probe.data.width,
                  h: probe.data.height,
                })
              : t("cameras.probe_failed")}
          </p>
        </div>
      ) : null}
      {slow ? <Alert variant="warning">{t("cameras.slow")}</Alert> : null}
      <StationError error={probe.error ?? save.error} />
    </div>
  );
}

export function CamerasPage() {
  const { t } = useTranslation("station");
  const status = useStatus();
  const robots = useRobots();
  const discover = useDiscoverCameras(Boolean(status?.robot?.connected));
  const profile = robots.data?.robots.find((r) => r.id === status?.robot?.id);
  const [adding, setAdding] = useState<string | null>(null);
  const remove = useStationMutation(
    (p: RobotProfile) => api.put<RobotProfile>(`/robots/${encodeURIComponent(p.id)}`, p),
    [qk.robots, qk.discover, qk.status],
  );
  if (!profile || !status?.robot?.connected) {
    return (
      <div>
        <PageHeader title={t("cameras.title")} description={t("cameras.desc")} />
        <p className="text-sm">
          {t("lock.connect_first")}{" "}
          <Link to="/robot" className="underline">
            {t("nav.robot")}
          </Link>
        </p>
      </div>
    );
  }
  const configured = Object.entries(profile.cameras);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("cameras.title")} description={t("cameras.desc")} />
      <Card>
        <CardHeader>
          <CardTitle>{t("cameras.configured")}</CardTitle>
          <CardDescription>{t("cameras.keys_hint")}</CardDescription>
        </CardHeader>
        <CardContent>
          {configured.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("camera.none")}</p>
          ) : null}
          <ul className="grid gap-3 sm:grid-cols-2">
            {configured.map(([name, c]) => (
              <li key={name} className="flex flex-col gap-1">
                <CameraTile name={name} cam={status.cameras.find((x) => x.name === name)} />
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                  <span className="font-mono">
                    observation.images.{name} · {c.width}×{c.height}@{c.fps}
                    {c.fourcc ? ` ${c.fourcc}` : ""}
                    {c.rotation ? ` ${c.rotation}°` : ""}
                  </span>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      const rest = Object.fromEntries(
                        Object.entries(profile.cameras).filter(([k]) => k !== name),
                      );
                      remove.mutate({ ...profile, cameras: rest });
                    }}
                  >
                    {t("common.remove")}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
          <StationError error={remove.error} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t("cameras.discovered")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Button variant="outline" size="sm" className="self-start" onClick={() => void discover.refetch()}>
            {t("cameras.rescan")}
          </Button>
          <StationError error={discover.error} />
          <ul className="flex flex-col gap-3">
            {(discover.data?.cameras ?? []).map((d) => (
              <li key={d.id} className="flex flex-col gap-2" data-testid={`discovered-${d.id}`}>
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <PxIcon name="camera" />
                  <span className="font-bold">{d.name}</span>
                  <Badge variant="outline">{d.type}</Badge>
                  <span className="break-all font-mono text-xs text-muted-foreground">
                    {d.stable_path ?? d.id}
                  </span>
                  <span className="text-xs">
                    {d.default ? `${d.default.width}×${d.default.height}@${d.default.fps}` : ""}
                  </span>
                  {d.in_use_by ? (
                    <Badge variant="secondary">{t("cameras.in_use", { name: d.in_use_by })}</Badge>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setAdding(adding === d.id ? null : d.id);
                      }}
                      aria-expanded={adding === d.id}
                    >
                      {t("cameras.add")}
                    </Button>
                  )}
                </div>
                {adding === d.id ? (
                  <AddCamera
                    cam={d}
                    profile={profile}
                    onDone={() => {
                      setAdding(null);
                    }}
                  />
                ) : null}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
