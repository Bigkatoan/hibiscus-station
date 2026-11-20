/**
 * Level 1 3D twin (kinematic display only, no physics): the SO-101 follower drawn from the joint
 * positions the control WebSocket streams (the mock arm under `--mock`, the real arm otherwise),
 * each motor housing coloured by its temperature level, and an optional translucent ghost arm
 * (trajectory preview). This wrapper is light; three.js loads lazily with TwinCanvas.
 */
import { lazy, Suspense, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { HomeControls } from "../components/HomeControls";
import { useThresholds } from "../components/MotorHealthPanel";
import { useStation } from "../ws/StationProvider";
import type { StationSnapshot } from "../ws/store";
import { levelColor, motorLevels, TWIN_JOINTS, type UrdfPose } from "./mapping";
import { useRegisterInlineTwin } from "./registry";
import { hasWebGL } from "./webgl";
import licenseUrl from "./so101/LICENSE.txt?url";
import noticeUrl from "./so101/NOTICE.txt?url";

const TwinCanvas = lazy(() => import("./TwinCanvas"));

const selFollower = (s: StationSnapshot) => s.telemetry.follower;
const selHasJoints = (s: StationSnapshot) => s.joints !== null;
const selMock = (s: StationSnapshot) => s.status?.station.mock ?? null;

export interface RobotTwinProps {
  /** Pose of the translucent ghost arm (URDF radians), or null for none. */
  ghost?: UrdfPose | null;
  /** Inline on a page (hides the shell dock while mounted). The dock itself passes false. */
  inline?: boolean;
  /** Heading level text; defaults to "Robot 3D". */
  title?: string;
  /** Keep the heading for screen readers only (the dock / section already says "Robot 3D"). */
  hideTitle?: boolean;
  /** Hide the per-motor temperature list (the dock shows it; small embeds may not). */
  legend?: boolean;
  className?: string | undefined;
  /** Classes of the canvas box (its height). */
  canvasClassName?: string | undefined;
  /** Extra controls under the canvas (ghost player). */
  children?: ReactNode;
  /** "Set Home at current position" / "Return Home" under the canvas (CR-2); off for previews. */
  home?: boolean;
}

export function RobotTwin({
  ghost = null,
  inline = true,
  title,
  hideTitle = false,
  legend = true,
  className,
  canvasClassName,
  children,
  home = ghost === null,
}: RobotTwinProps) {
  const { t } = useTranslation("station");
  const { resolved } = useTheme();
  const follower = useStation(selFollower);
  const hasJoints = useStation(selHasJoints);
  const mock = useStation(selMock);
  const th = useThresholds();
  const levels = useMemo(() => motorLevels(follower, th), [follower, th]);
  const [state, setState] = useState<"loading" | "ready" | "error" | "no-webgl">("loading");
  const [resetKey, setResetKey] = useState(0);
  // Probed once (a throwaway canvas, no three.js); a context that still fails later lands in
  // state "no-webgl" from the canvas, and the same note shows.
  const [probe] = useState(hasWebGL);
  const webgl = probe && state !== "no-webgl";
  useRegisterInlineTwin(inline);

  return (
    <section
      className={cn("flex min-w-0 flex-col gap-2", className)}
      aria-label={title ?? t("twin.title")}
      data-testid="robot-twin"
      data-state={webgl ? state : "no-webgl"}
    >
      <div className="flex items-center gap-2">
        <h3 className={cn("min-w-0 flex-1 truncate font-extrabold text-sm", hideTitle && "sr-only")}>
          {title ?? t("twin.title")}
        </h3>
        {hideTitle ? <span className="flex-1" /> : null}
        {mock !== null ? (
          <span className="border-2 border-frame/40 px-1 text-xs font-bold" data-testid="twin-source">
            {mock ? t("twin.source_mock") : t("twin.source_live")}
          </span>
        ) : null}
        {webgl ? (
          <button
            type="button"
            className="flex h-8 w-8 items-center justify-center border-2 border-transparent hover:border-frame"
            aria-label={t("twin.reset_view")}
            title={t("twin.reset_view")}
            onClick={() => {
              setResetKey((k) => k + 1);
            }}
          >
            <PxIcon name="refresh" />
          </button>
        ) : null}
      </div>
      {webgl ? (
        <div
          className={cn(
            "relative aspect-[4/3] w-full overflow-hidden border-2 border-frame bg-card",
            canvasClassName,
          )}
        >
          <Suspense fallback={null}>
            <TwinCanvas
              ghost={ghost}
              levels={levels}
              theme={resolved}
              resetKey={resetKey}
              label={t("twin.canvas_label")}
              onState={setState}
            />
          </Suspense>
          {state !== "ready" ? (
            <p
              className="pointer-events-none absolute inset-0 flex items-center justify-center p-2 text-center text-sm text-muted-foreground"
              role={state === "error" ? "alert" : "status"}
            >
              {state === "error" ? t("twin.error") : t("twin.loading")}
            </p>
          ) : null}
          {state === "ready" && !hasJoints ? (
            <p className="pointer-events-none absolute inset-x-0 top-0 p-1 text-center text-xs text-muted-foreground">
              {t("twin.rest_pose")}
            </p>
          ) : null}
        </div>
      ) : (
        <div
          className="px-panel-sm flex items-start gap-3 p-3 text-sm text-muted-foreground"
          role="note"
          data-testid="twin-no-webgl"
        >
          <PxIcon name="robot" className="mt-0.5 shrink-0 text-foreground" />
          <p className="min-w-0">{t("twin.no_webgl")}</p>
        </div>
      )}
      {children}
      {home ? <HomeControls /> : null}
      {legend && webgl ? (
        <div className="flex flex-col gap-1">
          <p className="text-xs text-muted-foreground">{t("twin.legend")}</p>
          <ul className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-xs tabular-nums" data-testid="twin-legend">
            {TWIN_JOINTS.map((j) => {
              const s = follower?.[j];
              const level = levels[j];
              const temp = s && !s.stale ? s.temp_c : null;
              return (
                <li
                  key={j}
                  className="flex min-w-0 items-center gap-1"
                  data-motor={j}
                  data-level={level ?? "unknown"}
                  title={
                    level && temp !== null
                      ? t("twin.motor_temp", { motor: j, temp, level: t(`level.${level}`) })
                      : t("twin.motor_unknown", { motor: j })
                  }
                >
                  <span
                    className="inline-block h-3 w-3 shrink-0 border-2 border-frame"
                    style={{ backgroundColor: levelColor(level) }}
                    aria-hidden
                  />
                  <span className="min-w-0 flex-1 truncate">{j}</span>
                  <span className={cn(level === "hot" || level === "critical" ? "font-extrabold" : "")}>
                    {temp !== null ? `${temp}°` : "–"}
                  </span>
                  <span className="sr-only">{level ? t(`level.${level}`) : ""}</span>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
      <p className="text-[11px] leading-tight text-muted-foreground">
        <a href={noticeUrl} target="_blank" rel="noreferrer" className="underline">
          {t("twin.credit")}
        </a>{" "}
        (
        <a href={licenseUrl} target="_blank" rel="noreferrer" className="underline">
          LICENSE
        </a>
        )
      </p>
    </section>
  );
}
