/**
 * Screen "Chương trình / Programs" (station-programs.md §8): three tabs, Trajectories, Detection and
 * Programs. The tab lives in the URL (`?tab=`), so a reload or a link opens the same tab.
 */
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/common";
import { Mascot } from "@/components/Mascot";
import { PixelAnim } from "@/hibiscus/PixelAnim";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useStation } from "../../ws/StationProvider";
import { DetectionTab } from "./DetectionTab";
import { ProgramTab } from "./ProgramTab";
import { programMood } from "./shared";
import { TrajectoriesTab } from "./TrajectoriesTab";

export const PROGRAM_TABS = ["trajectories", "detection", "programs"] as const;
export type ProgramTabName = (typeof PROGRAM_TABS)[number];

function isTab(v: string | null): v is ProgramTabName {
  return v !== null && (PROGRAM_TABS as readonly string[]).includes(v);
}

export function ProgramsPage() {
  const { t } = useTranslation("station");
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  const tab: ProgramTabName = isTab(raw) ? raw : "trajectories";
  const program = useStation((s) => s.program);
  const mood = programMood(program);
  return (
    <div className="flex flex-col gap-2">
      <PageHeader
        title={t("programs.title")}
        description={t("programs.desc")}
        actions={
          tab === "programs" ? null : <Mascot mood={mood} size="mini" label={t(`programs.mood.${mood}`)} />
        }
      />
      <Tabs
        value={tab}
        onValueChange={(v) => {
          setParams(
            (p) => {
              p.set("tab", v);
              return p;
            },
            { replace: true },
          );
        }}
      >
        <TabsList aria-label={t("programs.title")}>
          <TabsTrigger value="trajectories">
            <PixelAnim name="icon_robot_arm" /> {t("programs.tab_trajectories")}
          </TabsTrigger>
          <TabsTrigger value="detection">
            <PixelAnim name="icon_camera" /> {t("programs.tab_detection")}
          </TabsTrigger>
          <TabsTrigger value="programs">
            <PixelAnim name="icon_log" /> {t("programs.tab_programs")}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="trajectories">
          <TrajectoriesTab />
        </TabsContent>
        <TabsContent value="detection">
          <DetectionTab />
        </TabsContent>
        <TabsContent value="programs">
          <ProgramTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
