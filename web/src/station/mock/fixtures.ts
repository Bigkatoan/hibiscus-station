/** Fixtures for the mock Station (tests and `vite --mode mock`). */
import type {
  CalibrationFile,
  DiscoveredCamera,
  LocalDatasetDetail,
  ModelEntry,
  Port,
  RobotProfile,
  ServerDataset,
  ServerModel,
  ServerRun,
  SessionSummary,
  Settings,
} from "../api/types";

export const MOTORS = [
  "shoulder_pan",
  "shoulder_lift",
  "elbow_flex",
  "wrist_flex",
  "wrist_roll",
  "gripper",
] as const;

export const ports: Port[] = [
  {
    device: "/dev/ttyACM0",
    stable_path: "/dev/serial/by-id/usb-1a86_USB_Single_Serial_5A46083061-if00",
    vid_pid: "1a86:55d3",
    serial_number: "5A46083061",
    description: "USB Single Serial",
    in_use_by: null,
  },
  {
    device: "/dev/ttyACM1",
    stable_path: "/dev/serial/by-id/usb-1a86_USB_Single_Serial_5A46083188-if00",
    vid_pid: "1a86:55d3",
    serial_number: "5A46083188",
    description: "USB Single Serial",
    in_use_by: null,
  },
];

export const robot: RobotProfile = {
  id: "desk_so101",
  name: "Desk SO-101",
  follower: {
    type: "so101_follower",
    port: ports[0]?.stable_path ?? "/dev/ttyACM0",
    calibration_id: "desk_follower",
    max_relative_target: 5,
    rest_pose: null,
    on_session_end: "hold",
    disable_torque_on_disconnect: true,
    allow_fast_replay: false,
    grip_hold: { gap_min: 3, load_min_pct: 15 },
  },
  leader: {
    type: "so101_leader",
    port: ports[1]?.stable_path ?? "/dev/ttyACM1",
    calibration_id: "desk_leader",
  },
  cameras: {
    wrist: {
      type: "opencv",
      index_or_path: "/dev/v4l/by-id/usb-HD_USB_Camera-video-index0",
      serial_number_or_name: null,
      width: 640,
      height: 480,
      fps: 30,
      fourcc: "MJPG",
      rotation: 0,
    },
    front: {
      type: "opencv",
      index_or_path: "/dev/v4l/by-id/usb-Logi_C920-video-index0",
      serial_number_or_name: null,
      width: 640,
      height: 480,
      fps: 30,
      fourcc: "MJPG",
      rotation: 0,
    },
  },
  thresholds: null,
  safety_ack: true,
};

export const calibrations: CalibrationFile[] = [
  {
    arm: "follower",
    id: "desk_follower",
    path: "~/.cache/huggingface/lerobot/calibration/robots/so_follower/desk_follower.json",
    modified_at: "2026-11-14T09:12:00Z",
    dir: "so_follower",
  },
  {
    arm: "leader",
    id: "desk_leader",
    path: "~/.cache/huggingface/lerobot/calibration/teleoperators/so_leader/desk_leader.json",
    modified_at: "2026-11-14T09:20:00Z",
    dir: "so_leader",
  },
  {
    arm: "follower",
    id: "my_follower",
    path: "~/.cache/huggingface/lerobot/calibration/robots/so101_follower/my_follower.json",
    modified_at: "2026-10-02T15:40:00Z",
    dir: "so101_follower",
  },
  {
    arm: "leader",
    id: "my_leader",
    path: "~/.cache/huggingface/lerobot/calibration/teleoperators/so101_leader/my_leader.json",
    modified_at: "2026-10-02T15:44:00Z",
    dir: "so101_leader",
  },
];

export const discovered: DiscoveredCamera[] = [
  {
    type: "opencv",
    id: "/dev/video4",
    stable_path: "/dev/v4l/by-id/usb-Generic_USB2.0_Camera-video-index0",
    name: "USB2.0 Camera",
    default: { width: 640, height: 480, fps: 30, fourcc: "MJPG" },
    in_use_by: null,
  },
];

export function dataset(name = "picknplace_red", episodes = 3): LocalDatasetDetail {
  return {
    name,
    root: `~/.hibiscus/station/datasets/${name}`,
    episodes,
    frames: episodes * 900,
    fps: 30,
    robot_type: "so101_follower",
    cameras: ["wrist", "front"],
    video: true,
    size_bytes: episodes * 22_000_000,
    finalized: true,
    finalize_reasons: [],
    uploads: [],
    uploaded: null,
    task: "Pick the red cube and place it in the bowl",
    episode_list: Array.from({ length: episodes }, (_, i) => ({
      index: i,
      state: "saved" as const,
      length_s: 30,
      frames: 900,
      tasks: ["Pick the red cube and place it in the bowl"],
      telemetry_lines: 120,
      max_temp_c: {
        follower: {
          shoulder_pan: 38,
          shoulder_lift: 44,
          elbow_flex: 47 + i * 3,
          wrist_flex: 40,
          wrist_roll: 36,
          gripper: 41,
        },
      },
    })),
  };
}

export const model: ModelEntry = {
  key: "so101_picknplace_act-r42-step10000",
  name: "picknplace ACT · run #42",
  source: "bundle",
  server_model_id: "m_42",
  policy_type: "act",
  input_features: {
    "observation.state": { type: "STATE", shape: [6] },
    "observation.images.wrist": { type: "VISUAL", shape: [3, 480, 640] },
    "observation.images.front": { type: "VISUAL", shape: [3, 480, 640] },
  },
  output_features: { action: { type: "ACTION", shape: [6] } },
  fps: 30,
  task: "Pick the red cube and place it in the bowl",
  robot_type: "so101_follower",
  verified: true,
  imported_at: "2026-11-15T08:00:00Z",
  size_bytes: 206_000_000,
  pretrained_path: "pretrained_model",
};

export const serverDatasets: ServerDataset[] = [{ id: "d_7", name: "picknplace_red", latest_version: 2 }];
export const serverModels: ServerModel[] = [
  {
    id: "m_51",
    name: "picknplace diffusion · run #51",
    status: "ready",
    policy_type: "diffusion",
    size_bytes: 1_050_000_000,
    created_at: "2026-11-15T07:00:00Z",
  },
  {
    id: "m_52",
    name: "towel fold ACT · run #52",
    status: "exporting",
    policy_type: "act",
    size_bytes: 0,
    created_at: "2026-11-15T09:00:00Z",
  },
];
export const serverRuns: ServerRun[] = [
  {
    id: "r_42",
    number: 42,
    status: "succeeded",
    policy_type: "act",
    progress: 1,
    url: "https://hibiscus.example.org/w/lab/runs/42",
    model_id: "m_42",
  },
  {
    id: "r_51",
    number: 51,
    status: "running",
    policy_type: "diffusion",
    progress: 0.42,
    url: "https://hibiscus.example.org/w/lab/runs/51",
    model_id: null,
  },
];

export const settings: Settings = {
  thresholds: {
    temp_warn_c: 50,
    temp_hot_c: 60,
    temp_critical_c: 65,
    hysteresis_c: 3,
    critical_consecutive: 2,
    voltage_margin_v: 0.5,
    voltage_nominal_ratio: 0.85,
    current_ratio: 0.8,
    load_stall_pct: 90,
    load_stall_s: 2,
  },
  telemetry: { hot_hz: 2, cool_hz: 1, min_slack_ms: 6, max_age_s: 2, monitor_hz: 2, joints_hz: 20 },
  preview: { fps: 12, width: 320, quality: 70 },
  safety: {
    max_relative_target: 5,
    teleop_max_relative_target: 30,
    deadman_timeout_s: 1,
    deadman_replay: true,
    estop_double_press_s: 2,
    park_s: 1.5,
    smooth_approach_s: 1.5,
    stopping_deadline_s: 10,
    camera_stale_pause_s: 0.5,
    camera_lost_stop_s: 3,
    overrun_pause_s: 5,
    max_approach_deg: 30,
  },
  programs: {
    require_dry_run: true,
    condition_hz: 10,
    wait_timeout_s: 30,
    approach_speed_deg_s: 30,
    approach_threshold_deg: 3,
    check_speed_pct: 25,
    traj_default_s: 60,
    traj_max_s: 600,
    idle_trim_deg: 0.5,
    idle_trim_s: 0.5,
    max_blocks: 2000,
    notify_webhook: null,
    mqtt_url: null,
    mqtt_topics: [],
  },
  device: "auto",
  session_retention_days: 30,
  session_retention_bytes: 2147483648,
};

export const sessions: SessionSummary[] = [
  {
    id: "s_20261114_101501_a1b2",
    kind: "record",
    started_at: "2026-11-14T10:15:01Z",
    ended_at: "2026-11-14T10:32:40Z",
    outcome: "completed",
    reason: "completed",
    dataset: "picknplace_red",
    model: null,
    robot: "desk_so101",
    episodes: 3,
    max_temp_c: 53,
  },
];
