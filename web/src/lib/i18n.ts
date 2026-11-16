import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "@/i18n/en/translation.json";
import vi from "@/i18n/vi/translation.json";
import { browserLocale } from "./locale";
import { prefs } from "./utils";

export const SUPPORTED_LANGUAGES = ["vi", "en"] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];

export function isLanguage(value: unknown): value is Language {
  return value === "vi" || value === "en";
}

export function detectLanguage(): Language {
  const stored = prefs.get("lang");
  if (isLanguage(stored)) return stored;
  // Sanitised: a POSIX tag such as `en-US@posix` must not break detection (QC N-3).
  const nav = browserLocale().toLowerCase();
  return nav.startsWith("en") ? "en" : "vi";
}

export const resources = { en: { translation: en }, vi: { translation: vi } } as const;

export function initI18n(lng: Language = detectLanguage()): typeof i18n {
  if (!i18n.isInitialized) {
    void i18n.use(initReactI18next).init({
      resources,
      lng,
      fallbackLng: "en",
      supportedLngs: SUPPORTED_LANGUAGES,
      interpolation: { escapeValue: false },
      returnNull: false,
    });
  }
  document.documentElement.lang = lng;
  return i18n;
}

export function setLanguage(lng: Language): void {
  prefs.set("lang", lng);
  document.documentElement.lang = lng;
  void i18n.changeLanguage(lng);
}

export { i18n };
