/**
 * Field report 0.2.8 against the mock Station: "Return to rest pose" after an interrupted motion,
 * "Align follower to leader" when teleop refuses a far leader, locked wizard steps that explain
 * themselves and disable their controls, "New program" that always opens its form, and leader
 * telemetry that is informational only.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/test/server";
import { stationBase } from "./api/client";
import type { MotorSample } from "./api/types";
import { motorLevel } from "./health";
import { advance, renderStation, settle, setupStation } from "./test/utils";

beforeEach(() => {
  vi.stubGlobal(
    "createImageBitmap",
    vi.fn(() => Promise.resolve({ width: 320, height: 240, close: vi.fn() })),
  );
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    () =>
      ({
        drawImage: vi.fn(),
        measureText: (s: string) => ({ width: s.length * 7 }),
        font: "",
      }) as unknown as CanvasRenderingContext2D,
  );
  return () => {
    vi.unstubAllGlobals();
  };
});

describe("Return to rest pose", () => {
  it("is offered after an e-stop ended a motion and the latch was reset, and runs to completion", async () => {
    const h = setupStation();
    const p = h.sim.profiles[0];
    if (p) p.follower.rest_pose = { "shoulder_pan.pos": 0, "shoulder_lift.pos": -90 };
    const user = userEvent.setup();
    renderStation("/teleop", h);
    await settle();
    await user.click(await screen.findByRole("button", { name: "Start teleop" }));
    await waitFor(() => {
      expect(h.sim.state).toBe("teleop");
    });
    h.sim.estop("user");
    await settle();
    expect(screen.queryByTestId("rest-banner")).toBeNull(); // not while the latch holds
    h.sim.estopReset();
    const banner = await screen.findByTestId("rest-banner");
    expect(banner).toHaveAttribute("data-phase", "offer");
    expect(banner).toHaveTextContent("The arm stopped in the middle of a motion.");
    await user.click(within(banner).getByRole("button", { name: "Return to rest pose" }));
    await waitFor(() => {
      expect(screen.getByTestId("rest-banner")).toHaveAttribute("data-phase", "moving");
    });
    expect(h.sim.state).toBe("playing");
    await advance(h.sim, 3.2);
    await waitFor(() => {
      expect(screen.queryByTestId("rest-banner")).toBeNull();
    });
    expect(h.sim.state).toBe("idle");
  });

  it("asks for a rest pose when the robot has none", async () => {
    const h = setupStation();
    renderStation("/teleop", h);
    await settle();
    h.sim.startSession("teleop", {});
    h.sim.estop("user");
    h.sim.estopReset();
    const banner = await screen.findByTestId("rest-banner");
    expect(banner).toHaveTextContent("Set a rest pose on the Robot page");
    expect(within(banner).queryByRole("button", { name: "Return to rest pose" })).toBeNull();
  });
});

describe("Align follower to leader", () => {
  it("offers to align when the leader is far, then starts teleop with align", async () => {
    const h = setupStation();
    const bodies: unknown[] = [];
    let first = true;
    server.use(
      http.post(`${stationBase()}/sessions/teleop`, async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        bodies.push(body);
        if (first) {
          first = false;
          return HttpResponse.json(
            {
              type: "x",
              title: "Conflict",
              status: 409,
              code: "leader_far",
              detail: "Move the leader arm closer to the follower pose first",
              request_id: "r",
              params: {
                joints: { shoulder_lift: 141.8, elbow_flex: 117.3 },
                max_deg: 30,
                can_align: true,
              },
            },
            { status: 409 },
          );
        }
        return HttpResponse.json(h.sim.startSession("teleop", body));
      }),
    );
    const user = userEvent.setup();
    renderStation("/teleop", h);
    await settle();
    await user.click(await screen.findByRole("button", { name: "Start teleop" }));
    const offer = await screen.findByTestId("align-offer");
    expect(screen.getByText(/shoulder_lift 141.8, elbow_flex 117.3/)).toBeInTheDocument();
    await user.click(within(offer).getByRole("button", { name: "Align follower to leader" }));
    await waitFor(() => {
      expect(h.sim.state).toBe("teleop");
    });
    expect(bodies[1]).toMatchObject({ align: true });
    expect(await screen.findByTestId("teleop-aligning")).toHaveTextContent("keep the leader still");
    await advance(h.sim, 2.2);
    await waitFor(() => {
      expect(screen.queryByTestId("teleop-aligning")).toBeNull();
    });
  });
});

describe("Locked steps", () => {
  it("a locked page says why and disables its controls (connect first)", async () => {
    const h = setupStation({ connected: false });
    renderStation("/teleop", h);
    await settle();
    const gate = await screen.findByTestId("lock-gate");
    expect(gate).toHaveAttribute("data-lock", "connect_first");
    expect(gate).toHaveTextContent("Connect a robot first.");
    expect(within(gate).getByRole("link", { name: /Go to Robot/ })).toHaveAttribute("href", "/robot");
    expect(screen.getByTestId("locked-content")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Start teleop" })).toBeDisabled();
  });

  it("an e-stop locks teleop without remounting it; the reset lifts the lock", async () => {
    const h = setupStation();
    renderStation("/teleop", h);
    await settle();
    expect(screen.queryByTestId("lock-gate")).toBeNull();
    h.sim.estop("user");
    expect(await screen.findByTestId("lock-gate")).toHaveAttribute("data-lock", "estopped");
    h.sim.estopReset();
    await waitFor(() => {
      expect(screen.queryByTestId("lock-gate")).toBeNull();
    });
    expect(screen.getByRole("button", { name: "Start teleop" })).toBeEnabled();
  });

  it("Train asks to pair first and keeps the pairing form usable", async () => {
    const h = setupStation();
    renderStation("/train", h);
    await settle();
    expect(await screen.findByTestId("lock-gate")).toHaveAttribute("data-lock", "pair_first");
    expect(screen.queryByTestId("locked-content")).toBeNull();
  });

  it("Upload says to record a dataset first", async () => {
    const h = setupStation({ datasets: [] });
    renderStation("/upload", h);
    await settle();
    const gate = await screen.findByTestId("lock-gate");
    expect(gate).toHaveAttribute("data-lock", "record_first");
    expect(within(gate).getByRole("link", { name: /Go to Record/ })).toHaveAttribute("href", "/record");
  });
});

describe("New program", () => {
  it("always opens the form and focuses the name, also with no program yet", async () => {
    const h = setupStation();
    h.sim.programs.programs = [];
    const user = userEvent.setup();
    renderStation("/programs?tab=programs", h);
    await settle();
    const form = await screen.findByTestId("new-program-form");
    const btn = screen.getByRole("button", { name: "New program" });
    await user.click(btn);
    await user.click(btn); // a second click never closes it (it used to toggle)
    expect(screen.getByTestId("new-program-form")).toBe(form);
    expect(within(form).getByRole("textbox")).toHaveFocus();
  });

  it("shows a failing program list with a retry, and the form still opens", async () => {
    const h = setupStation();
    let fail = true;
    server.use(
      http.get(`${stationBase()}/programs`, () =>
        fail
          ? HttpResponse.json(
              {
                type: "x",
                title: "Conflict",
                status: 409,
                code: "estopped",
                detail: "reset the e-stop first",
                request_id: "r",
              },
              { status: 409 },
            )
          : HttpResponse.json({ programs: [] }),
      ),
    );
    const user = userEvent.setup();
    renderStation("/programs?tab=programs", h);
    await settle();
    expect(await screen.findByTestId("programs-error")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New program" }));
    expect(screen.getByTestId("new-program-form")).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => {
      expect(screen.queryByTestId("programs-error")).toBeNull();
    });
  });
});

describe("Leader telemetry", () => {
  const sample: MotorSample = {
    temp_c: null,
    voltage_v: 5.3,
    current_a: null,
    load_pct: 0,
    status: ["overload"],
    level: "ok",
    stale: false,
  };
  it("never colours a leader motor critical from its status bits or load", () => {
    expect(motorLevel(sample, undefined, "leader")).toBe("ok");
    expect(motorLevel({ ...sample, load_pct: 99 }, undefined, "leader")).toBe("ok");
    expect(motorLevel({ ...sample, temp_c: 80 }, undefined, "leader")).toBe("hot");
    expect(motorLevel(sample)).toBe("critical"); // the follower keeps it
  });
});
