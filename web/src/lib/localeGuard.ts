// Side-effect module: imported first by main.tsx so it runs before uPlot reads
// navigator.language at module load (QC N-3).
import { installNavigatorLocaleGuard } from "./locale";

installNavigatorLocaleGuard();
