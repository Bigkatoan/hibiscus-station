/**
 * Station strings live in their own "station" namespace (docs/spec/station.md §6), registered at
 * the station entry, so the server app's translation.json is never edited.
 */
import { i18n } from "@/lib/i18n";
import en from "./en.json";
import vi from "./vi.json";

export const STATION_NS = "station";
export const stationResources = { en, vi } as const;

export function registerStationI18n(): void {
  for (const [lng, bundle] of Object.entries(stationResources)) {
    if (!i18n.hasResourceBundle(lng, STATION_NS)) i18n.addResourceBundle(lng, STATION_NS, bundle, true, true);
  }
}
