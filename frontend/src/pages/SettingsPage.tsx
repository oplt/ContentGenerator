import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { getSocialAccounts, upsertSocialAccount, type SocialAccountUpsertPayload } from "../api/publishing";
import { getTelegramSettings, getTenantSettings, getWhatsAppSettings, registerTelegramWebhook, updateTelegramSettings, updateTenantSettings, updateWhatsAppSettings } from "../api/settings";
import { SocialPlatformSettingsCard, type SocialPlatformConfigField } from "../components/dashboard/SocialPlatformSettingsCard";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { LoadingState } from "../components/ui/LoadingState";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { queryClient } from "../lib/queryClient";

type WorkspaceSettingsForm = {
  name: string;
  timezone: string;
};

type WorkflowSettingsForm = {
  approval_sender_label: string;
  publishing_default_timezone: string;
  publishing_default_dry_run: string;
  ingestion_default_polling_interval_minutes: string;
};

type WhatsAppSettingsForm = {
  recipient: string;
  provider: string;
  phone_number_id: string;
  business_account_id: string;
  verify_token: string;
  access_token: string;
  app_secret: string;
};

type TelegramSettingsForm = {
  bot_token: string;
  chat_id: string;
  enabled: boolean;
};

type SocialPlatformDefinition = {
  platform: string;
  label: string;
  description: string;
  configFields: SocialPlatformConfigField[];
};

const WHATSAPP_CONFIG_VARIABLES = [
  { key: "recipient", label: "Approval Recipient", description: "Default phone number that receives draft approvals in E.164 format." },
  { key: "provider", label: "Provider Mode", description: "Use stub for local development or Meta Cloud API for live WhatsApp delivery." },
  { key: "phone_number_id", label: "Phone Number ID", description: "Meta Cloud API phone number identifier used for outbound messages." },
  { key: "business_account_id", label: "Business Account ID", description: "Optional Meta business account ID used for operator context and support flows." },
  { key: "verify_token", label: "Verify Token", description: "Webhook verification token configured in the Meta developer console." },
  { key: "access_token", label: "Access Token", description: "Long-lived Meta access token used for WhatsApp Cloud API calls." },
  { key: "app_secret", label: "App Secret", description: "Meta app secret used to verify inbound webhook signatures." },
];

const SOCIAL_PLATFORM_DEFINITIONS: SocialPlatformDefinition[] = [
  {
    platform: "youtube",
    label: "YouTube",
    description:
      "Configure your channel publishing identifiers and OAuth client values for long-form and Shorts distribution.",
    configFields: [
      { key: "channel_id", label: "Channel ID", placeholder: "UC...", description: "Target YouTube channel identifier." },
      { key: "client_id", label: "Client ID", placeholder: "Google OAuth client ID", description: "Google OAuth client identifier for YouTube publishing." },
      { key: "client_secret", label: "Client Secret", placeholder: "Google OAuth client secret", description: "OAuth secret paired with the YouTube client ID.", secret: true },
    ],
  },
  {
    platform: "instagram",
    label: "Instagram",
    description:
      "Manage the Instagram Business / Meta app values required for captioned image or reel delivery.",
    configFields: [
      { key: "business_account_id", label: "Business Account ID", placeholder: "1784...", description: "Instagram Business account identifier tied to Meta publishing." },
      { key: "app_id", label: "App ID", placeholder: "Meta app ID", description: "Meta app ID used for Instagram Graph permissions." },
      { key: "app_secret", label: "App Secret", placeholder: "Meta app secret", description: "Meta app secret for server-side token exchange.", secret: true },
    ],
  },
  {
    platform: "tiktok",
    label: "TikTok",
    description:
      "Store the TikTok developer identifiers needed for video publishing and account-scoped authorization.",
    configFields: [
      { key: "open_id", label: "Open ID", placeholder: "TikTok open ID", description: "Account-level TikTok Open Platform identifier." },
      { key: "client_key", label: "Client Key", placeholder: "TikTok client key", description: "TikTok client key used by the app integration." },
      { key: "client_secret", label: "Client Secret", placeholder: "TikTok client secret", description: "TikTok app secret for token exchange.", secret: true },
    ],
  },
  {
    platform: "x",
    label: "X",
    description:
      "Manage X account and app credentials for text, media upload, and API v2 / legacy token workflows.",
    configFields: [
      { key: "user_id", label: "User ID", placeholder: "Numeric X user ID", description: "The numeric account ID that publishing jobs will target." },
      { key: "client_id", label: "Client ID", placeholder: "X OAuth client ID", description: "OAuth 2 client identifier for your X application." },
      { key: "client_secret", label: "Client Secret", placeholder: "X OAuth client secret", description: "OAuth 2 secret paired with the X app.", secret: true },
      { key: "access_token_secret", label: "Access Token Secret", placeholder: "Legacy token secret", description: "Needed when the account uses X OAuth 1.0a style publishing.", secret: true },
    ],
  },
  {
    platform: "bluesky",
    label: "Bluesky",
    description:
      "Store your Bluesky handle and app-password style configuration for authenticated posting.",
    configFields: [
      { key: "identifier", label: "Identifier", placeholder: "handle.bsky.social", description: "Bluesky handle or DID used for login." },
      { key: "app_password", label: "App Password", placeholder: "Bluesky app password", description: "App password used for authenticated posting.", secret: true },
      { key: "pds_host", label: "PDS Host", placeholder: "https://bsky.social", description: "Optional custom PDS host if you are not using the default." },
    ],
  },
];

export default function SettingsPage() {
  const [savingPlatform, setSavingPlatform] = useState<string | null>(null);
  const tenantSettings = useQuery({ queryKey: ["tenant-settings"], queryFn: getTenantSettings });
  const whatsappSettings = useQuery({
    queryKey: ["settings", "whatsapp"],
    queryFn: getWhatsAppSettings,
  });
  const telegramSettings = useQuery({
    queryKey: ["settings", "telegram"],
    queryFn: getTelegramSettings,
  });
  const socialAccounts = useQuery({
    queryKey: ["publishing", "social-accounts"],
    queryFn: getSocialAccounts,
  });

  const workspaceForm = useForm<WorkspaceSettingsForm>({
    defaultValues: { name: "", timezone: "UTC" },
  });
  const workflowForm = useForm<WorkflowSettingsForm>({
    defaultValues: {
      approval_sender_label: "",
      publishing_default_timezone: "UTC",
      publishing_default_dry_run: "true",
      ingestion_default_polling_interval_minutes: "30",
    },
  });
  const whatsappForm = useForm<WhatsAppSettingsForm>({
    defaultValues: {
      recipient: "",
      provider: "stub",
      phone_number_id: "",
      business_account_id: "",
      verify_token: "",
      access_token: "",
      app_secret: "",
    },
  });
  const telegramForm = useForm<TelegramSettingsForm>({
    defaultValues: { bot_token: "", chat_id: "", enabled: false },
  });

  useEffect(() => {
    if (!tenantSettings.data) {
      return;
    }
    workspaceForm.reset({
      name: tenantSettings.data.name,
      timezone: tenantSettings.data.timezone,
    });
    workflowForm.reset({
      approval_sender_label: tenantSettings.data.settings["approval.sender_label"] ?? "",
      publishing_default_timezone:
        tenantSettings.data.settings["publishing.default_timezone"] ?? tenantSettings.data.timezone,
      publishing_default_dry_run:
        tenantSettings.data.settings["publishing.default_dry_run"] ?? "true",
      ingestion_default_polling_interval_minutes:
        tenantSettings.data.settings["ingestion.default_polling_interval_minutes"] ?? "30",
    });
  }, [tenantSettings.data, workflowForm, workspaceForm]);

  useEffect(() => {
    if (!whatsappSettings.data) {
      return;
    }
    whatsappForm.reset({
      recipient: whatsappSettings.data.recipient ?? "",
      provider: whatsappSettings.data.provider || "stub",
      phone_number_id: whatsappSettings.data.phone_number_id ?? "",
      business_account_id: whatsappSettings.data.business_account_id ?? "",
      verify_token: whatsappSettings.data.verify_token ?? "",
      access_token: "",
      app_secret: "",
    });
  }, [whatsappForm, whatsappSettings.data]);

  useEffect(() => {
    if (!telegramSettings.data) return;
    telegramForm.reset({
      bot_token: "",
      chat_id: telegramSettings.data.chat_id,
      enabled: telegramSettings.data.enabled,
    });
  }, [telegramForm, telegramSettings.data]);

  const tenantMutation = useMutation({
    mutationFn: updateTenantSettings,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["tenant-settings"] });
    },
  });

  const whatsappMutation = useMutation({
    mutationFn: updateWhatsAppSettings,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["settings", "whatsapp"] });
    },
  });

  const telegramMutation = useMutation({
    mutationFn: updateTelegramSettings,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["settings", "telegram"] });
    },
  });
  const registerWebhookMutation = useMutation({ mutationFn: registerTelegramWebhook });

  const socialMutation = useMutation({
    mutationFn: upsertSocialAccount,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["publishing", "social-accounts"] });
    },
  });

  const defaultSocialPlatform = useMemo(
    () => socialAccounts.data?.[0]?.platform ?? SOCIAL_PLATFORM_DEFINITIONS[0].platform,
    [socialAccounts.data]
  );
  const whatsappProvider = whatsappForm.watch("provider");

  if (
    tenantSettings.isLoading ||
    whatsappSettings.isLoading ||
    telegramSettings.isLoading ||
    socialAccounts.isLoading ||
    !tenantSettings.data ||
    !whatsappSettings.data
  ) {
    return <LoadingState label="Loading settings" />;
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Settings</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Manage workspace defaults, approval delivery, and social media account connections from one place.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="muted">{tenantSettings.data.slug}</Badge>
            <Badge variant="default">{tenantSettings.data.plan_tier}</Badge>
            <Badge variant={tenantSettings.data.status === "active" ? "success" : "warning"}>
              {tenantSettings.data.status}
            </Badge>
          </div>
        </div>
      </Card>

      <Tabs defaultValue="general" className="space-y-6">
        <TabsList className="grid w-full grid-cols-2 gap-2 md:grid-cols-5">
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="workflow">Workflow</TabsTrigger>
          <TabsTrigger value="whatsapp">WhatsApp</TabsTrigger>
          <TabsTrigger value="telegram">Telegram</TabsTrigger>
          <TabsTrigger value="social">Social Media</TabsTrigger>
        </TabsList>

        <TabsContent value="general" className="space-y-6">
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
              <Button type="submit" className="md:col-span-2" disabled={tenantMutation.isPending}>
                Save Workspace Settings
              </Button>
            </form>
          </Card>
        </TabsContent>

        <TabsContent value="workflow" className="space-y-6">
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
                <p className="font-medium">WhatsApp routing moved</p>
                <p className="mt-1 text-muted-foreground">
                  Manage the approval recipient and optional Meta Cloud API credentials under the WhatsApp tab.
                </p>
              </div>
              <Button type="submit" className="md:col-span-2" disabled={tenantMutation.isPending}>
                Save Workflow Defaults
              </Button>
            </form>
          </Card>
        </TabsContent>

        <TabsContent value="whatsapp" className="space-y-6">
          <Card className="space-y-6 p-6">
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div>
                <h2 className="text-xl font-semibold">WhatsApp Approval Delivery</h2>
                <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
                  Content approvals are sent to this tenant-level WhatsApp recipient automatically whenever a draft is ready.
                  Switch to Meta Cloud API only when you have the required provider credentials configured.
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
                    Stub is safe for local development. Meta mode sends real WhatsApp messages and verifies webhook signatures.
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
                <Input type="password" placeholder="Meta Cloud API access token" {...whatsappForm.register("access_token")} />
                <p className="text-xs text-muted-foreground">
                  {whatsappSettings.data.access_token_configured ? "A tenant access token is already stored." : "No tenant access token is stored yet."}
                </p>
              </label>
              <label className="space-y-2 text-sm">
                <span className="font-medium">App secret</span>
                <Input type="password" placeholder="Meta app secret" {...whatsappForm.register("app_secret")} />
                <p className="text-xs text-muted-foreground">
                  {whatsappSettings.data.app_secret_configured ? "A tenant app secret is already stored." : "No tenant app secret is stored yet."}
                </p>
              </label>
              <Button type="submit" className="md:col-span-2" disabled={whatsappMutation.isPending}>
                {whatsappMutation.isPending ? "Saving WhatsApp Settings..." : "Save WhatsApp Settings"}
              </Button>
            </form>
          </Card>
        </TabsContent>

        <TabsContent value="telegram" className="space-y-6">
          <Card className="p-6">
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div>
                <h2 className="text-xl font-semibold">Telegram Approval Delivery</h2>
                <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
                  Send content approval notifications to a Telegram chat. Create a bot via
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
                  chat_id: values.chat_id || undefined,
                  enabled: values.enabled,
                });
              })}
            >
              <label className="space-y-2 text-sm">
                <span className="font-medium">Bot Token</span>
                <Input
                  type="password"
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
                onClick={() => registerWebhookMutation.mutate()}
              >
                {registerWebhookMutation.isPending ? "Registering…" : "Register Webhook"}
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
            </form>
          </Card>
        </TabsContent>

        <TabsContent value="social" className="space-y-6">
          <Card className="p-6">
            <h2 className="text-xl font-semibold">Social Media Connections</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Connect each destination account here. Provider-specific configuration variables are grouped under the platform that uses them.
            </p>
          </Card>

          <Tabs defaultValue={defaultSocialPlatform} className="space-y-6">
            <TabsList className="grid w-full grid-cols-2 gap-2 md:grid-cols-5">
              {SOCIAL_PLATFORM_DEFINITIONS.map((definition) => (
                <TabsTrigger key={definition.platform} value={definition.platform}>
                  {definition.label}
                </TabsTrigger>
              ))}
            </TabsList>

            {SOCIAL_PLATFORM_DEFINITIONS.map((definition) => {
              const account = socialAccounts.data?.find((item) => item.platform === definition.platform);

              return (
                <TabsContent key={definition.platform} value={definition.platform}>
                  <SocialPlatformSettingsCard
                    platform={definition.platform}
                    label={definition.label}
                    description={definition.description}
                    account={account}
                    configFields={definition.configFields}
                    isSaving={savingPlatform === definition.platform && socialMutation.isPending}
                    onSave={async (payload: SocialAccountUpsertPayload) => {
                      setSavingPlatform(definition.platform);
                      try {
                        await socialMutation.mutateAsync(payload);
                      } finally {
                        setSavingPlatform(null);
                      }
                    }}
                  />
                </TabsContent>
              );
            })}
          </Tabs>
        </TabsContent>
      </Tabs>
    </div>
  );
}
