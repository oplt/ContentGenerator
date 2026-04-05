import { apiFetch } from "./client";

export type TenantSettings = {
  id: string;
  name: string;
  slug: string;
  plan_tier: string;
  timezone: string;
  status: string;
  settings: Record<string, string>;
};

export type WhatsAppSettings = {
  recipient: string;
  provider: string;
  phone_number_id: string;
  business_account_id: string;
  verify_token: string;
  access_token_configured: boolean;
  app_secret_configured: boolean;
  using_tenant_recipient: boolean;
  using_tenant_credentials: boolean;
};

export type AuditLog = {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  message: string;
  payload: Record<string, string>;
  correlation_id: string | null;
};

export function getTenantSettings() {
  return apiFetch<TenantSettings>("/settings/tenant");
}

export function updateTenantSettings(payload: Record<string, unknown>) {
  return apiFetch<TenantSettings>("/settings/tenant", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getWhatsAppSettings() {
  return apiFetch<WhatsAppSettings>("/settings/whatsapp");
}

export function updateWhatsAppSettings(payload: Record<string, unknown>) {
  return apiFetch<WhatsAppSettings>("/settings/whatsapp", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export type TelegramSettings = {
  bot_token_configured: boolean;
  chat_id: string;
  enabled: boolean;
};

export function getTelegramSettings() {
  return apiFetch<TelegramSettings>("/settings/telegram");
}

export function updateTelegramSettings(payload: Record<string, unknown>) {
  return apiFetch<TelegramSettings>("/settings/telegram", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function registerTelegramWebhook() {
  return apiFetch<{ webhook_url: string }>("/settings/telegram/register-webhook", {
    method: "POST",
  });
}

export function getAuditLogs() {
  return apiFetch<AuditLog[]>("/audit/logs");
}
