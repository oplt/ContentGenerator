import type { UseFormReturn } from "react-hook-form";
import type { UseMutationResult } from "@tanstack/react-query";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { PasswordInput } from "../../components/ui/PasswordInput";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../components/ui/tabs";
import { SocialConnectionsPanel } from "./SocialConnectionsPanel";
import {
  WHATSAPP_CONFIG_VARIABLES,
  type SettingsTab,
  type TelegramSettingsForm,
  type WhatsAppSettingsForm,
  type WorkflowSettingsForm,
  type WorkspaceSettingsForm,
} from "./constants";

type SettingsWorkspaceTabsProps = {
  settingsTab: SettingsTab;
  setSettingsTab: (tab: SettingsTab) => void;
  workspaceForm: UseFormReturn<WorkspaceSettingsForm>;
  workflowForm: UseFormReturn<WorkflowSettingsForm>;
  whatsappForm: UseFormReturn<WhatsAppSettingsForm>;
  telegramForm: UseFormReturn<TelegramSettingsForm>;
  tenantMutation: UseMutationResult<any, any, any, any>;
  whatsappMutation: UseMutationResult<any, any, any, any>;
  telegramMutation: UseMutationResult<any, any, any, any>;
  socialMutation: UseMutationResult<any, any, any, any>;
  registerWebhookMutation: UseMutationResult<any, any, any, any>;
  sendTelegramDigestTestMutation: UseMutationResult<any, any, any, any>;
  tenantSettings: any;
  whatsappSettings: any;
  telegramSettings: any;
  socialAccounts: any;
  whatsappProvider: string;
  activeMembership: any;
  defaultSocialPlatform: string;
  savingPlatform: string | null;
  setSavingPlatform: (platform: string | null) => void;
};

export function SettingsWorkspaceTabs({
  settingsTab,
  setSettingsTab,
  workspaceForm,
  workflowForm,
  whatsappForm,
  telegramForm,
  tenantMutation,
  whatsappMutation,
  telegramMutation,
  socialMutation,
  registerWebhookMutation,
  sendTelegramDigestTestMutation,
  tenantSettings,
  whatsappSettings,
  telegramSettings,
  socialAccounts,
  whatsappProvider,
  activeMembership,
  defaultSocialPlatform,
  savingPlatform,
  setSavingPlatform,
}: SettingsWorkspaceTabsProps) {
  return (
      <Tabs value={settingsTab} onValueChange={(value) => setSettingsTab(value as SettingsTab)} className="space-y-6">
        <TabsList className="grid w-full grid-cols-2 gap-2 md:grid-cols-5">
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="workflow">Workflow</TabsTrigger>
          <TabsTrigger value="whatsapp">WhatsApp</TabsTrigger>
          <TabsTrigger value="telegram">Telegram</TabsTrigger>
          <TabsTrigger value="social">Social Media</TabsTrigger>
        </TabsList>

        <TabsContent value="general" className="space-y-6" forceMount hidden={settingsTab !== "general"}>
          <Card className="p-6">
            <h2 className="text-xl font-semibold">Workspace Defaults</h2>
            <form
              className="mt-5 grid gap-4 md:max-w-2xl md:grid-cols-2"
              onSubmit={workspaceForm.handleSubmit(async (values) => {
                await tenantMutation.mutateAsync({
                  name: values.name,
                  timezone: values.timezone,
                  settings: {},
                });
              })}
            >
              <label className="space-y-2 text-sm">
                <span className="font-medium">Workspace name</span>
                <Input placeholder="Workspace name" {...workspaceForm.register("name")} />
              </label>
              <label className="space-y-2 text-sm">
                <span className="font-medium">Timezone</span>
                <Input placeholder="Europe/Brussels" {...workspaceForm.register("timezone")} />
              </label>
              <div className="grid gap-3 rounded-2xl border border-border bg-muted/40 p-4 text-sm md:col-span-2 md:grid-cols-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Slug</p>
                  <p className="mt-2 font-medium">{tenantSettings.data.slug}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Plan</p>
                  <p className="mt-2 font-medium">{tenantSettings.data.plan_tier}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Status</p>
                  <p className="mt-2 font-medium">{tenantSettings.data.status}</p>
                </div>
              </div>
              <div className="grid gap-3 rounded-2xl border border-border bg-muted/40 p-4 text-sm md:col-span-2 md:grid-cols-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">RBAC Mode</p>
                  <p className="mt-2 font-medium">{tenantSettings.data.rbac_mode}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Active Role</p>
                  <p className="mt-2 font-medium">{activeMembership?.role?.name ?? "Workspace operator"}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Permission Count</p>
                  <p className="mt-2 font-medium">{activeMembership?.role?.permission_codes.length ?? 0}</p>
                </div>
                <div className="md:col-span-3">
                  <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Permission Placeholders</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {(activeMembership?.role?.permission_codes ?? []).length > 0 ? (
                      (activeMembership?.role?.permission_codes ?? []).map((code: string) => (
                        <Badge key={code} variant="muted" className="font-mono normal-case tracking-normal">
                          {code}
                        </Badge>
                      ))
                    ) : (
                      <span className="text-muted-foreground">
                        No explicit permission codes are assigned yet. API and UI are exposing the placeholder contract now.
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <Button type="submit" className="md:col-span-2" disabled={tenantMutation.isPending}>
                Save Workspace Settings
              </Button>
            </form>
          </Card>
        </TabsContent>

        <TabsContent value="workflow" className="space-y-6" forceMount hidden={settingsTab !== "workflow"}>
          <Card className="p-6">
            <h2 className="text-xl font-semibold">Approval and Publishing Defaults</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              These workspace-level values control sender labels and publish defaults used across the tenant.
            </p>
            <form
              className="mt-5 grid gap-4 md:grid-cols-2"
              onSubmit={workflowForm.handleSubmit(async (values) => {
                await tenantMutation.mutateAsync({
                  settings: {
                    "approval.sender_label": values.approval_sender_label,
                    "publishing.default_timezone": values.publishing_default_timezone,
                    "publishing.default_dry_run": values.publishing_default_dry_run,
                    "ingestion.default_polling_interval_minutes": values.ingestion_default_polling_interval_minutes,
                  },
                });
              })}
            >
              <label className="space-y-2 text-sm">
                <span className="font-medium">Approval sender label</span>
                <Input placeholder="SignalForge Ops" {...workflowForm.register("approval_sender_label")} />
              </label>
              <label className="space-y-2 text-sm">
                <span className="font-medium">Default publish timezone</span>
                <Input placeholder="UTC" {...workflowForm.register("publishing_default_timezone")} />
              </label>
              <label className="space-y-2 text-sm">
                <span className="font-medium">Default dry run</span>
                <Input placeholder="true or false" {...workflowForm.register("publishing_default_dry_run")} />
              </label>
              <label className="space-y-2 text-sm">
                <span className="font-medium">Source update interval (minutes)</span>
                <Input
                  type="number"
                  min={5}
                  max={1440}
                  placeholder="30"
                  {...workflowForm.register("ingestion_default_polling_interval_minutes")}
                />
                <p className="text-xs text-muted-foreground">
                  Default polling interval applied when creating new sources. Existing sources keep their own interval.
                </p>
              </label>
              <div className="rounded-2xl border border-border bg-muted/40 p-4 text-sm md:col-span-2">
                <p className="font-medium">Telegram is the primary approval channel</p>
                <p className="mt-1 text-muted-foreground">
                  Configure Telegram for topic, brief, asset, and publish approvals. Keep WhatsApp only as a legacy or fallback delivery path.
                </p>
              </div>
              <Button type="submit" className="md:col-span-2" disabled={tenantMutation.isPending}>
                Save Workflow Defaults
              </Button>
            </form>
          </Card>
        </TabsContent>

        <TabsContent value="whatsapp" className="space-y-6" forceMount hidden={settingsTab !== "whatsapp"}>
          <Card className="space-y-6 p-6">
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div>
                <h2 className="text-xl font-semibold">Legacy WhatsApp Delivery</h2>
                <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
                  Telegram is the primary editorial approval channel. Use WhatsApp only when you need a secondary operator delivery path or an older tenant workflow.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant={whatsappSettings.data.provider === "meta" ? "success" : "muted"}>
                  {whatsappSettings.data.provider === "meta" ? "Meta Cloud API" : "Stub Provider"}
                </Badge>
                <Badge variant={whatsappSettings.data.using_tenant_recipient ? "success" : "muted"}>
                  {whatsappSettings.data.using_tenant_recipient ? "Tenant recipient" : "Global recipient fallback"}
                </Badge>
                <Badge variant={whatsappSettings.data.using_tenant_credentials ? "success" : "muted"}>
                  {whatsappSettings.data.using_tenant_credentials ? "Tenant credentials" : "Global credentials fallback"}
                </Badge>
              </div>
            </div>

            <div className="grid gap-3 rounded-2xl border border-border bg-muted/40 p-4 text-sm md:grid-cols-3">
              <div>
                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Recipient</p>
                <p className="mt-2 font-medium">{whatsappSettings.data.recipient || "Not configured"}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Access Token</p>
                <p className="mt-2 font-medium">
                  {whatsappSettings.data.access_token_configured ? "Configured" : "Not configured"}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">App Secret</p>
                <p className="mt-2 font-medium">
                  {whatsappSettings.data.app_secret_configured ? "Configured" : "Not configured"}
                </p>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  Managed Variables
                </h3>
                <div className="flex flex-wrap gap-2">
                  {WHATSAPP_CONFIG_VARIABLES.map((field) => (
                    <Badge key={field.key} variant="muted" className="font-mono normal-case tracking-normal">
                      {field.key}
                    </Badge>
                  ))}
                </div>
              </div>
              <p className="text-sm text-muted-foreground">
                Leave sensitive fields blank when you do not want to change them. Submitting an empty value for a secret clears
                the stored tenant override and falls back to the global environment config.
              </p>
            </div>

            <form
              className="grid gap-4 md:grid-cols-2"
              onSubmit={whatsappForm.handleSubmit(async (values) => {
                await whatsappMutation.mutateAsync(values);
              })}
            >
              <div className="space-y-3 md:col-span-2">
                <span className="text-sm font-medium">Provider mode</span>
                <div className="flex flex-wrap items-center gap-3">
                  <Button
                    type="button"
                    variant={whatsappProvider === "stub" ? "default" : "outline"}
                    size="sm"
                    onClick={() => whatsappForm.setValue("provider", "stub", { shouldDirty: true })}
                  >
                    Stub
                  </Button>
                  <Button
                    type="button"
                    variant={whatsappProvider === "meta" ? "default" : "outline"}
                    size="sm"
                    onClick={() => whatsappForm.setValue("provider", "meta", { shouldDirty: true })}
                  >
                    Meta Cloud API
                  </Button>
                  <p className="text-sm text-muted-foreground">
                    Stub is safe for local development. Meta mode sends real WhatsApp messages only for legacy fallback workflows.
                  </p>
                </div>
              </div>

              <label className="space-y-2 text-sm">
                <span className="font-medium">Approval recipient</span>
                <Input placeholder="+15551234567" {...whatsappForm.register("recipient")} />
                <p className="text-xs text-muted-foreground">
                  This number is used automatically when approval requests are created without an explicit recipient.
                </p>
              </label>
              <label className="space-y-2 text-sm">
                <span className="font-medium">Verify token</span>
                <Input placeholder="meta-webhook-verify-token" {...whatsappForm.register("verify_token")} />
                <p className="text-xs text-muted-foreground">
                  Configure the same token in the Meta webhook subscription screen.
                </p>
              </label>
              <label className="space-y-2 text-sm">
                <span className="font-medium">Phone number ID</span>
                <Input placeholder="123456789012345" {...whatsappForm.register("phone_number_id")} />
                <p className="text-xs text-muted-foreground">
                  Required for outbound messages when Meta Cloud API mode is enabled.
                </p>
              </label>
              <label className="space-y-2 text-sm">
                <span className="font-medium">Business account ID</span>
                <Input placeholder="987654321098765" {...whatsappForm.register("business_account_id")} />
                <p className="text-xs text-muted-foreground">
                  Optional but useful when operating multiple Meta business accounts.
                </p>
              </label>
              <label className="space-y-2 text-sm">
                <span className="font-medium">Access token</span>
                <PasswordInput placeholder="Meta Cloud API access token" {...whatsappForm.register("access_token")} />
                <p className="text-xs text-muted-foreground">
                  {whatsappSettings.data.access_token_configured ? "A tenant access token is already stored." : "No tenant access token is stored yet."}
                </p>
              </label>
              <label className="space-y-2 text-sm">
                <span className="font-medium">Access token secret reference</span>
                <Input
                  placeholder="vault://meta/whatsapp/access-token"
                  {...whatsappForm.register("access_token_secret_ref")}
                />
                <p className="text-xs text-muted-foreground">
                  Optional external secret reference. When present, runtime delivery resolves this reference instead of using the stored tenant token.
                </p>
              </label>
              <label className="space-y-2 text-sm">
                <span className="font-medium">App secret</span>
                <PasswordInput placeholder="Meta app secret" {...whatsappForm.register("app_secret")} />
                <p className="text-xs text-muted-foreground">
                  {whatsappSettings.data.app_secret_configured ? "A tenant app secret is already stored." : "No tenant app secret is stored yet."}
                </p>
              </label>
              <label className="space-y-2 text-sm">
                <span className="font-medium">App secret reference</span>
                <Input
                  placeholder="vault://meta/whatsapp/app-secret"
                  {...whatsappForm.register("app_secret_secret_ref")}
                />
                <p className="text-xs text-muted-foreground">
                  Use this to keep the webhook verification secret in an external secret manager and only store the reference here.
                </p>
              </label>
              <Button type="submit" className="md:col-span-2" disabled={whatsappMutation.isPending}>
                {whatsappMutation.isPending ? "Saving WhatsApp Settings..." : "Save WhatsApp Settings"}
              </Button>
            </form>
          </Card>
        </TabsContent>

        <TabsContent value="telegram" className="space-y-6" forceMount hidden={settingsTab !== "telegram"}>
          <Card className="p-6">
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div>
                <h2 className="text-xl font-semibold">Telegram Editorial Approvals</h2>
                <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
                  Route topic, brief, asset, and publish approvals to a Telegram chat. Create a bot via
                  <span className="mx-1 font-mono text-xs">@BotFather</span>
                  on Telegram, then add the bot to your group or use the direct chat ID.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant={telegramSettings.data?.bot_token_configured ? "success" : "muted"}>
                  {telegramSettings.data?.bot_token_configured ? "Bot configured" : "No bot token"}
                </Badge>
                <Badge variant={telegramSettings.data?.enabled ? "success" : "muted"}>
                  {telegramSettings.data?.enabled ? "Enabled" : "Disabled"}
                </Badge>
              </div>
            </div>

            <div className="mt-6 grid gap-3 rounded-2xl border border-border bg-muted/40 p-4 text-sm md:grid-cols-3">
              <div>
                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Bot Token</p>
                <p className="mt-2 font-medium">
                  {telegramSettings.data?.bot_token_configured ? "Configured" : "Not configured"}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Chat ID</p>
                <p className="mt-2 font-medium">{telegramSettings.data?.chat_id || "Not set"}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Status</p>
                <p className="mt-2 font-medium">{telegramSettings.data?.enabled ? "Active" : "Inactive"}</p>
              </div>
            </div>

            <form
              className="mt-6 grid gap-4 md:grid-cols-2"
              onSubmit={telegramForm.handleSubmit(async (values) => {
                await telegramMutation.mutateAsync({
                  bot_token: values.bot_token || undefined,
                  bot_token_secret_ref: values.bot_token_secret_ref || undefined,
                  chat_id: values.chat_id || undefined,
                  enabled: values.enabled,
                });
              })}
            >
              <label className="space-y-2 text-sm">
                <span className="font-medium">Bot Token</span>
                <PasswordInput
                  placeholder="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
                  {...telegramForm.register("bot_token")}
                />
                <p className="text-xs text-muted-foreground">
                  {telegramSettings.data?.bot_token_configured
                    ? "A bot token is already stored. Leave blank to keep it."
                    : "Get this from @BotFather on Telegram after creating a bot."}
                </p>
              </label>
              <label className="space-y-2 text-sm">
                <span className="font-medium">Bot token secret reference</span>
                <Input
                  placeholder="vault://telegram/editorial/bot-token"
                  {...telegramForm.register("bot_token_secret_ref")}
                />
                <p className="text-xs text-muted-foreground">
                  Optional external secret reference. When set, the Telegram provider resolves the bot token from that reference at runtime.
                </p>
              </label>
              <label className="space-y-2 text-sm">
                <span className="font-medium">Chat ID</span>
                <Input
                  placeholder="-1001234567890 or @yourchannel"
                  {...telegramForm.register("chat_id")}
                />
                <p className="text-xs text-muted-foreground">
                  Use a group/channel ID (negative number) or username. Send a message to
                  <span className="mx-1 font-mono text-xs">@userinfobot</span>
                  to find your ID.
                </p>
              </label>
              <div className="flex items-center gap-3 md:col-span-2">
                <input
                  type="checkbox"
                  id="telegram-enabled"
                  className="h-4 w-4 rounded border-border accent-primary"
                  {...telegramForm.register("enabled")}
                />
                <label htmlFor="telegram-enabled" className="text-sm font-medium">
                  Enable Telegram approval notifications
                </label>
              </div>
              <Button type="submit" disabled={telegramMutation.isPending}>
                {telegramMutation.isPending ? "Saving…" : "Save Telegram Settings"}
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={registerWebhookMutation.isPending || !telegramSettings.data?.bot_token_configured}
                onClick={() => registerWebhookMutation.mutate(undefined)}
              >
                {registerWebhookMutation.isPending ? "Registering…" : "Register Webhook"}
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={
                  sendTelegramDigestTestMutation.isPending ||
                  !telegramSettings.data?.bot_token_configured ||
                  !telegramSettings.data?.chat_id ||
                  !telegramSettings.data?.enabled
                }
                onClick={() => sendTelegramDigestTestMutation.mutate(undefined)}
              >
                {sendTelegramDigestTestMutation.isPending ? "Sending…" : "Send Test Daily Digest"}
              </Button>
              {registerWebhookMutation.isSuccess && (
                <p className="text-xs text-muted-foreground md:col-span-2">
                  ✅ Webhook registered: {registerWebhookMutation.data?.webhook_url}
                </p>
              )}
              {registerWebhookMutation.isError && (
                <p className="text-xs text-destructive md:col-span-2">
                  Failed to register webhook. Make sure the bot token is saved and the server is publicly reachable.
                </p>
              )}
              {sendTelegramDigestTestMutation.isSuccess && (
                <p className="text-xs text-muted-foreground md:col-span-2">
                  ✅ Test daily digest sent to the configured Telegram chat.
                </p>
              )}
              {sendTelegramDigestTestMutation.isError && (
                <p className="text-xs text-destructive md:col-span-2">
                  Failed to send the test daily digest. Check that Telegram is enabled, the bot token is valid, the chat ID is correct, and daily repos exist.
                </p>
              )}
            </form>
          </Card>
        </TabsContent>

        <TabsContent value="social" className="space-y-6" forceMount hidden={settingsTab !== "social"}>
          <SocialConnectionsPanel
            accounts={socialAccounts.data}
            defaultPlatform={defaultSocialPlatform}
            savingPlatform={savingPlatform}
            isSaving={socialMutation.isPending}
            onSave={async (platform, payload) => {
              setSavingPlatform(platform);
              try {
                await socialMutation.mutateAsync(payload);
              } finally {
                setSavingPlatform(null);
              }
            }}
          />
        </TabsContent>
      </Tabs>
  );
}
