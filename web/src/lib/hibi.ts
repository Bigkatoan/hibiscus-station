import type { HibiMood } from "@/hibiscus/PixelAnim";

export type { HibiMood };

/** Every mood the synced Hibi (robot arm holding a hibiscus) is drawn in. */
export const HIBI_MOODS: readonly HibiMood[] = ["idle", "wave", "happy", "working", "sleep", "sad"];
