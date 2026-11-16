/**
 * Locale sanitising (QC N-3). Browsers in a `LANG=C` environment report tags such as
 * `en-US@posix` or `C.UTF-8`; passing those to any `Intl.*` constructor throws
 * `RangeError: Incorrect locale information provided`, which used to blank the whole SPA
 * (uPlot builds `new Intl.NumberFormat(navigator.language)` at module load).
 */

const FALLBACKS = ["vi", "en"] as const;

/** A canonical BCP-47 tag for `tag`, or null when it cannot be repaired. */
export function sanitizeLocale(tag: string | null | undefined): string | null {
  if (typeof tag !== "string") return null;
  // POSIX forms: drop the modifier (@posix) and codeset (.UTF-8); en_US -> en-US.
  const cleaned = tag.trim().split("@")[0]?.split(".")[0]?.replace(/_/g, "-") ?? "";
  if (!cleaned || cleaned.toUpperCase() === "C" || cleaned.toUpperCase() === "POSIX") return null;
  try {
    const [canonical] = Intl.getCanonicalLocales(cleaned);
    if (!canonical) return null;
    // Some engines accept a tag in getCanonicalLocales but still reject it in constructors.
    new Intl.NumberFormat(canonical);
    return canonical;
  } catch {
    return null;
  }
}

/** `tag` if usable by Intl, else the first usable fallback (vi, then en). */
export function safeLocale(tag: string | null | undefined): string {
  const ok = sanitizeLocale(tag);
  if (ok) return ok;
  for (const f of FALLBACKS) {
    if (sanitizeLocale(f)) return f;
  }
  return "en";
}

/** navigator.language followed by navigator.languages (the latter is missing in some engines). */
function navigatorLanguages(): string[] {
  const list = navigator.languages as readonly string[] | undefined;
  return [navigator.language, ...(list ? Array.from(list) : [])];
}

/** The browser's preferred locale, sanitised. */
export function browserLocale(): string {
  if (typeof navigator === "undefined") return FALLBACKS[0];
  const candidates = navigatorLanguages();
  for (const c of candidates) {
    const ok = sanitizeLocale(c);
    if (ok) return ok;
  }
  return safeLocale(null);
}

/**
 * Third-party code (uPlot) reads `navigator.language` straight into `Intl`. When the browser
 * reports an invalid tag, shadow `navigator.language(s)` with sanitised values. Must run before
 * those modules are evaluated: it is the first import of main.tsx.
 */
export function installNavigatorLocaleGuard(): void {
  if (typeof navigator === "undefined") return;
  const langs = navigatorLanguages();
  if (langs.every((l) => sanitizeLocale(l) === l)) return;
  const primary = browserLocale();
  const fixed = Array.from(
    new Set([primary, ...langs.map((l) => sanitizeLocale(l)).filter((l): l is string => !!l)]),
  );
  try {
    Object.defineProperty(navigator, "language", { configurable: true, get: () => primary });
    Object.defineProperty(navigator, "languages", { configurable: true, get: () => fixed });
  } catch {
    /* non-configurable in this engine: the error boundary still catches what slips through */
  }
}
