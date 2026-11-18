import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Field } from "@/components/Field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "../api/client";
import { qk, useStationMutation } from "../api/hooks";
import type { ServerLink } from "../api/types";
import { StationError } from "./StationError";

export const TOKEN_SCOPES = "datasets:write,models:read,runs:read";

export function tokenUrl(server: string): string | null {
  try {
    const u = new URL("/account/tokens", server);
    if (u.protocol !== "https:" && u.protocol !== "http:") return null;
    u.searchParams.set("scopes", TOKEN_SCOPES);
    return u.toString();
  } catch {
    return null;
  }
}

/**
 * A friendly early hint for the share-link families the customer named (field report 0.2.9: a
 * OneDrive link): OneDrive / SharePoint / Office / `cloud.microsoft` / Teams, Google Drive / Docs /
 * usercontent, Dropbox, the domain or any subdomain. Outlook Safe Links and Google redirect links
 * are unwrapped. Unknown hosts are not judged (QD-41): the Station's identity probe on pairing is
 * what keeps the token safe (QD-40). Same rules as `hibiscus_station/server_url.py`; both are
 * tested on `tests/server_urls.json`.
 */
const FILE_SHARE_DOMAINS = [
  "cloud.microsoft",
  "officeapps.live.com",
  "office.com",
  "office.net",
  "office365.com",
  "sharepoint.com",
  "onedrive.com",
  "onedrive.live.com",
  "skydrive.live.com",
  "docs.live.net",
  "1drv.ms",
  "teams.microsoft.com",
  "drive.google.com",
  "docs.google.com",
  "usercontent.google.com",
  "googleusercontent.com",
  "dropbox.com",
  "dropboxusercontent.com",
  "db.tt",
];

/** Link wrappers whose real target is in a query parameter. */
const WRAPPERS: [string, string[]][] = [
  ["safelinks.protection.outlook.com", ["url"]],
  ["google.com", ["q", "url"]],
];

const on = (host: string, domain: string) => host === domain || host.endsWith(`.${domain}`);

export type ServerUrlProblem = "not_url" | "file_share" | "insecure";

/** IPv4 networks a plain http:// server may be on: loopback, RFC 1918, link-local, CGNAT. */
const LOCAL_V4: [number, number][] = [
  [0x7f000000, 8],
  [0x0a000000, 8],
  [0xac100000, 12],
  [0xc0a80000, 16],
  [0xa9fe0000, 16],
  [0x64400000, 10],
];

function ipv4(host: string): number | null {
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(host);
  if (!m) return null;
  const parts = m.slice(1).map(Number);
  if (parts.some((p) => p > 255)) return null;
  return parts.reduce((a, p) => a * 256 + p, 0);
}

/**
 * A host on this computer or the local network (QD-45): localhost, loopback / private /
 * link-local / CGNAT addresses (IPv4 and IPv6), `*.local`, `*.lan` and single-label names. Plain
 * http:// is only allowed there; the same rule as `is_local_host` on the Station.
 */
export function isLocalHost(raw: string): boolean {
  const host = raw
    .replace(/^\[|\]$/g, "")
    .replace(/\.$/, "")
    .toLowerCase();
  const v4 = ipv4(host);
  if (v4 !== null)
    return LOCAL_V4.some(
      ([net, bits]) => Math.floor(v4 / 2 ** (32 - bits)) === Math.floor(net / 2 ** (32 - bits)),
    );
  if (host.includes(":")) {
    // IPv6: ::1, fc00::/7 (ULA), fe80::/10 (link-local)
    if (host === "::1") return true;
    const first = parseInt(host.split(":")[0] ?? "0", 16);
    return (first & 0xfe00) === 0xfc00 || (first & 0xffc0) === 0xfe80;
  }
  return !host.includes(".") || on(host, "localhost") || host.endsWith(".local") || host.endsWith(".lan");
}

/** Why `raw` cannot be a Hibiscus server address, or null when the hint has nothing to say. */
export function serverUrlProblem(raw: string, depth = 0): ServerUrlProblem | null {
  const text = raw.trim();
  let u: URL;
  try {
    u = new URL(text);
  } catch {
    return "not_url";
  }
  if ((u.protocol !== "https:" && u.protocol !== "http:") || !u.hostname || /\s/.test(text)) return "not_url";
  const host = u.hostname.toLowerCase().replace(/\.$/, "");
  if (FILE_SHARE_DOMAINS.some((d) => on(host, d))) return "file_share";
  for (const [wrapper, keys] of WRAPPERS) {
    if (!on(host, wrapper) || depth >= 3) continue;
    const inner = [...u.searchParams].find(([k, v]) => keys.includes(k.toLowerCase()) && v.includes("://"));
    if (inner && serverUrlProblem(inner[1], depth + 1) === "file_share") return "file_share";
  }
  // The token must never cross the internet in clear text (QD-45).
  if (u.protocol === "http:" && !isLocalHost(u.hostname)) return "insecure";
  return null;
}

/** Pair with a Hibiscus server (§4.8): server URL + personal access token. */
export function PairForm({ onPaired }: { onPaired?: () => void }) {
  const { t } = useTranslation("station");
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const [touched, setTouched] = useState(false);
  const pair = useStationMutation(
    (body: { url: string; token: string }) => api.post<ServerLink>("/server/pair", body),
    [qk.server, qk.status],
  );
  const problem = url.trim() ? serverUrlProblem(url) : null;
  // A pasted file-share link is said at once; a half-typed (or plain http) address once the field
  // is left. Pair stays off meanwhile.
  const urlError = problem === "file_share" || (problem && touched) ? t(`pair.url_${problem}`) : undefined;
  const link = problem ? null : tokenUrl(url);
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (problem) {
          setTouched(true);
          return;
        }
        pair.mutate(
          { url: url.trim(), token: token.trim() },
          {
            onSuccess: () => {
              setToken("");
              onPaired?.();
            },
          },
        );
      }}
    >
      <Field label={t("pair.url")} required error={urlError}>
        <Input
          type="url"
          value={url}
          placeholder="https://hibiscus.example.org"
          data-testid="pair-url"
          onChange={(e) => {
            setUrl(e.target.value);
          }}
          onBlur={() => {
            setTouched(true);
          }}
        />
      </Field>
      <Field
        label={t("pair.token")}
        required
        description={
          link ? (
            <a href={link} target="_blank" rel="noreferrer noopener" className="underline">
              {t("pair.create_token")}
            </a>
          ) : (
            t("pair.token_hint")
          )
        }
      >
        <Input
          type="password"
          autoComplete="off"
          value={token}
          onChange={(e) => {
            setToken(e.target.value);
          }}
        />
      </Field>
      <StationError error={pair.error} />
      {pair.isSuccess ? (
        <p role="status" className="text-sm text-success">
          {t("pair.done")}
        </p>
      ) : null}
      <Button
        type="submit"
        className="self-start"
        disabled={!url.trim() || problem !== null || !token.trim() || pair.isPending}
      >
        {t("pair.submit")}
      </Button>
    </form>
  );
}
