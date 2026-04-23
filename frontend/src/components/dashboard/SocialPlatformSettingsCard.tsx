import { useEffect, useState } from "react";
import type { SocialAccount, SocialAccountUpsertPayload } from "../../api/publishing";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import { Input } from "../ui/input";
import { PasswordInput } from "../ui/PasswordInput";

export type SocialPlatformConfigField = {
  key: string;
  label: string;
  placeholder: string;
  description: string;
  secret?: boolean;
};

export type AccessTokenConfig = {
  label: string;
  placeholder: string;
  description?: string;
};

type SocialPlatformSettingsCardProps = {
  platform: string;
  label: string;
  description: string;
  account?: SocialAccount;
  configFields: SocialPlatformConfigField[];
  hiddenFields?: string[];
  accessTokenConfig?: AccessTokenConfig;
  isSaving: boolean;
  onSave: (payload: SocialAccountUpsertPayload) => Promise<unknown>;
};

type PlatformFormState = {
  displayName: string;
  handle: string;
  accountExternalId: string;
  accessToken: string;
  accessTokenSecretRef: string;
  refreshToken: string;
  scopesCsv: string;
  useStub: boolean;
  metadata: Record<string, string>;
};

function buildInitialState(
  account: SocialAccount | undefined,
  label: string,
  configFields: SocialPlatformConfigField[]
): PlatformFormState {
  const metadata = Object.fromEntries(
    configFields.map((field) => [field.key, account?.metadata[field.key] ?? ""])
  );

  return {
    displayName: account?.display_name ?? label,
    handle: account?.handle ?? "",
    accountExternalId: account?.account_external_id ?? "",
    accessToken: "",
    accessTokenSecretRef: "",
    refreshToken: "",
    scopesCsv: "",
    // For an existing account respect the saved mode; new accounts default to real
    useStub: account ? account.metadata.mode !== "real" : false,
    metadata,
  };
}

function toOptionalString(value: string) {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function toScopes(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function SocialPlatformSettingsCard({
  platform,
  label,
  description,
  account,
  configFields,
  hiddenFields = [],
  accessTokenConfig,
  isSaving,
  onSave,
}: SocialPlatformSettingsCardProps) {
  const hide = (field: string) => hiddenFields.includes(field);
  const tokenLabel = accessTokenConfig?.label ?? "Access token";
  const tokenPlaceholder = accessTokenConfig?.placeholder ?? "Optional access token";
  const tokenDescription = accessTokenConfig?.description;
  const [state, setState] = useState<PlatformFormState>(() => buildInitialState(account, label, configFields));

  useEffect(() => {
    setState(buildInitialState(account, label, configFields));
  }, [account, configFields, label]);

  const extraMetadata = Object.fromEntries(
    Object.entries(account?.metadata ?? {}).filter(
      ([key]) => key !== "mode" && !configFields.some((field) => field.key === key)
    )
  );

  return (
    <Card className="space-y-6 p-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-semibold">{label}</h2>
            <Badge variant={account ? (account.metadata.mode === "stub" ? "warning" : "success") : "muted"}>
              {account ? account.metadata.mode ?? account.status : "not connected"}
            </Badge>
          </div>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{description}</p>
        </div>
        {account ? (
          <div className="inset-panel px-4 py-3 text-sm">
            <p className="font-medium">{account.display_name}</p>
            <p className="mt-1 text-muted-foreground">{account.handle ?? "No handle configured"}</p>
          </div>
        ) : null}
      </div>

      {configFields.length > 0 && (
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Provider Config Variables
          </h3>
          <div className="flex flex-wrap gap-2">
            {configFields.map((field) => (
              <Badge key={field.key} variant="muted" className="font-mono normal-case tracking-normal">
                {field.key}
              </Badge>
            ))}
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {configFields.map((field) => (
            <label key={field.key} className="space-y-2 text-sm">
              <span className="font-medium">{field.label}</span>
              {field.secret ? (
                <PasswordInput
                  placeholder={field.placeholder}
                  value={state.metadata[field.key] ?? ""}
                  onChange={(event) =>
                    setState((current) => ({
                      ...current,
                      metadata: { ...current.metadata, [field.key]: event.target.value },
                    }))
                  }
                />
              ) : (
                <Input
                  placeholder={field.placeholder}
                  value={state.metadata[field.key] ?? ""}
                  onChange={(event) =>
                    setState((current) => ({
                      ...current,
                      metadata: { ...current.metadata, [field.key]: event.target.value },
                    }))
                  }
                />
              )}
              <p className="text-xs text-muted-foreground">{field.description}</p>
            </label>
          ))}
        </div>
      </div>
      )}

      <form
        className="grid gap-4 md:grid-cols-2"
        onSubmit={async (event) => {
          event.preventDefault();
          await onSave({
            platform,
            display_name: state.displayName.trim() || label,
            handle: toOptionalString(state.handle),
            account_external_id: toOptionalString(state.accountExternalId),
            access_token: toOptionalString(state.accessToken),
            access_token_secret_ref: toOptionalString(state.accessTokenSecretRef),
            refresh_token: toOptionalString(state.refreshToken),
            scopes: toScopes(state.scopesCsv),
            metadata: { ...extraMetadata, ...state.metadata },
            use_stub: state.useStub,
          });
        }}
      >
        <label className="space-y-2 text-sm">
          <span className="font-medium">Display name</span>
          <Input
            placeholder={`${label} workspace`}
            value={state.displayName}
            onChange={(event) => setState((current) => ({ ...current, displayName: event.target.value }))}
          />
        </label>
        <label className="space-y-2 text-sm">
          <span className="font-medium">Handle</span>
          <Input
            placeholder="@yourhandle"
            value={state.handle}
            onChange={(event) => setState((current) => ({ ...current, handle: event.target.value }))}
          />
        </label>
        {!hide("accountExternalId") && (
        <label className="space-y-2 text-sm">
          <span className="font-medium">External account ID</span>
          <Input
            placeholder="Platform-specific account or channel ID"
            value={state.accountExternalId}
            onChange={(event) =>
              setState((current) => ({ ...current, accountExternalId: event.target.value }))
            }
          />
        </label>
        )}
        {!hide("scopesCsv") && (
        <label className="space-y-2 text-sm">
          <span className="font-medium">Scopes</span>
          <Input
            placeholder="Comma separated scopes"
            value={state.scopesCsv}
            onChange={(event) => setState((current) => ({ ...current, scopesCsv: event.target.value }))}
          />
        </label>
        )}
        <label className="space-y-2 text-sm">
          <span className="font-medium">{tokenLabel}</span>
          <PasswordInput
            placeholder={tokenPlaceholder}
            value={state.accessToken}
            onChange={(event) => setState((current) => ({ ...current, accessToken: event.target.value }))}
          />
          {tokenDescription && (
            <p className="text-xs text-muted-foreground">{tokenDescription}</p>
          )}
        </label>
        {!hide("refreshToken") && (
        <label className="space-y-2 text-sm">
          <span className="font-medium">Refresh token</span>
          <PasswordInput
            placeholder="Optional refresh token"
            value={state.refreshToken}
            onChange={(event) => setState((current) => ({ ...current, refreshToken: event.target.value }))}
          />
        </label>
        )}
        {!hide("accessTokenSecretRef") && (
        <label className="space-y-2 text-sm md:col-span-2">
          <span className="font-medium">Access token secret reference</span>
          <Input
            placeholder="vault://platform/account/access-token"
            value={state.accessTokenSecretRef}
            onChange={(event) =>
              setState((current) => ({ ...current, accessTokenSecretRef: event.target.value }))
            }
          />
          <p className="text-xs text-muted-foreground">
            Optional external secret reference. Use this instead of storing a live platform token directly in the database.
          </p>
        </label>
        )}

        <div className="space-y-3 md:col-span-2">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm font-medium">Connection mode</span>
            <Button
              type="button"
              variant={state.useStub ? "default" : "outline"}
              size="sm"
              onClick={() => setState((current) => ({ ...current, useStub: true }))}
            >
              Stub
            </Button>
            <Button
              type="button"
              variant={state.useStub ? "outline" : "default"}
              size="sm"
              onClick={() => setState((current) => ({ ...current, useStub: false }))}
            >
              Manual / Live
            </Button>
            <p className="text-sm text-muted-foreground">
              Stub mode enables safe local publishing. Manual / Live mode stores credentials for real provider setup.
            </p>
          </div>
          <Button type="submit" disabled={isSaving}>
            {isSaving ? `Saving ${label}...` : `Save ${label} Connection`}
          </Button>
        </div>
      </form>
    </Card>
  );
}
