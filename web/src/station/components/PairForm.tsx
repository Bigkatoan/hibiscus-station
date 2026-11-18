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
 * File-sharing / office sites (the domain or any subdomain): people paste their links instead of
 * the server address (field report 0.2.9: a OneDrive link). Same rules as the Station's own check
 * (`hibiscus_station/server_url.py`); both are tested on `tests/server_urls.json`.
 */
const FILE_SHARE_DOMAINS = [
  // Microsoft 365 / OneDrive / SharePoint
  "cloud.microsoft",
  "officeapps.live.com",
  "office.com",
  "office.net",
  "office365.com",
  "sharepoint.com",
  "sharepoint-df.com",
  "onedrive.com",
  "onedrive.live.com",
  "skydrive.live.com",
  "storage.live.com",
  "1drv.ms",
  "1drv.com",
  "microsoftpersonalcontent.com",
  // Google
  "drive.google.com",
  "docs.google.com",
  "googleusercontent.com",
  // Dropbox, Box, WeTransfer, iCloud, others
  "dropbox.com",
  "dropboxusercontent.com",
  "db.tt",
  "box.com",
  "box.net",
  "boxcloud.com",
  "wetransfer.com",
  "we.tl",
  "icloud.com",
  "mega.nz",
  "mediafire.com",
];

/** Query parameters of share links (OneDrive / Office / SharePoint), lower case. */
const SHARE_PARAMS = new Set(["docid", "driveid", "resid", "authkey", "redeem", "sourcedoc", "cid"]);

/** Paths of share links (/open/onedrive, SharePoint "/:w:/", Google "/file/d/"…) and document names. */
const SHARE_PATH =
  /\/open\/onedrive|\/:[a-z]{1,2}:\/|\/file\/d\/|\/drive\/folders\/|\/_layouts\/|\/scl\/f[io]\/|\.(docx?|xlsx?|pptx?|pdf|zip|rar|7z|txt|csv|odt|ods)$/i;

export type ServerUrlProblem = "not_url" | "file_share";

/**
 * Why `raw` cannot be a Hibiscus server address, or null when it can (D-25, QD-35): it must be an
 * http(s) URL, and not a link to a file-sharing site or to a shared file.
 */
export function serverUrlProblem(raw: string): ServerUrlProblem | null {
  const text = raw.trim();
  let u: URL;
  try {
    u = new URL(text);
  } catch {
    return "not_url";
  }
  if ((u.protocol !== "https:" && u.protocol !== "http:") || !u.hostname || text.includes(" "))
    return "not_url";
  const host = u.hostname.toLowerCase().replace(/\.$/, "");
  if (FILE_SHARE_DOMAINS.some((d) => host === d || host.endsWith(`.${d}`))) return "file_share";
  if (host.endsWith(".live.com") && /onedrive|skydrive|redeem|resid/i.test(text)) return "file_share";
  if ([...u.searchParams.keys()].some((k) => SHARE_PARAMS.has(k.toLowerCase()))) return "file_share";
  let path = u.pathname;
  try {
    path = decodeURIComponent(path);
  } catch {
    // keep it encoded
  }
  if (SHARE_PATH.test(path)) return "file_share";
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
  // A pasted file-share link is said at once; a half-typed address once the field is left.
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
