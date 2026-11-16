/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" only in `--mode mock` (vite.config.ts, station/mock/browser.ts). */
  readonly VITE_STATION_MOCK?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
