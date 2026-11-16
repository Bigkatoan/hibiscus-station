import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PxIcon, Sprite } from "@/hibiscus/PixelAnim";
import { ANIMS } from "@/hibiscus/sprites.gen";
import { HIBI_MOODS } from "@/lib/hibi";
import { Mascot } from "./Mascot";

describe("Hibi mascot (hibiscus-assets)", () => {
  it("has every mood drawn in both resolutions", () => {
    for (const m of HIBI_MOODS) {
      expect(Object.keys(ANIMS)).toContain(`hibi_${m}`);
      expect(Object.keys(ANIMS)).toContain(`hibi_mini_${m}`);
    }
  });

  it("draws the robot-arm Hibi strip at one art pixel = 2 CSS px", () => {
    const { container, rerender } = render(<Mascot mood="wave" label="Hibi" />);
    const hero = screen.getByRole("img", { name: "Hibi" });
    expect(hero).toHaveClass("px-anim");
    expect(hero.style.getPropertyValue("--src")).toBe("url(/pixel/anim/hibi_wave.png)");
    expect(container.querySelector("[data-hibi='wave']")).not.toBeNull();
    rerender(<Mascot mood="sad" size="mini" />);
    const mini = container.querySelector<HTMLElement>(".px-anim")!;
    expect(mini.style.getPropertyValue("--src")).toBe("url(/pixel/anim/hibi_mini_sad.png)");
    expect(mini).toHaveAttribute("aria-hidden", "true");
  });

  it("static sprites and glyphs have no per-use scale: 16×16 → 32 px, 8×8 → 16 px", () => {
    render(
      <>
        <Sprite name="icon_camera" alt="camera" />
        <PxIcon name="estop" label="stop" />
      </>,
    );
    const img = screen.getByRole("img", { name: "camera" });
    expect(img).toHaveAttribute("width", "32");
    expect(img).toHaveAttribute("height", "32");
    expect(img).toHaveClass("pixelated");
    const glyph = screen.getByRole("img", { name: "stop" });
    expect(glyph).toHaveAttribute("width", "16");
  });
});
