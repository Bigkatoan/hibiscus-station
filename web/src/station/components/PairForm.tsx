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

/** Pair with a Hibiscus server (§4.8): server URL + personal access token. */
export function PairForm({ onPaired }: { onPaired?: () => void }) {
  const { t } = useTranslation("station");
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const pair = useStationMutation(
    (body: { url: string; token: string }) => api.post<ServerLink>("/server/pair", body),
    [qk.server, qk.status],
  );
  const link = tokenUrl(url);
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
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
      <Field label={t("pair.url")} required>
        <Input
          type="url"
          value={url}
          placeholder="https://hibiscus.example.org"
          onChange={(e) => {
            setUrl(e.target.value);
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
      <Button type="submit" className="self-start" disabled={!url.trim() || !token.trim() || pair.isPending}>
        {t("pair.submit")}
      </Button>
    </form>
  );
}
