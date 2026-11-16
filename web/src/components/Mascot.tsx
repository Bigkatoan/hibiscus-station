import { Hibi, type HibiMood } from "@/hibiscus/PixelAnim";
import { cn } from "@/lib/utils";

export interface MascotProps {
  mood?: HibiMood;
  /** hero = 48×48 art (96 px, login / big empty states), mini = 24×24 art (48 px). */
  size?: "hero" | "mini";
  /** Accessible description; decorative when omitted. */
  label?: string;
  className?: string;
}

/**
 * Hibi, the Hibiscus mascot (a robot arm holding a hibiscus), from the synced design system.
 * The wrapper only adds `data-hibi` so tests and screenshots can tell which mood is shown.
 * Keep it to one looping mascot per screen (plus the sidebar garden).
 */
export function Mascot({ mood = "idle", size = "hero", label, className }: MascotProps) {
  return (
    <span className={cn("inline-flex shrink-0", className)} data-hibi={mood}>
      <Hibi mood={mood} size={size} {...(label ? { label } : {})} />
    </span>
  );
}
