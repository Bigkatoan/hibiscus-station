/**
 * The plural class sweep (QC 0.2.9 QD-8, QD-17, QD-20): an English string that puts a number before
 * a plural noun ("{{n}} steps") reads "1 steps" unless it is an i18next plural (key_one /
 * key_other, the number passed as `count`). Used by the i18n tests of both namespaces.
 */
const PLURAL_RE = /_(zero|one|two|few|many|other)$/;

/** Words after a number that are not a counted noun: verbs, and units written the same for 1. */
const NOT_COUNTED = new Set(["is", "was", "has", "does", "sees", "reports", "draws", "fps", "ms", "s"]);

/** Every en entry that counts something without the _one / _other forms, as "key: reason". */
export function countsWithoutPlural(entries: Iterable<[string, string]>): string[] {
  const map = new Map(entries);
  const bad: string[] = [];
  for (const [key, value] of map) {
    const base = key.replace(PLURAL_RE, "");
    // "check_other" is a plain key; a plural form has {{count}} or a sibling form
    const forms = ["_one", "_other"].filter((f) => map.has(`${base}${f}`)).length;
    const plural = PLURAL_RE.test(key) && (/\{\{\s*count\s*\}\}/.test(value) || forms > 1);
    if (plural && !(map.has(`${base}_one`) && map.has(`${base}_other`)))
      bad.push(`${key}: needs both ${base}_one and ${base}_other`);
    if (/\{\{\s*count\s*\}\}/.test(value) && !plural) bad.push(`${key}: {{count}} without _one / _other`);
    for (const m of value.matchAll(/(\/\s*)?\{\{\s*(\w+)\s*\}\}\s+([A-Za-z]+)\b/g)) {
      const [, fraction, token, word = ""] = m;
      // "3/6 motors", "2 / 6 joints": the noun counts the total, which is never 1 here
      if (fraction || !word.endsWith("s") || NOT_COUNTED.has(word)) continue;
      if (!plural || token !== "count") bad.push(`${key}: "{{${token ?? ""}}} ${word}" is not a plural`);
    }
  }
  return bad;
}
