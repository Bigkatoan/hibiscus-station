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

/** File-sharing sites whose links people paste instead of the server address (field report 0.2.9). */
const FILE_SHARE_HOSTS = [
  "onedrive.live.com",
  "onedrive.com",
  "1drv.ms",
  "sharepoint.com",
  "drive.google.com",
  "docs.google.com",
  "dropbox.com",
  "dropboxusercontent.com",
  "db.tt",
];

export type ServerUrlProblem = "not_url" | "file_share";

/**
 * Why `raw` cannot be a Hibiscus server address, or null when it can (D-25): it must be an
 * http(s) URL, and not a OneDrive / SharePoint / Google Drive / Dropbox link.
 */
export function serverUrlProblem(raw: string): ServerUrlProblem | null {
  let u: URL;
  try {
    u = new URL(raw.trim());
  } catch {
    return "not_url";
  }
  if ((u.protocol !== "https:" && u.protocol !== "http:") || !u.hostname) return "not_url";
  const host = u.hostname.toLowerCase().replace(/\.$/, "");
  if (FILE_SHARE_HOSTS.some((d) => host === d || host.endsWith(`.${d}`))) return "file_share";
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
