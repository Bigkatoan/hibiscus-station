/**
 * D-26 (customer report 2026-11-20, F-8 "robot profile: create / edit / delete"): the Robot page
 * had no way to remove a duplicate profile. Each card has Delete, with a confirmation that names
 * the profile and says calibration files and datasets stay; the connected one says why it cannot.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { i18n } from "@/lib/i18n";
import type { RobotProfile } from "./api/types";
import * as fx from "./mock/fixtures";
import { renderStation, settle, setupStation } from "./test/utils";

afterEach(async () => {
  await i18n.changeLanguage("en");
});

function three(): RobotProfile[] {
  const dup: RobotProfile = { ...structuredClone(fx.robot), id: "so-101-1", name: "so-101-1" };
  const demo: RobotProfile = {
    ...structuredClone(fx.robot),
    id: "demo_so101",
    name: "Demo SO-101 (mock)",
    follower: { ...fx.robot.follower, type: "hibiscus_mock_follower", port: "mock://follower" },
  };
  return [demo, dup, structuredClone(fx.robot)];
}

/** The card of the profile named `name`. */
async function card(name: string): Promise<HTMLElement> {
  const title = await screen.findByText(name, { selector: "span" });
  const li = title.closest("li");
  if (!li) throw new Error(`no card ${name}`);
  return li;
}

describe("Robot: delete a profile (D-26)", () => {
  it("asks, names the profile, deletes it, and keeps the others", async () => {
    const h = setupStation();
    h.sim.profiles = three();
    const user = userEvent.setup();
    renderStation("/robot", h);
    await settle();
    await user.click(within(await card("so-101-1")).getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Delete robot profile so-101-1?");
    expect(dialog).toHaveTextContent("Calibration files and datasets are not deleted.");
    await user.click(within(dialog).getByRole("button", { name: "Delete profile" }));
    await waitFor(() => {
      expect(screen.queryByText("so-101-1", { selector: "span" })).not.toBeInTheDocument();
    });
    expect(h.sim.profiles.map((p) => p.id)).toEqual(["demo_so101", "desk_so101"]);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("Cancel keeps the profile", async () => {
    const h = setupStation();
    h.sim.profiles = three();
    const user = userEvent.setup();
    renderStation("/robot", h);
    await settle();
    await user.click(within(await card("Demo SO-101 (mock)")).getByRole("button", { name: "Delete" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(h.sim.profiles).toHaveLength(3);
  });

  it("the connected profile cannot be deleted and says why, in Vietnamese too", async () => {
    const h = setupStation(); // connected to desk_so101
    h.sim.profiles = three();
    renderStation("/robot", h);
    await settle();
    const conn = await card("Desk SO-101");
    await waitFor(() => {
      expect(within(conn).getByRole("button", { name: "Delete" })).toBeDisabled();
    });
    expect(conn).toHaveTextContent("Disconnect before deleting");
    expect(within(await card("so-101-1")).getByRole("button", { name: "Delete" })).toBeEnabled();
    await i18n.changeLanguage("vi");
    await waitFor(() => {
      expect(conn).toHaveTextContent("Ngắt kết nối trước khi xoá");
    });
    const user = userEvent.setup();
    await user.click(within(await card("so-101-1")).getByRole("button", { name: "Xoá" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Xoá hồ sơ robot so-101-1?");
    expect(dialog).toHaveTextContent("Tệp hiệu chỉnh và bộ dữ liệu không bị xoá.");
  });

  it("deleting the last profile leaves the page usable", async () => {
    const h = setupStation({ connected: false });
    h.sim.profiles = [structuredClone(fx.robot)];
    const user = userEvent.setup();
    renderStation("/robot", h);
    await settle();
    await user.click(within(await card("Desk SO-101")).getByRole("button", { name: "Delete" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete profile" }),
    );
    expect(await screen.findByText("No robot yet. Create one to start.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New robot" })).toBeEnabled();
  });
});
