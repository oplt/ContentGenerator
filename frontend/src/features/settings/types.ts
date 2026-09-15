import type { UseFormReturn } from "react-hook-form";
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";
import type { Membership } from "../../api/auth";
import type { SocialAccount, SocialAccountUpsertPayload } from "../../api/publishing";
import type {
  TelegramSettings,
  TenantSettings,
  WhatsAppSettings,
} from "../../api/settings";
import type {
  SettingsTab,
  TelegramSettingsForm,
  WhatsAppSettingsForm,
  WorkflowSettingsForm,
  WorkspaceSettingsForm,
} from "./constants";

export type TenantSettingsMutation = UseMutationResult<
  TenantSettings,
  Error,
  Record<string, unknown>
>;

export type WhatsAppSettingsMutation = UseMutationResult<
  WhatsAppSettings,
  Error,
  Record<string, unknown>
>;

export type TelegramSettingsMutation = UseMutationResult<
  TelegramSettings,
  Error,
  Record<string, unknown>
>;

export type SocialAccountMutation = UseMutationResult<
  SocialAccount,
  Error,
  SocialAccountUpsertPayload
>;

export type RegisterWebhookMutation = UseMutationResult<
  { webhook_url: string },
  Error,
  void
>;

export type SendTelegramDigestTestMutation = UseMutationResult<
  { status: string },
  Error,
  void
>;

export type GeneralTabProps = {
  workspaceForm: UseFormReturn<WorkspaceSettingsForm>;
  tenantMutation: TenantSettingsMutation;
  tenantSettings: TenantSettings;
  activeMembership: Membership | null;
};

export type PublishingTabProps = {
  workflowForm: UseFormReturn<WorkflowSettingsForm>;
  tenantMutation: TenantSettingsMutation;
};

export type IntegrationsTabProps = {
  whatsappForm: UseFormReturn<WhatsAppSettingsForm>;
  telegramForm: UseFormReturn<TelegramSettingsForm>;
  whatsappMutation: WhatsAppSettingsMutation;
  telegramMutation: TelegramSettingsMutation;
  registerWebhookMutation: RegisterWebhookMutation;
  sendTelegramDigestTestMutation: SendTelegramDigestTestMutation;
  whatsappSettings: WhatsAppSettings;
  telegramSettings: TelegramSettings | undefined;
  whatsappProvider: string;
};

export type SocialTabProps = {
  socialAccounts: SocialAccount[] | undefined;
  socialMutation: SocialAccountMutation;
  defaultSocialPlatform: string;
  savingPlatform: string | null;
  setSavingPlatform: (platform: string | null) => void;
};

export type SettingsWorkspaceTabsProps = {
  settingsTab: SettingsTab;
  setSettingsTab: (tab: SettingsTab) => void;
  workspaceForm: UseFormReturn<WorkspaceSettingsForm>;
  workflowForm: UseFormReturn<WorkflowSettingsForm>;
  whatsappForm: UseFormReturn<WhatsAppSettingsForm>;
  telegramForm: UseFormReturn<TelegramSettingsForm>;
  tenantMutation: TenantSettingsMutation;
  whatsappMutation: WhatsAppSettingsMutation;
  telegramMutation: TelegramSettingsMutation;
  socialMutation: SocialAccountMutation;
  registerWebhookMutation: RegisterWebhookMutation;
  sendTelegramDigestTestMutation: SendTelegramDigestTestMutation;
  tenantSettings: UseQueryResult<TenantSettings, Error>;
  whatsappSettings: UseQueryResult<WhatsAppSettings, Error>;
  telegramSettings: UseQueryResult<TelegramSettings, Error>;
  socialAccounts: UseQueryResult<SocialAccount[], Error>;
  whatsappProvider: string;
  activeMembership: Membership | null;
  defaultSocialPlatform: string;
  savingPlatform: string | null;
  setSavingPlatform: (platform: string | null) => void;
};
