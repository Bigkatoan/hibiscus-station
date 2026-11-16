import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/test/server";
import { stationBase } from "./api/client";
import { advance, renderStation, settle, setupStation, type StationHarness } from "./test/utils";

beforeEach(() => {
  vi.stubGlobal(
    "createImageBitmap",
    vi.fn(() => Promise.resolve({ width: 320, height: 240, close: vi.fn() })),
  );
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    () => ({ drawImage: vi.fn() }) as unknown as CanvasRenderingContext2D,
  );
  return () => {
    vi.unstubAllGlobals();
  };
});

async function startRunViaUi(h: StationHarness) {
  const user = userEvent.setup();
  renderStation("/run", h);
  await settle();
  await user.click(await screen.findByRole("button", { name: /picknplace ACT/ }));
  await user.click(await screen.findByRole("button", { name: "Load" }));
  await advance(h.sim, 2.5);
  await screen.findByTestId("load-result");
  const start = await screen.findByRole("button", { name: "Run on the robot" });
  await waitFor(() => {
    expect(start).toBeEnabled();
  });
  await user.click(start);
  await waitFor(() => {
    expect(h.sim.state).toBe("inferring");
  });
  return user;
}

describe("Run model (R2)", () => {
  it("shows every configured camera as policy input while the model runs, with joints vs commands and health", async () => {
    const h = setupStation({ paired: true });
    await startRunViaUi(h);
    await advance(h.sim, 3.2); // countdown → episode
    await screen.findByTestId("camera-grid");
    for (const cam of ["wrist", "front"]) {
      const tile = screen.getByTestId(`camera-${cam}`);
      await waitFor(() => {
        expect(within(tile).getByText("policy input · 640×480 → 320×240")).toBeInTheDocument();
      });
    }
    expect(screen.getByText(/Episode 1 \/ 1 · model running/)).toBeInTheDocument();
    const joints = screen.getByTestId("joint-panel");
    expect(within(joints).getByRole("columnheader", { name: "Action" })).toBeInTheDocument();
    expect(within(joints).getByRole("columnheader", { name: "Sent" })).toBeInTheDocument();
    expect(within(screen.getByTestId("joint-wrist_flex")).getByText("clipped")).toBeInTheDocument();
    expect(screen.getByTestId("motor-follower-elbow_flex")).toBeInTheDocument();
    expect(within(screen.getByTestId("loop-stats")).getByText("Inference p50/p95")).toBeInTheDocument();
    // The big e-stop is 128 px on this screen.
    expect(screen.getByRole("button", { name: "Emergency stop (Space)" })).toHaveStyle({ width: "128px" });
  });

  it("a critical alert shows the red banner and disables the run controls", async () => {
    const h = setupStation({ paired: true });
    await startRunViaUi(h);
    await advance(h.sim, 3.2);
    const stop = await screen.findByRole("button", { name: "Stop" });
    expect(stop).toBeEnabled();
    act(() => {
      h.runtime.store.handle({
        type: "alert",
        id: "x",
        t: 1,
        level: "critical",
        kind: "temperature",
        arm: "follower",
        motor: "elbow_flex",
        camera: null,
        value: 66,
        message_key: "motor.temp.critical",
        params: {},
        active: true,
      });
    });
    expect(await screen.findByTestId("critical-banner")).toHaveTextContent(
      "Motor critical: elbow_flex 66 °C. Robot stopped, torque off. Let it cool down.",
    );
    expect(screen.getByRole("button", { name: "Stop" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("the thermal safe stop latches e-stop, turns torque off and offers Reset only once cool", async () => {
    const h = setupStation({ paired: true });
    await startRunViaUi(h);
    h.sim.temps.follower.elbow_flex = 66;
    await advance(h.sim, 1.1);
    expect(h.sim.state).toBe("estopped");
    const banner = await screen.findByTestId("critical-banner");
    expect(banner).toHaveTextContent("elbow_flex 66 °C");
    expect(banner).toHaveTextContent("Support the arm. Torque is off.");
    expect(await screen.findByTestId("run-summary")).toBeInTheDocument();
    // Cameras stay on screen after the stop.
    expect(screen.getByTestId("camera-wrist")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "I'm clear, reset" }));
    expect(await screen.findByText(/Motors too hot: elbow_flex/)).toBeInTheDocument();
    expect(h.sim.state).toBe("estopped");
  });
});

describe("Record (§6.6)", () => {
  it("runs the episode loop with → / ← / Esc and ends on the upload card", async () => {
    const h = setupStation({ paired: true });
    const user = userEvent.setup();
    renderStation("/record", h);
    await settle();
    await user.type(await screen.findByLabelText(/Dataset name/), "cube_demo");
    await user.type(screen.getByLabelText(/^Task/), "Pick the cube");
    expect(screen.getByTestId("disk-estimate")).toHaveTextContent("2 camera(s)");
    await user.click(screen.getByRole("button", { name: "Start recording" }));
    await waitFor(() => {
      expect(h.sim.state).toBe("recording");
    });
    await advance(h.sim, 3.1);
    expect(await screen.findByText(/Episode 1 \/ 20 · recording/)).toBeInTheDocument();
    await advance(h.sim, 2);
    fireEvent.keyDown(document.body, { key: "ArrowRight" });
    await waitFor(() => {
      expect(h.sim.session?.s.episode.phase).toBe("reset");
    });
    expect(h.sim.session?.s.episode.saved).toBe(1);
    expect(await screen.findByText("#1")).toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: "ArrowLeft" });
    await waitFor(() => {
      expect(h.sim.session?.s.episode.saved).toBe(0);
    });
    expect(h.sim.session?.s.episode.phase).toBe("episode");
    await advance(h.sim, 1);
    fireEvent.keyDown(document.body, { key: "Escape" });
    await waitFor(() => {
      expect(h.sim.state).toBe("idle");
    });
    const done = await screen.findByTestId("record-done");
    expect(done).toHaveTextContent("1 episodes saved in ~/.hibiscus/station/datasets/cube_demo");
    expect(within(done).getByRole("link", { name: "Upload" })).toHaveAttribute(
      "href",
      "/datasets/cube_demo?upload=1",
    );
  });
});

describe("Teleop (§6.5)", () => {
  it("shows cameras, joints with leader values and motor temperatures", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    renderStation("/teleop", h);
    await settle();
    await user.click(await screen.findByRole("button", { name: "Start teleop" }));
    await advance(h.sim, 0.6);
    expect(await screen.findByText("Follower moving to the leader pose…")).toBeInTheDocument();
    expect(screen.getByTestId("camera-wrist")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("joint-panel")).getByRole("columnheader", { name: "Leader" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("motor-leader-gripper")).toBeInTheDocument();
    await advance(h.sim, 1.0);
    await waitFor(() => {
      expect(screen.queryByText("Follower moving to the leader pose…")).not.toBeInTheDocument();
    });
  });

  it("starts at the fast default rate and shows the measured latency", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    renderStation("/teleop", h);
    await settle();
    expect(screen.getByRole("combobox")).toHaveValue("250");
    await user.click(await screen.findByRole("button", { name: "Start teleop" }));
    await advance(h.sim, 0.6);
    expect(await screen.findByTestId("teleop-latency")).toHaveTextContent("latency ~5 ms, 250 Hz");
  });
});

describe("Calibrate (§6.3)", () => {
  it("guides Home → Ranges → Done with live range bars", async () => {
    const h = setupStation();
    const user = userEvent.setup();
    renderStation("/calibrate", h);
    await settle();
    await user.click(await screen.findByRole("button", { name: "Recalibrate" }));
    expect(await screen.findByTestId("cal-home")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "SO-101 arm with every joint in the middle of its range" }),
    ).toBeInTheDocument();
    expect(screen.getByText("The follower is limp: hold it.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Set home" }));
    await screen.findByTestId("cal-ranges");
    await advance(h.sim, 3);
    await waitFor(() => {
      expect(screen.getByTestId("range-shoulder_pan")).toHaveAttribute("data-ok", "true");
    });
    // LeLab-style: wrist_roll is recorded like every joint, never "full turn".
    expect(
      within(screen.getByTestId("range-wrist_roll")).queryByText("full turn, nothing to record"),
    ).toBeNull();
    await user.click(screen.getByRole("button", { name: "Finish and save" }));
    expect(await screen.findByTestId("cal-done")).toHaveTextContent("so_follower/desk_follower.json");
    expect(screen.getByRole("link", { name: "Next: Cameras" })).toHaveAttribute("href", "/cameras");
  });

  it("offers calibration files written under another name (LeLab) and uses one", async () => {
    const h = setupStation();
    h.sim.calibrated.follower = false;
    let sent: unknown = null;
    server.use(
      http.post(`${stationBase()}/calibration/start`, async ({ request }) => {
        sent = await request.json();
        h.sim.calibrated.follower = true;
        return HttpResponse.json(h.sim.status());
      }),
    );
    const user = userEvent.setup();
    renderStation("/calibrate", h);
    await settle();
    const others = await screen.findByTestId("cal-others-follower");
    expect(others).toHaveTextContent("my_follower");
    expect(others).toHaveTextContent("so101_follower");
    await user.click(within(others).getByRole("button", { name: "Use this file" }));
    await waitFor(() => {
      expect(sent).toMatchObject({ arm: "follower" });
      expect((sent as { source?: string } | null)?.source).toContain("so101_follower/my_follower.json");
    });
  });
});

describe("Upload (§6.7)", () => {
  it("uploads with progress through hashing and uploading, then links the server version", async () => {
    const h = setupStation({ paired: true });
    const user = userEvent.setup();
    renderStation("/datasets/picknplace_red?upload=1", h);
    await settle();
    await user.click(await screen.findByRole("button", { name: "Upload" }));
    const job = await screen.findByTestId(/^job-/);
    expect(job).toHaveTextContent("hashing");
    await advance(h.sim, 2.2);
    await waitFor(() => {
      expect(screen.getByTestId(/^job-/)).toHaveTextContent("uploading");
    });
    await advance(h.sim, 2.2);
    expect(await screen.findByTestId("upload-done")).toHaveTextContent("Uploaded as version 1.");
  });

  it("asks to pair first when there is no server", async () => {
    const h = setupStation();
    renderStation("/datasets/picknplace_red", h);
    await settle();
    expect(await screen.findByText("Pair with a Hibiscus server to upload.")).toBeInTheDocument();
    expect(screen.getByLabelText(/Server URL/)).toBeInTheDocument();
  });
});

describe("Shell and robot screen", () => {
  it("health chip shows the hottest motor; locked steps say why", async () => {
    const h = setupStation({ connected: false });
    renderStation("/robot", h);
    await settle();
    expect((await screen.findAllByText("Connect a robot first.", { selector: "p" })).length).toBeGreaterThan(
      0,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Connect" }));
    await waitFor(() => {
      expect(h.sim.state).toBe("idle");
    });
    h.sim.temps.follower.elbow_flex = 52;
    await advance(h.sim, 0.6);
    const chip = await screen.findByTestId("health-chip");
    await waitFor(() => {
      expect(chip).toHaveAttribute("data-level", "warn");
    });
    expect(chip).toHaveTextContent("52°C");
    expect(screen.getByTestId("hibi-alert")).toHaveTextContent("elbow_flex is getting warm (52 °C).");
    await user.click(chip);
    expect(await screen.findByRole("dialog")).toHaveTextContent("Last 120 s");
  });

  it("maps port_busy to a friendly message", async () => {
    const h = setupStation({ connected: false });
    server.use(
      http.post(`${stationBase()}/robots/:id/connect`, () =>
        HttpResponse.json(
          {
            title: "busy",
            status: 409,
            code: "port_busy",
            params: { port: "/dev/ttyACM0", holder: "pid 42" },
          },
          { status: 409, headers: { "Content-Type": "application/problem+json" } },
        ),
      ),
    );
    renderStation("/robot", h);
    await settle();
    await userEvent.click(await screen.findByRole("button", { name: "Connect" }));
    expect(
      await screen.findByText("Another program (LeLab? lerobot?) is using /dev/ttyACM0."),
    ).toBeInTheDocument();
  });

  it("warns loudly when the demo (simulated) arm is in use while a real arm is plugged in", async () => {
    const h = setupStation();
    const demo = h.sim.profiles[0]!;
    demo.follower.type = "hibiscus_mock_follower";
    demo.follower.port = "mock://follower";
    const user = userEvent.setup();
    renderStation("/robot", h);
    await settle();
    expect(await screen.findByTestId("demo-chip")).toHaveTextContent("DEMO");
    const banner = await screen.findByTestId("demo-banner");
    expect(banner).toHaveTextContent("SIMULATED demo arm");
    await user.click(within(banner).getByRole("button", { name: "Create a profile for the real arm" }));
    expect(await screen.findByRole("heading", { name: "New robot" })).toBeInTheDocument();
    expect(screen.getByTestId("cal-id-follower")).toBeInTheDocument();
  });

  it("identifies arms by role, hints from the voltage and never swaps by itself", async () => {
    const h = setupStation();
    const demo = h.sim.profiles[0]!;
    demo.follower.type = "hibiscus_mock_follower";
    demo.follower.port = "mock://follower";
    const user = userEvent.setup();
    renderStation("/robot", h);
    await settle();
    const banner = await screen.findByTestId("demo-banner");
    await user.click(within(banner).getByRole("button", { name: "Create a profile for the real arm" }));
    // the find buttons say which arm they look for
    expect(screen.getByRole("button", { name: "Find the follower arm (move it)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Find the leader arm (unplug it)" })).toBeInTheDocument();
    // ttyACM0 reads 12.1 V (follower), ttyACM1 5.0 V (leader): right way round, no warning
    const hints = await screen.findAllByTestId("probe-hint");
    expect(hints.map((x) => x.textContent)).toEqual([
      "12.1 V: looks like a follower arm · fw 3.10",
      "5.0 V: looks like a leader arm · fw 3.10",
    ]);
    expect(screen.queryByTestId("role-warning-follower")).not.toBeInTheDocument();
    // swapped by hand: both slots warn, nothing changes until the user swaps back
    await user.click(screen.getByTestId("swap-arms"));
    expect(await screen.findByTestId("role-warning-follower")).toHaveTextContent(
      "The follower arm port reads 5.0 V: it looks like the leader arm.",
    );
    expect(screen.getByTestId("role-warning-leader")).toBeInTheDocument();
    await user.click(screen.getByTestId("swap-arms"));
    await waitFor(() => {
      expect(screen.queryByTestId("role-warning-follower")).not.toBeInTheDocument();
    });
  });

  it("finding an arm by moving fills the slot that was asked for and excludes the other arm", async () => {
    const h = setupStation();
    const bodies: unknown[] = [];
    server.use(
      http.post(`${stationBase()}/ports/detect`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({
          port: {
            device: "/dev/ttyACM1",
            stable_path: null,
            vid_pid: "1a86:55d3",
            serial_number: null,
            description: "",
            in_use_by: null,
          },
        });
      }),
    );
    const user = userEvent.setup();
    renderStation("/robot", h);
    await settle();
    await user.click(screen.getByRole("button", { name: "New robot" }));
    await user.click(await screen.findByRole("button", { name: "Find the leader arm (move it)" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Move ONLY the leader arm/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Start" }));
    await user.click(await within(dialog).findByRole("button", { name: "Use as leader arm" }));
    expect(bodies[0]).toMatchObject({ method: "motion", exclude: [] });
    const selects = screen.getAllByRole("combobox");
    // follower slot untouched, leader slot filled
    expect(selects.some((el) => (el as HTMLSelectElement).value === "/dev/ttyACM1")).toBe(true);
    expect(screen.getByTestId("swap-arms")).toBeEnabled();
  });

  it("shows the server's exact reason under the friendly message", async () => {
    const h = setupStation({ connected: false });
    const detail =
      "follower on COM3: the motors did not pass lerobot's check: Missing motor IDs: - 4 (expected model: 777)";
    server.use(
      http.post(`${stationBase()}/robots/:id/connect`, () =>
        HttpResponse.json(
          {
            title: "A motor did not answer on the serial bus",
            status: 502,
            code: "bus_error",
            detail,
            params: {},
          },
          { status: 502, headers: { "Content-Type": "application/problem+json" } },
        ),
      ),
    );
    renderStation("/robot", h);
    await settle();
    await userEvent.click(await screen.findByRole("button", { name: "Connect" }));
    expect(await screen.findByText(/A motor did not answer\. Check the arm/)).toBeInTheDocument();
    expect(await screen.findByTestId("error-detail")).toHaveTextContent(detail);
  });

  it("switches to Vietnamese", async () => {
    const h = setupStation();
    renderStation("/", h);
    await settle();
    await userEvent.click(await screen.findByRole("button", { name: /Switch language/ }));
    expect(
      await screen.findByText(
        "Station chạy ngay cạnh robot của bạn. Dữ liệu nằm trên máy này cho tới khi bạn tải lên.",
      ),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Đổi ngôn ngữ/ }));
  });
});
