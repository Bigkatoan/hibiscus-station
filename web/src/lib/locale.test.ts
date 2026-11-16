import { afterEach, describe, expect, it, vi } from "vitest";
import { formatDateTime, formatInt } from "./format";
import { detectLanguage } from "./i18n";
import { browserLocale, installNavigatorLocaleGuard, safeLocale, sanitizeLocale } from "./locale";

function fakeNavigator(language: string, languages: string[] = [language]) {
  vi.spyOn(navigator, "language", "get").mockReturnValue(language);
  vi.spyOn(navigator, "languages", "get").mockReturnValue(languages);
}

afterEach(() => {
  vi.restoreAllMocks();
  // installNavigatorLocaleGuard shadows the getters on the instance; drop them again.
  Reflect.deleteProperty(navigator, "language");
  Reflect.deleteProperty(navigator, "languages");
});

describe("locale sanitising (QC N-3: blank SPA under LANG=C)", () => {
  it("repairs POSIX tags and rejects garbage", () => {
    expect(() => new Intl.NumberFormat("en-US@posix")).toThrow(RangeError);
    expect(sanitizeLocale("en-US@posix")).toBe("en-US");
    expect(sanitizeLocale("vi_VN.UTF-8")).toBe("vi-VN");
    expect(sanitizeLocale("C")).toBeNull();
    expect(sanitizeLocale("C.UTF-8")).toBeNull();
    expect(sanitizeLocale("!!")).toBeNull();
    expect(sanitizeLocale(undefined)).toBeNull();
    expect(safeLocale("POSIX")).toBe("vi");
    expect(safeLocale("en")).toBe("en");
  });

  it("detects the UI language from an invalid navigator.language", () => {
    fakeNavigator("en-US@posix");
    expect(browserLocale()).toBe("en-US");
    expect(detectLanguage()).toBe("en");
    fakeNavigator("C", ["C"]);
    expect(browserLocale()).toBe("vi");
    expect(detectLanguage()).toBe("vi");
  });

  it("formatters never throw on a bad locale", () => {
    expect(formatInt(1234, "en-US@posix")).toBe("1,234");
    expect(formatDateTime("2026-11-15T09:30:00Z", "C")).not.toBe("—");
  });

  it("shadows navigator.language so third-party Intl calls (uPlot) do not throw", () => {
    fakeNavigator("en-US@posix", ["en-US@posix", "fr_FR"]);
    installNavigatorLocaleGuard();
    expect(navigator.language).toBe("en-US");
    expect(navigator.languages).toEqual(["en-US", "fr-FR"]);
    expect(() => new Intl.NumberFormat(navigator.language)).not.toThrow();
  });

  it("leaves a valid navigator.language alone", () => {
    fakeNavigator("vi-VN", ["vi-VN", "en"]);
    const define = vi.spyOn(Object, "defineProperty");
    installNavigatorLocaleGuard();
    expect(define.mock.calls.filter(([target]) => target === navigator)).toEqual([]);
    expect(navigator.languages).toEqual(["vi-VN", "en"]);
  });
});
