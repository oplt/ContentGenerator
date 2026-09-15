import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { getSocialAccounts, upsertSocialAccount } from "../api/publishing";
import {
  getTelegramSettings,
  getTenantSettings,
  getWhatsAppSettings,
  registerTelegramWebhook,
  sendTelegramDailyDigestTest,
  updateTelegramSettings,
  updateTenantSettings,
  updateWhatsAppSettings,
} from "../api/settings";
import { Badge } from "../components/ui/badge";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";
import { useAuth } from "../features/auth/AuthContext";
import { canAccessTenantSettings, getActiveMembership } from "../features/auth/access";
import { useDeepLinkTab } from "../hooks/useDeepLinkTab";
import { useTenantScope } from "../hooks/useTenantScope";
import { queryClient } from "../lib/queryClient";
import { queryKeys } from "../lib/queryKeys";
import { ErrorState } from "../components/ui/ErrorState";
import { SectionHelp } from "../components/ui/HelpDisclosure";
import { resolveQueriesStatus } from "../components/ui/QueryBoundary";
import {
  SETTINGS_TABS,
  SETTINGS_TAB_ALIASES,
  SOCIAL_PLATFORM_DEFINITIONS,
  WORKSPACE_SETTINGS_TABS,
  type SettingsTab,
  type TelegramSettingsForm,
  type WhatsAppSettingsForm,
  type WorkflowSettingsForm,
  type WorkspaceSettingsForm,
  SettingsWorkspaceTabs,
} from "../features/settings";

function isWorkspaceTab(tab: SettingsTab): boolean {
  return (WORKSPACE_SETTINGS_TABS as readonly string[]).includes(tab);
}

export default function SettingsPage() {
  const [savingPlatform, setSavingPlatform] = useState<string | null>(null);
  const [settingsTab, setSettingsTab] = useDeepLinkTab<SettingsTab>(
    "tab",
    SETTINGS_TABS,
    "account",
    SETTINGS_TAB_ALIASES,
  );
  const { currentUser } = useAuth();
  const { tenantId, enabled } = useTenantScope();
  const canManageWorkspace = canAccessTenantSettings(currentUser, tenantId);

  useEffect(() => {
    if (!canManageWorkspace && isWorkspaceTab(settingsTab)) {
      setSettingsTab("account");
    }
  }, [canManageWorkspace, settingsTab, setSettingsTab]);

  const tenantSettings = useQuery({
    queryKey: queryKeys.tenantSettings(tenantId ?? "none"),
    queryFn: getTenantSettings,
    enabled: enabled && canManageWorkspace,
  });
  const whatsappSettings = useQuery({
    queryKey: queryKeys.whatsappSettings(tenantId ?? "none"),
    queryFn: getWhatsAppSettings,
    enabled: enabled && canManageWorkspace && settingsTab === "integrations",
  });
  const telegramSettings = useQuery({
    queryKey: queryKeys.telegramSettings(tenantId ?? "none"),
    queryFn: getTelegramSettings,
    enabled: enabled && canManageWorkspace && settingsTab === "integrations",
  });
  const socialAccounts = useQuery({
    queryKey: queryKeys.socialAccounts(tenantId ?? "none"),
    queryFn: getSocialAccounts,
    enabled: enabled && canManageWorkspace && settingsTab === "social",
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
      access_token_secret_ref: "",
      app_secret: "",
      app_secret_secret_ref: "",
    },
  });
  const telegramForm = useForm<TelegramSettingsForm>({
    defaultValues: { bot_token: "", bot_token_secret_ref: "", chat_id: "", enabled: false },
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
      access_token_secret_ref: whatsappSettings.data.access_token_secret_ref ?? "",
      app_secret: "",
      app_secret_secret_ref: whatsappSettings.data.app_secret_secret_ref ?? "",
    });
  }, [whatsappForm, whatsappSettings.data]);

  useEffect(() => {
    if (!telegramSettings.data) return;
    telegramForm.reset({
      bot_token: "",
      bot_token_secret_ref: telegramSettings.data.bot_token_secret_ref ?? "",
      chat_id: telegramSettings.data.chat_id,
      enabled: telegramSettings.data.enabled,
    });
  }, [telegramForm, telegramSettings.data]);

  const activeMembership = useMemo(
    () => getActiveMembership(currentUser, tenantId),
    [currentUser, tenantId]
  );

  const tenantMutation = useMutation({
    mutationFn: updateTenantSettings,
    onSuccess: async () => {
      if (!tenantId) return;
      await queryClient.invalidateQueries({ queryKey: queryKeys.tenantSettings(tenantId) });
    },
  });

  const whatsappMutation = useMutation({
    mutationFn: updateWhatsAppSettings,
    onSuccess: async () => {
      if (!tenantId) return;
      await queryClient.invalidateQueries({ queryKey: queryKeys.whatsappSettings(tenantId) });
    },
  });

  const telegramMutation = useMutation({
    mutationFn: updateTelegramSettings,
    onSuccess: async () => {
      if (!tenantId) return;
      await queryClient.invalidateQueries({ queryKey: queryKeys.telegramSettings(tenantId) });
    },
  });
  const registerWebhookMutation = useMutation({ mutationFn: registerTelegramWebhook });
  const sendTelegramDigestTestMutation = useMutation({ mutationFn: sendTelegramDailyDigestTest });

  const socialMutation = useMutation({
    mutationFn: upsertSocialAccount,
    onSuccess: async () => {
      if (!tenantId) return;
      await queryClient.invalidateQueries({ queryKey: queryKeys.socialAccounts(tenantId) });
    },
  });

  const defaultSocialPlatform = useMemo(
    () => socialAccounts.data?.[0]?.platform ?? SOCIAL_PLATFORM_DEFINITIONS[0].platform,
    [socialAccounts.data]
  );
  const whatsappProvider = whatsappForm.watch("provider");

  if (canManageWorkspace) {
    const shellStatus = resolveQueriesStatus([tenantSettings]);
    if (shellStatus.status === "loading") {
      return <LoadingState label="Loading settings" />;
    }
    if (shellStatus.status === "error" || !tenantSettings.data) {
      return (
        <ErrorState
          message="Workspace settings could not be loaded."
          onRetry={
            shellStatus.status === "error"
              ? shellStatus.retry
              : () => {
                  void tenantSettings.refetch();
                }
          }
        />
      );
    }
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Settings</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Manage your account security
              {canManageWorkspace
                ? ", workspace defaults, approval delivery, and social connections"
                : ""}
              .
            </p>
          </div>
          {tenantSettings.data ? (
            <div className="flex flex-wrap gap-2">
              <Badge variant="muted">{tenantSettings.data.slug}</Badge>
              <Badge variant="default">{tenantSettings.data.plan_tier}</Badge>
              <Badge variant={tenantSettings.data.status === "active" ? "success" : "warning"}>
                {tenantSettings.data.status}
              </Badge>
            </div>
          ) : null}
        </div>
      </Card>

      <SectionHelp summary="About these settings sections">
        Account covers your profile, password, MFA, and sessions. When you have workspace access, General stores
        identity, Publishing holds approval/publish defaults, Integrations covers Telegram and WhatsApp, and Social
        stores per-platform credentials—unsaved form values stay in memory while you switch tabs via{" "}
        <code className="mx-1">?tab=</code>.
      </SectionHelp>

      <SettingsWorkspaceTabs
        settingsTab={settingsTab}
        setSettingsTab={setSettingsTab}
        canManageWorkspace={canManageWorkspace}
        workspaceForm={workspaceForm}
        workflowForm={workflowForm}
        whatsappForm={whatsappForm}
        telegramForm={telegramForm}
        tenantMutation={tenantMutation}
        whatsappMutation={whatsappMutation}
        telegramMutation={telegramMutation}
        socialMutation={socialMutation}
        registerWebhookMutation={registerWebhookMutation}
        sendTelegramDigestTestMutation={sendTelegramDigestTestMutation}
        tenantSettings={tenantSettings}
        whatsappSettings={whatsappSettings}
        telegramSettings={telegramSettings}
        socialAccounts={socialAccounts}
        whatsappProvider={whatsappProvider}
        activeMembership={activeMembership}
        defaultSocialPlatform={defaultSocialPlatform}
        savingPlatform={savingPlatform}
        setSavingPlatform={setSavingPlatform}
      />
    </div>
  );
}
