/**
 * Station shell (§6.0): top bar (robot chip with Hibi mood, motor-health chip → health drawer,
 * server chip, language/theme), wizard rail with prerequisites, banners and the e-stop dock.
 */
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import type { HibiMood } from "@/lib/hibi";
import { Garden, PixelAnim, PxIcon, Sprite } from "@/hibiscus/PixelAnim";
import type { AnimName, SpriteName } from "@/hibiscus/sprites.gen";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { setLanguage } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { useDatasets, useModels, useRobots, useStatusQuery } from "./api/hooks";
import type { Level, Status } from "./api/types";
import { SafetyBanners } from "./components/Banners";
import { EStopButton } from "./components/EStopButton";
import { HomeControls } from "./components/HomeControls";
import { MotorHealthPanel, useThresholds } from "./components/MotorHealthPanel";
import { serverText } from "./components/ServerText";
import { levelCss, motorLevel, worstLevel } from "./health";
import { TwinDock, TwinSection } from "./twin/TwinDock";
import { useStation } from "./ws/StationProvider";
import type { StationSnapshot } from "./ws/store";

export function hibiMood(status: Status | null): HibiMood | "hot" {
  if (!status) return "sleep";
  if (status.health.level === "warn" || status.health.level === "hot" || status.health.level === "critical")
    return status.state === "estopped" ? "sad" : "hot";
  switch (status.state) {
    case "disconnected":
      return "sleep";
    case "estopped":
    case "error":
      return "sad";
    case "idle":
    case "connecting":
    case "stopping":
      return "idle";
    case "programming":
      // programs §8: Hibi sleeps while the program waits for a condition (wait, wait until, ask).
      return status.sub === "waiting" || status.sub === "paused" ? "sleep" : "working";
    default:
      return "working";
  }
}

/** The garden's mini Hibi: "hot" becomes the wilting (sad) mood. */
function gardenMood(status: Status | null): HibiMood {
  const m = hibiMood(status);
  return m === "hot" ? "sad" : m;
}

export interface Step {
  to: string;
  key: string;
  icon: AnimName;
  done: boolean;
  lock: string | null;
  /** The exact reason behind the lock, from the Station (missing calibration file, bus error...). */
  why?: string | null;
  /**
   * Not a lock: what to do first on the step's own page (field report 0.2.9, D-25: Train only needs
   * a Hibiscus server, no robot, and the pairing form is on the page). Key under `step_hint.`.
   */
  hint?: string | null;
}

export function wizardSteps(
  status: Status | null,
  info: { robots: number; datasets: { episodes: number; uploaded: boolean }[]; models: number },
): Step[] {
  const robot = status?.robot ?? null;
  const connected = Boolean(robot?.connected);
  const follower = robot?.arms.follower;
  const leader = robot?.arms.leader;
  const calibrated = Boolean(follower?.calibrated) && (!leader || leader.calibrated);
  const needConnect = connected ? null : "connect_first";
  const needCal = needConnect ?? (follower?.calibrated ? null : "calibrate_first");
  const needLeader = needCal ?? (leader ? (leader.calibrated ? null : "calibrate_leader") : "needs_leader");
  const estopped = status?.state === "estopped" ? "estopped" : null;
  const whyOf = (lock: string | null): string | null => {
    if (lock === "connect_first") return status?.state === "error" ? (status.detail ?? null) : null;
    if (lock === "calibrate_first") return follower?.issue ?? null;
    if (lock === "calibrate_leader") return leader?.issue ?? null;
    if (lock === "estopped") return status?.detail ?? null;
    return null;
  };
  const recorded = info.datasets.some((d) => d.episodes > 0);
  return [
    { to: "/robot", key: "robot", icon: "icon_robot_arm", done: info.robots > 0, lock: null },
    {
      to: "/calibrate",
      key: "calibrate",
      icon: "icon_calibrate",
      done: connected && calibrated,
      lock: needConnect ?? estopped,
      why: whyOf(needConnect ?? estopped),
    },
    {
      to: "/cameras",
      key: "cameras",
      icon: "icon_camera",
      done: (status?.cameras ?? []).some((c) => c.streaming),
      lock: needConnect,
      why: whyOf(needConnect),
    },
    {
      to: "/teleop",
      key: "teleop",
      icon: "icon_teleop",
      done: false,
      lock: needLeader ?? estopped,
      why: whyOf(needLeader ?? estopped),
    },
    {
      to: "/record",
      key: "record",
      icon: "icon_dataset",
      done: recorded,
      lock: needLeader ?? estopped,
      why: whyOf(needLeader ?? estopped),
    },
    {
      to: "/upload",
      key: "upload",
      icon: "icon_upload",
      done: info.datasets.some((d) => d.uploaded),
      lock: recorded ? null : "record_first",
    },
    {
      to: "/train",
      key: "train",
      icon: "icon_train",
      done: false,
      lock: null,
      hint: status?.server.paired ? null : "pair_server",
    },
    {
      to: "/run",
      key: "run",
      icon: "icon_model",
      done: info.models > 0,
      lock: needCal ?? estopped,
      why: whyOf(needCal ?? estopped),
    },
  ];
}

const EXTRA: { to: string; key: string }[] = [
  { to: "/programs", key: "programs" },
  { to: "/datasets", key: "datasets" },
  { to: "/models", key: "models" },
  { to: "/sessions", key: "sessions" },
  { to: "/settings", key: "settings" },
];

function WizardRail({ steps, onNavigate }: { steps: Step[]; onNavigate?: () => void }) {
  const { t, i18n } = useTranslation("station");
  // The rail says the Station's reason only in words; an unknown line is on the step's page,
  // behind "Technical details" (QC 0.2.9 QD-19).
  const why = (s: Step): string | null => serverText(t, s.why, i18n.language).text;
  return (
    <nav aria-label={t("nav.wizard")} className="flex gap-1 overflow-x-auto md:flex-col md:overflow-visible">
      <ol className="flex gap-1 md:flex-col">
        {steps.map((s, i) => (
          <li key={s.key} className="shrink-0">
            <NavLink
              to={s.to}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  "px-hover flex items-center gap-2 border-2 border-transparent px-2 py-1 text-sm hover:border-frame",
                  isActive && "border-frame bg-card font-bold",
                  s.lock && "opacity-70",
                )
              }
              title={
                s.lock
                  ? [t(`lock.${s.lock}`), why(s)].filter(Boolean).join(" — ")
                  : s.hint
                    ? t(`step_hint.${s.hint}`)
                    : undefined
              }
            >
              <span className="w-4 text-right tabular-nums text-xs text-muted-foreground">{i + 1}</span>
              <PixelAnim name={s.icon} />
              <span className="whitespace-nowrap">{t(`nav.${s.key}`)}</span>
              {s.done ? <PxIcon name="check" className="text-success" label={t("nav.done")} /> : null}
              {s.lock ? <PxIcon name="lock" /> : null}
            </NavLink>
            {s.lock ? (
              <p className="hidden pl-8 text-xs text-muted-foreground md:block">{t(`lock.${s.lock}`)}</p>
            ) : s.hint ? (
              <p
                className="hidden pl-8 text-xs text-muted-foreground md:block"
                data-testid={`step-hint-${s.key}`}
              >
                {t(`step_hint.${s.hint}`)}
              </p>
            ) : null}
            {s.lock && why(s) ? (
              <p
                className="hidden max-w-[16rem] break-words pl-8 text-[11px] leading-tight text-muted-foreground md:line-clamp-4"
                data-testid={`lock-why-${s.key}`}
              >
                {why(s)}
              </p>
            ) : null}
          </li>
        ))}
      </ol>
      <ul className="flex gap-1 border-frame/40 md:mt-3 md:flex-col md:border-t-2 md:pt-3">
        {EXTRA.map((x) => (
          <li key={x.key} className="shrink-0">
            <NavLink
              to={x.to}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  "block whitespace-nowrap border-2 border-transparent px-2 py-1 text-sm hover:border-frame",
                  isActive && "border-frame bg-card font-bold",
                )
              }
            >
              {t(`nav.${x.key}`)}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

const selTelemetry = (s: StationSnapshot) => s.telemetry;
const selStatus = (s: StationSnapshot) => s.status;

/** Hottest motor across arms, from live telemetry (falls back to the status snapshot). */
export function useHottest(): { level: Level; motor: string | null; temp: number | null } {
  const telemetry = useStation(selTelemetry);
  const status = useStation(selStatus);
  const th = useThresholds();
  return useMemo(() => {
    let best: { level: Level; motor: string | null; temp: number | null } = {
      level: "ok",
      motor: null,
      temp: null,
    };
    for (const motors of Object.values(telemetry)) {
      for (const [m, s] of Object.entries(motors)) {
        if (s.temp_c !== null && (best.temp === null || s.temp_c > best.temp))
          best = { level: best.level, motor: m, temp: s.temp_c };
      }
    }
    const levels = Object.entries(telemetry).flatMap(([arm, motors]) =>
      Object.values(motors).map((s) => motorLevel(s, th, arm === "leader" ? "leader" : "follower")),
    );
    const level = worstLevel([...levels, status?.health.level ?? "ok"]);
    if (best.motor === null && status?.health.hottest)
      return { level, motor: status.health.hottest.motor, temp: status.health.hottest.temp_c };
    return { ...best, level };
  }, [telemetry, status, th]);
}

function HealthChip() {
  const { t } = useTranslation("station");
  const hot = useHottest();
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => {
          setOpen(true);
        }}
        className="flex h-9 items-center gap-1 border-2 px-2 tabular-nums text-sm"
        style={levelCss(hot.level)}
        data-testid="health-chip"
        data-level={hot.level}
        aria-label={t("health.chip", {
          motor: hot.motor ?? "–",
          temp: hot.temp ?? "–",
          level: t(`level.${hot.level}`),
        })}
      >
        <PxIcon name="thermo" />
        <span className="hidden sm:inline">{hot.motor ?? t("health.title")}</span>
        <span>{hot.temp !== null ? `${hot.temp}°C` : "–"}</span>
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t("health.drawer_title")}</DialogTitle>
            <DialogDescription>{t("health.drawer_desc")}</DialogDescription>
          </DialogHeader>
          <MotorHealthPanel variant="large" />
        </DialogContent>
      </Dialog>
    </>
  );
}

/** The robot chip is 32 px tall, so it shows a 16×16 state icon (the mascot lives on the pages). */
const CHIP_SPRITE: Record<HibiMood | "hot", SpriteName> = {
  idle: "icon_robot_arm",
  wave: "icon_robot_arm",
  working: "icon_robot_arm",
  happy: "icon_heart",
  sleep: "icon_plug",
  sad: "icon_warning",
  hot: "icon_thermo_hot",
};

function TopBar() {
  const { t, i18n } = useTranslation("station");
  const status = useStation(selStatus);
  const { preference, setPreference } = useTheme();
  const mood = hibiMood(status);
  const nextTheme = preference === "light" ? "dark" : preference === "dark" ? "system" : "light";
  const themeGlyph = preference === "light" ? "sun" : preference === "dark" ? "moon" : "theme_auto";
  return (
    <header className="sticky top-0 z-40 border-b-4 border-frame bg-header text-header-foreground">
      <div className="flex h-14 items-center gap-2 px-2 sm:px-4">
        <Link to="/" className="px-hover flex shrink-0 items-center gap-2" aria-label="Hibiscus Station">
          <PixelAnim name="hibiscus_sparkle" />
          <span className="hidden text-xl font-extrabold sm:inline">Hibiscus</span>
          <span className="hidden text-base font-extrabold text-[#9bd35a] md:inline">{t("app.station")}</span>
        </Link>
        <div className="ml-auto flex min-w-0 items-center gap-1 sm:gap-2">
          <HomeControls compact className="hidden flex-nowrap sm:flex" />
          <Link
            to="/robot"
            className="flex h-9 min-w-0 items-center gap-1 border-2 border-[#c99a62] dark:border-[#4f5a80] px-1 text-sm"
            data-testid="robot-chip"
            aria-label={t("chip.robot", {
              robot: status?.robot?.id ?? t("chip.no_robot"),
              state: t(`state.${status?.state ?? "disconnected"}`),
            })}
          >
            <span className="flex shrink-0" data-mood={mood}>
              <Sprite name={CHIP_SPRITE[mood]} />
            </span>
            <span className="hidden max-w-[8rem] truncate md:inline">
              {status?.robot?.id ?? t("chip.no_robot")}
            </span>
            <span className="truncate font-extrabold">
              {status?.session?.kind === "rest"
                ? t("state_rest")
                : t(`state.${status?.state ?? "disconnected"}`)}
            </span>
          </Link>
          {status?.robot?.mock || status?.station.mock ? (
            <Link
              to="/robot"
              className="flex h-9 shrink-0 items-center border-2 border-[#f08a24] bg-[#ffc531] px-2 text-xs font-extrabold text-[#3b2027]"
              data-testid="demo-chip"
              title={t("demo.chip_title")}
            >
              {t("demo.chip")}
            </Link>
          ) : null}
          <HealthChip />
          <Link
            to="/settings"
            className="hidden h-9 items-center border-2 border-[#c99a62] dark:border-[#4f5a80] px-2 text-sm lg:flex"
            data-testid="server-chip"
          >
            {status?.server.paired
              ? t("chip.server", { ws: status.server.workspace ?? "" })
              : t("chip.offline")}
          </Link>
          <button
            type="button"
            className="flex h-9 w-9 items-center justify-center border-2 border-transparent hover:border-[#c99a62] dark:hover:border-[#4f5a80]"
            aria-label={t("chip.language")}
            onClick={() => {
              setLanguage(i18n.language === "vi" ? "en" : "vi");
            }}
          >
            <PxIcon name="language" />
            <span className="sr-only">{i18n.language}</span>
          </button>
          <button
            type="button"
            className="flex h-9 w-9 items-center justify-center border-2 border-transparent hover:border-[#c99a62] dark:hover:border-[#4f5a80]"
            aria-label={t("chip.theme", { mode: t(`theme.${preference}`) })}
            onClick={() => {
              setPreference(nextTheme);
            }}
          >
            <PxIcon name={themeGlyph} />
          </button>
        </div>
      </div>
    </header>
  );
}

/** The wizard steps from the live status and the robots / datasets / models queries. `ready` is
 * false until the status and the datasets are known (no lock flashes while a page loads). */
export function useWizardSteps(): { steps: Step[]; ready: boolean } {
  const status = useStation(selStatus);
  const robots = useRobots();
  const datasets = useDatasets();
  const models = useModels();
  const steps = wizardSteps(status, {
    robots: robots.data?.robots.length ?? 0,
    datasets: (datasets.data?.datasets ?? []).map((d) => ({
      episodes: d.episodes,
      uploaded: d.uploaded !== null,
    })),
    models: models.data?.models.length ?? 0,
  });
  return { steps, ready: status !== null && !datasets.isPending };
}

export function StationShell() {
  const { t } = useTranslation("station");
  useStatusQuery();
  const status = useStation(selStatus);
  const loc = useLocation();
  const { steps } = useWizardSteps();
  return (
    <div className="min-h-screen">
      <a
        href="#station-main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
      >
        {t("nav.skip")}
      </a>
      <TopBar />
      <div className="md:flex">
        <aside className="border-b-4 border-frame bg-sidebar text-sidebar-foreground md:sticky md:top-[60px] md:flex md:h-[calc(100vh-60px)] md:w-60 md:shrink-0 md:flex-col md:border-b-0 md:border-r-4">
          <div className="p-2 md:min-h-0 md:flex-1 md:overflow-y-auto md:p-3">
            <WizardRail steps={steps} />
          </div>
          <div className="hidden md:block">
            <Garden mood={gardenMood(status)} />
          </div>
        </aside>
        <main
          id="station-main"
          tabIndex={-1}
          className="min-w-0 flex-1 p-4 pb-40 sm:p-6 sm:pb-40 lg:p-8 lg:pb-40"
        >
          <div className="mb-4">
            <SafetyBanners />
          </div>
          <Outlet />
          <TwinSection />
        </main>
        <TwinDock />
      </div>
      <EStopButton size={loc.pathname.startsWith("/run") ? 128 : 96} />
    </div>
  );
}
