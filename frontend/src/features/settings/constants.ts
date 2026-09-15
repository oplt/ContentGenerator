import type { AccessTokenConfig, SocialPlatformConfigField } from "../../components/dashboard/SocialPlatformSettingsCard";

export type WorkspaceSettingsForm = {
  name: string;
  timezone: string;
};

export type WorkflowSettingsForm = {
  approval_sender_label: string;
  publishing_default_timezone: string;
  publishing_default_dry_run: string;
  ingestion_default_polling_interval_minutes: string;
};

export type WhatsAppSettingsForm = {
  recipient: string;
  provider: string;
  phone_number_id: string;
  business_account_id: string;
  verify_token: string;
  access_token: string;
  access_token_secret_ref: string;
  app_secret: string;
  app_secret_secret_ref: string;
};

export type TelegramSettingsForm = {
  bot_token: string;
  bot_token_secret_ref: string;
  chat_id: string;
  enabled: boolean;
};

export type SocialPlatformDefinition = {
  platform: string;
  label: string;
  description: string;
  configFields: SocialPlatformConfigField[];
  hiddenFields?: string[];
  accessTokenConfig?: AccessTokenConfig;
};

export const WHATSAPP_CONFIG_VARIABLES = [
  { key: "recipient", label: "Approval Recipient", description: "Default phone number that receives draft approvals in E.164 format." },
  { key: "provider", label: "Provider Mode", description: "Use stub for local development or Meta Cloud API for live WhatsApp delivery." },
  { key: "phone_number_id", label: "Phone Number ID", description: "Meta Cloud API phone number identifier used for outbound messages." },
  { key: "business_account_id", label: "Business Account ID", description: "Optional Meta business account ID used for operator context and support flows." },
  { key: "verify_token", label: "Verify Token", description: "Webhook verification token configured in the Meta developer console." },
  { key: "access_token", label: "Access Token", description: "Long-lived Meta access token used for WhatsApp Cloud API calls." },
  { key: "app_secret", label: "App Secret", description: "Meta app secret used to verify inbound webhook signatures." },
];

export const SOCIAL_PLATFORM_DEFINITIONS: SocialPlatformDefinition[] = [
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
    label: "Twitter",
    description:
      "Connect your Twitter account for automatic posting. Provide your handle and an OAuth 2.0 user access token with tweet.write scope.",
    configFields: [],
    hiddenFields: ["accountExternalId", "scopesCsv", "refreshToken", "accessTokenSecretRef"],
    accessTokenConfig: {
      label: "Access Token (OAuth 2.0 User Token)",
      placeholder: "Paste your OAuth 2.0 user access token",
      description:
        "Required. From Twitter Developer Portal → your app → Keys and Tokens → OAuth 2.0 User Access Token. Must have tweet.write and users.read scopes.",
    },
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

export const SETTINGS_TABS = ["general", "publishing", "integrations", "social"] as const;
export type SettingsTab = (typeof SETTINGS_TABS)[number];

/** Legacy ?tab= values from pre–Phase 9 settings IA. */
export const SETTINGS_TAB_ALIASES: Readonly<Record<string, SettingsTab>> = {
  workflow: "publishing",
  whatsapp: "integrations",
  telegram: "integrations",
};

