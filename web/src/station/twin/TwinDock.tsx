/**
 * Shell placement of the twin when the page has none inline: a collapsible right-hand dock next to
 * the e-stop on desktop (≥ 1024 px), a "Robot 3D" section under the page on narrow screens. The
 * open/closed choice is remembered per viewer (try/catch localStorage via `prefs`). Collapsed
 * means unmounted, so no WebGL context and no rendering.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PxIcon } from "@/hibiscus/PixelAnim";
import { prefs } from "@/lib/utils";
import { RobotTwin } from "./RobotTwin";
import { useInlineTwinCount, useMediaQuery } from "./registry";

export const DESKTOP_QUERY = "(min-width: 1024px)";
const DOCK_KEY = "station.twin.dock";
const SECTION_KEY = "station.twin.section";

function usePersistedOpen(key: string, fallback: boolean): [boolean, (v: boolean) => void] {
  const [open, setOpen] = useState(() => {
    const v = prefs.get(key);
    return v === null ? fallback : v === "1";
  });
  return [
    open,
    (v: boolean) => {
      prefs.set(key, v ? "1" : "0");
      setOpen(v);
    },
  ];
}

/** Desktop dock: rendered by the shell as the right column. */
export function TwinDock() {
  const { t } = useTranslation("station");
  const desktop = useMediaQuery(DESKTOP_QUERY);
  const inline = useInlineTwinCount();
  const [open, setOpen] = usePersistedOpen(DOCK_KEY, true);
  if (!desktop || inline > 0) return null;
  if (!open) {
    return (
      <aside className="sticky top-[60px] h-[calc(100vh-60px)] shrink-0 border-l-4 border-frame bg-sidebar">
        <button
          type="button"
          className="flex h-full w-10 flex-col items-center gap-2 pt-3 text-sidebar-foreground hover:bg-accent"
          aria-label={t("twin.show")}
          aria-expanded={false}
          title={t("twin.show")}
          data-testid="twin-dock-toggle"
          onClick={() => {
            setOpen(true);
          }}
        >
          <PxIcon name="chevron_left" />
          <PxIcon name="robot" />
          <span className="font-extrabold text-xs [writing-mode:vertical-rl]">{t("twin.title")}</span>
        </button>
      </aside>
    );
  }
  return (
    <aside
      className="sticky top-[60px] flex h-[calc(100vh-60px)] w-72 shrink-0 flex-col gap-2 overflow-y-auto border-l-4 border-frame bg-sidebar p-3 pb-40 text-sidebar-foreground xl:w-80"
      data-testid="twin-dock"
    >
      <button
        type="button"
        className="flex items-center gap-1 self-end border-2 border-transparent px-1 text-xs font-bold hover:border-frame"
        aria-label={t("twin.hide")}
        aria-expanded
        data-testid="twin-dock-toggle"
        onClick={() => {
          setOpen(false);
        }}
      >
        {t("twin.hide")} <PxIcon name="chevron_right" />
      </button>
      <RobotTwin inline={false} canvasClassName="aspect-square" />
    </aside>
  );
}

/** Narrow screens: a collapsible "Robot 3D" section at the end of the page. */
export function TwinSection() {
  const { t } = useTranslation("station");
  const desktop = useMediaQuery(DESKTOP_QUERY);
  const inline = useInlineTwinCount();
  const [open, setOpen] = usePersistedOpen(SECTION_KEY, false);
  if (desktop || inline > 0) return null;
  return (
    <section className="px-panel-sm mt-4 bg-card p-2" data-testid="twin-section">
      <button
        type="button"
        className="flex w-full items-center gap-2 text-left font-extrabold"
        aria-expanded={open}
        onClick={() => {
          setOpen(!open);
        }}
      >
        <PxIcon name="robot" />
        <span className="flex-1">{t("twin.title")}</span>
        <PxIcon name={open ? "chevron_up" : "chevron_down"} />
        <span className="sr-only">{open ? t("twin.hide") : t("twin.show")}</span>
      </button>
      {open ? <RobotTwin inline={false} hideTitle className="mt-2" /> : null}
    </section>
  );
}
