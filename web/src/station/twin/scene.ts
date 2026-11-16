/**
 * three.js scene of the 3D twin (lazy chunk): the SO-101 follower from its URDF, an optional
 * translucent ghost arm, orbit controls and render-on-demand (no animation loop: a frame is drawn
 * only when a pose, a colour, the size or the camera changed, so an idle twin costs nothing).
 */
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import URDFLoader, { type URDFRobot } from "urdf-loader";
import { PALETTE } from "@/hibiscus/sprites.gen";
import type { Level } from "../api/types";
import { levelColor, TWIN_JOINTS, type TwinJoint, type UrdfPose } from "./mapping";
import urdfText from "./so101/so101_new_calib.urdf?raw";

const meshUrls = import.meta.glob<string>("./so101/assets/*.stl", {
  query: "?url",
  import: "default",
  eager: true,
});

/** URDF link that houses each motor (its `sts3215` visual is coloured by that motor's level). */
export const MOTOR_LINK: Record<TwinJoint, string> = {
  shoulder_pan: "base_link",
  shoulder_lift: "shoulder_link",
  elbow_flex: "upper_arm_link",
  wrist_flex: "lower_arm_link",
  wrist_roll: "wrist_link",
  gripper: "gripper_link",
};

export type TwinTheme = "light" | "dark";

const THEME: Record<TwinTheme, { bg: string; floor: string; grid: string; printed: string }> = {
  light: { bg: PALETTE.C, floor: PALETTE.c, grid: PALETTE.W, printed: PALETTE.S },
  dark: { bg: "#222842", floor: PALETTE.n, grid: PALETTE.N, printed: PALETTE.S },
};

let geometries: Promise<Map<string, THREE.BufferGeometry>> | null = null;

/** Fetch and parse every mesh once per page (both arms and every twin share the geometry). */
function loadGeometries(): Promise<Map<string, THREE.BufferGeometry>> {
  geometries ??= Promise.all(
    Object.entries(meshUrls).map(async ([path, url]) => {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`mesh ${path}: HTTP ${res.status}`);
      const geom = new STLLoader().parse(await res.arrayBuffer());
      geom.computeVertexNormals();
      return [path.split("/").pop() ?? path, geom] as const;
    }),
  ).then((entries) => new Map(entries));
  geometries.catch(() => {
    geometries = null; // let a later twin retry
  });
  return geometries;
}

interface Arm {
  robot: URDFRobot;
  /** Motor housing (`sts3215` visual) of each motor: always the level colour. */
  motors: Map<TwinJoint, THREE.MeshStandardMaterial>;
  /** Printed parts of the link holding each motor: tinted only when that motor is warm or hot. */
  shells: Map<TwinJoint, THREE.MeshStandardMaterial>;
  /** Printed parts of links without a motor (moving jaw). */
  printed: THREE.MeshStandardMaterial;
}

function linkJoint(mesh: THREE.Object3D): TwinJoint | undefined {
  let o: THREE.Object3D | null = mesh;
  while (o && !("isURDFLink" in o && o.isURDFLink)) o = o.parent;
  return TWIN_JOINTS.find((j) => MOTOR_LINK[j] === o?.name);
}

/** Render order of the ghost's passes: after everything else in their (opaque / transparent) list. */
export const GHOST_ORDER = 10;

function buildArm(geoms: Map<string, THREE.BufferGeometry>, ghost: boolean): Arm {
  const printed = new THREE.MeshStandardMaterial({ roughness: 0.75, metalness: 0.05 });
  const motors = new Map<TwinJoint, THREE.MeshStandardMaterial>();
  const shells = new Map<TwinJoint, THREE.MeshStandardMaterial>();
  // The ghost is drawn in two passes so it reads as one clean translucent shell: a depth-only pass
  // (opaque list, after the live arm, floor and grid) keeps only its front-most surface, then the
  // colour pass blends that surface once. Blending every face without depth (the STL parts overlap
  // and are concave) gave a noisy pink cloud. The polygon offset pushes the ghost a hair back, so
  // where it matches the live arm the solid arm wins cleanly instead of z-fighting.
  const offset = { polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 4 };
  const ghostDepth = new THREE.MeshBasicMaterial({ colorWrite: false, ...offset });
  const ghostMat = new THREE.MeshStandardMaterial({
    color: PALETTE.p, // blush: apart from the steel-grey live arm in both themes
    transparent: true,
    opacity: 0.45,
    depthWrite: false,
    depthFunc: THREE.LessEqualDepth,
    roughness: 0.9,
    ...offset,
  });
  const loader = new URDFLoader();
  const pending: { mesh: THREE.Mesh; motor: boolean }[] = [];
  loader.loadMeshCb = (path, _manager, material, done) => {
    const geom = geoms.get(path.split("/").pop() ?? path);
    if (!geom) {
      done(null as unknown as THREE.Object3D, new Error(`no mesh ${path}`));
      return;
    }
    const mesh = new THREE.Mesh(geom, ghost ? ghostMat : printed);
    if (ghost) {
      mesh.renderOrder = GHOST_ORDER;
      const depth = new THREE.Mesh(geom, ghostDepth);
      depth.renderOrder = GHOST_ORDER;
      mesh.add(depth);
    }
    pending.push({ mesh, motor: material.name.startsWith("sts3215") });
    done(mesh);
  };
  const robot = loader.parse(urdfText);
  if (!ghost) {
    for (const { mesh, motor } of pending) {
      const joint = linkJoint(mesh);
      if (!joint) continue;
      const map = motor ? motors : shells;
      let mat = map.get(joint);
      if (!mat) {
        mat = motor
          ? new THREE.MeshStandardMaterial({ roughness: 0.55, metalness: 0.1 })
          : new THREE.MeshStandardMaterial({ roughness: 0.75, metalness: 0.05 });
        map.set(joint, mat);
      }
      mesh.material = mat;
    }
  }
  // URDF is Z-up; three.js is Y-up.
  robot.rotation.x = -Math.PI / 2;
  return { robot, motors, shells, printed };
}

function applyPose(robot: URDFRobot, pose: UrdfPose): boolean {
  let changed = false;
  for (const j of TWIN_JOINTS) {
    const v = pose[j];
    if (v === undefined) continue;
    if (robot.setJointValue(j, v)) changed = true;
  }
  return changed;
}

/** Default camera direction (from the target): front-right, a little above. */
const VIEW_DIR = new THREE.Vector3(0.75, 0.5, 0.9).normalize();

export class TwinScene {
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(35, 1, 0.01, 10);
  private readonly controls: OrbitControls;
  private readonly floor: THREE.Mesh;
  private grid: THREE.GridHelper;
  private arm: Arm | null = null;
  private ghost: Arm | null = null;
  private frame = 0;
  private disposed = false;
  private visible = true;
  private dirty = false;
  private theme: TwinTheme = "light";
  private pose: UrdfPose = {};
  private ghostPose: UrdfPose | null = null;
  private levels: Partial<Record<TwinJoint, Level | null>> = {};
  private readonly resize: ResizeObserver;
  private readonly home = { target: new THREE.Vector3(0, 0.15, 0), distance: 0.75 };
  /** Frames drawn so far (tests and the idle check read it). */
  frames = 0;

  constructor(private readonly host: HTMLElement) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "low-power" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.domElement.style.display = "block";
    this.renderer.domElement.style.width = "100%";
    this.renderer.domElement.style.height = "100%";
    host.appendChild(this.renderer.domElement);

    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x8b9bb4, 1.6));
    const key = new THREE.DirectionalLight(0xffffff, 1.8);
    key.position.set(0.6, 1.2, 0.8);
    this.scene.add(key);
    const rim = new THREE.DirectionalLight(0xffffff, 0.5);
    rim.position.set(-0.8, 0.5, -0.6);
    this.scene.add(rim);

    this.floor = new THREE.Mesh(
      new THREE.CircleGeometry(0.26, 48),
      new THREE.MeshStandardMaterial({ roughness: 1 }),
    );
    this.floor.rotation.x = -Math.PI / 2;
    this.floor.position.y = -0.001;
    this.scene.add(this.floor);
    this.grid = new THREE.GridHelper(0.5, 10);
    this.scene.add(this.grid);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = false;
    this.controls.enablePan = false;
    this.controls.maxPolarAngle = Math.PI * 0.49;
    this.controls.addEventListener("change", this.invalidate);
    this.placeCamera();

    this.resize = new ResizeObserver(this.onResize);
    this.resize.observe(host);
    this.onResize();
    this.setTheme("light");
  }

  /** Load the model (meshes are fetched once per page). Resolves when the arm is on screen. */
  async load(): Promise<void> {
    const geoms = await loadGeometries();
    if (this.disposed) return;
    this.arm = buildArm(geoms, false);
    this.scene.add(this.arm.robot);
    this.fitView(this.arm.robot);
    applyPose(this.arm.robot, this.pose);
    this.paintMotors();
    this.paintTheme();
    if (this.ghostPose) this.showGhost(geoms);
    this.invalidate();
  }

  setPose(pose: UrdfPose): void {
    this.pose = { ...this.pose, ...pose };
    if (this.arm && applyPose(this.arm.robot, pose)) this.invalidate();
  }

  /** A pose for the translucent ghost arm, or null to hide it. */
  setGhostPose(pose: UrdfPose | null): void {
    this.ghostPose = pose;
    if (!pose) {
      if (this.ghost) {
        this.ghost.robot.visible = false;
        this.invalidate();
      }
      return;
    }
    if (!this.ghost) {
      if (this.arm) void loadGeometries().then((g) => this.showGhost(g));
      return;
    }
    this.ghost.robot.visible = true;
    applyPose(this.ghost.robot, pose);
    this.invalidate();
  }

  private showGhost(geoms: Map<string, THREE.BufferGeometry>): void {
    if (this.disposed || this.ghost || !this.ghostPose) return;
    this.ghost = buildArm(geoms, true);
    this.scene.add(this.ghost.robot);
    applyPose(this.ghost.robot, this.ghostPose);
    this.invalidate();
  }

  setLevels(levels: Partial<Record<TwinJoint, Level | null>>): void {
    this.levels = levels;
    this.paintMotors();
    this.invalidate();
  }

  setTheme(theme: TwinTheme): void {
    this.theme = theme;
    this.paintTheme();
    this.invalidate();
  }

  resetView(): void {
    this.placeCamera();
    this.invalidate();
  }

  /** Frame the arm at its rest pose with room for it to move (the sphere around its box). */
  private fitView(robot: URDFRobot): void {
    applyPose(robot, Object.fromEntries(TWIN_JOINTS.map((j) => [j, 0])));
    robot.updateMatrixWorld(true);
    const sphere = new THREE.Box3().setFromObject(robot).getBoundingSphere(new THREE.Sphere());
    const fov = (this.camera.fov * Math.PI) / 180;
    const fit = Math.min(fov, 2 * Math.atan(Math.tan(fov / 2) * Math.max(this.camera.aspect, 0.75)));
    this.home.target.copy(sphere.center);
    this.home.distance = (sphere.radius * 0.95) / Math.sin(fit / 2);
    this.controls.minDistance = this.home.distance * 0.4;
    this.controls.maxDistance = this.home.distance * 2.5;
    this.placeCamera();
  }

  private placeCamera(): void {
    this.controls.target.copy(this.home.target);
    this.camera.position.copy(this.home.target).addScaledVector(VIEW_DIR, this.home.distance);
    this.controls.update();
  }

  private paintMotors(): void {
    if (!this.arm) return;
    const base = THEME[this.theme].printed;
    for (const [joint, mat] of this.arm.motors) mat.color.set(levelColor(this.levels[joint] ?? null));
    for (const [joint, mat] of this.arm.shells) {
      const level = this.levels[joint] ?? null;
      mat.color.set(base);
      if (level !== null && level !== "ok") mat.color.lerp(new THREE.Color(levelColor(level)), 0.7);
    }
  }

  private paintTheme(): void {
    const c = THEME[this.theme];
    this.scene.background = new THREE.Color(c.bg);
    (this.floor.material as THREE.MeshStandardMaterial).color.set(c.floor);
    this.scene.remove(this.grid);
    this.grid.dispose();
    this.grid = new THREE.GridHelper(0.5, 10, c.grid, c.grid);
    this.scene.add(this.grid);
    this.arm?.printed.color.set(c.printed);
    this.paintMotors();
  }

  private onResize = (): void => {
    const w = Math.max(1, this.host.clientWidth);
    const h = Math.max(1, this.host.clientHeight);
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.invalidate();
  };

  /** Off screen (scrolled away): changes are kept and drawn once it is visible again. */
  setVisible(visible: boolean): void {
    this.visible = visible;
    if (visible && this.dirty) this.invalidate();
  }

  /** Ask for one frame (coalesced; rAF does not fire while the tab is hidden). */
  invalidate = (): void => {
    if (this.disposed || this.frame) return;
    if (!this.visible) {
      this.dirty = true;
      return;
    }
    this.dirty = false;
    this.frame = requestAnimationFrame(() => {
      this.frame = 0;
      if (this.disposed) return;
      this.renderer.render(this.scene, this.camera);
      this.frames += 1;
    });
  };

  dispose(): void {
    this.disposed = true;
    if (this.frame) cancelAnimationFrame(this.frame);
    this.resize.disconnect();
    this.controls.removeEventListener("change", this.invalidate);
    this.controls.dispose();
    for (const arm of [this.arm, this.ghost]) {
      if (!arm) continue;
      arm.robot.traverse((o) => {
        if (o instanceof THREE.Mesh) (o.material as THREE.Material).dispose();
      });
    }
    this.grid.dispose();
    this.floor.geometry.dispose();
    (this.floor.material as THREE.Material).dispose();
    this.renderer.dispose();
    this.renderer.forceContextLoss();
    this.renderer.domElement.remove();
  }
}
