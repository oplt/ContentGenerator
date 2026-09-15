import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { FormField } from "../../components/ui/HelpDisclosure";
import { Input } from "../../components/ui/input";
import { PasswordInput } from "../../components/ui/PasswordInput";
import type { IntegrationsTabProps } from "./types";

type TelegramIntegrationCardProps = Pick<
  IntegrationsTabProps,
  | "telegramForm"
  | "telegramMutation"
  | "registerWebhookMutation"
  | "sendTelegramDigestTestMutation"
  | "telegramSettings"
>;

export function TelegramIntegrationCard({
  telegramForm,
  telegramMutation,
  registerWebhookMutation,
  sendTelegramDigestTestMutation,
  telegramSettings,
}: TelegramIntegrationCardProps) {
  return (
    <Card className="p-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-xl font-semibold">Telegram editorial approvals</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={telegramSettings?.bot_token_configured ? "success" : "muted"}>
            {telegramSettings?.bot_token_configured ? "Bot configured" : "No bot token"}
          </Badge>
          <Badge variant={telegramSettings?.enabled ? "success" : "muted"}>
            {telegramSettings?.enabled ? "Enabled" : "Disabled"}
          </Badge>
        </div>
      </div>

      <div className="mt-6 grid gap-3 rounded-2xl border border-border bg-muted/40 p-4 text-sm md:grid-cols-3">
        <div>
          <p className="text-xs font-medium text-muted-foreground">Bot Token</p>
          <p className="mt-2 font-medium">
            {telegramSettings?.bot_token_configured ? "Configured" : "Not configured"}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium text-muted-foreground">Chat ID</p>
          <p className="mt-2 font-medium">{telegramSettings?.chat_id || "Not set"}</p>
        </div>
        <div>
          <p className="text-xs font-medium text-muted-foreground">Status</p>
          <p className="mt-2 font-medium">{telegramSettings?.enabled ? "Active" : "Inactive"}</p>
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
        <FormField
          label="Bot token"
          htmlFor="tg-bot-token"
          help={
            telegramSettings?.bot_token_configured
              ? "A bot token is already stored. Leave blank to keep it."
              : "Create a bot with @BotFather, then paste the token."
          }
        >
          <PasswordInput
            id="tg-bot-token"
            placeholder="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
            {...telegramForm.register("bot_token")}
          />
        </FormField>
        <FormField
          label="Bot token secret reference"
          htmlFor="tg-bot-ref"
          help="Optional vault reference resolved at runtime instead of the stored token."
        >
          <Input
            id="tg-bot-ref"
            placeholder="vault://telegram/editorial/bot-token"
            {...telegramForm.register("bot_token_secret_ref")}
          />
        </FormField>
        <FormField
          label="Chat ID"
          htmlFor="tg-chat"
          help="Group/channel ID (negative) or username. @userinfobot can help find IDs."
        >
          <Input
            id="tg-chat"
            placeholder="-1001234567890 or @yourchannel"
            {...telegramForm.register("chat_id")}
          />
        </FormField>
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
          disabled={registerWebhookMutation.isPending || !telegramSettings?.bot_token_configured}
          onClick={() => registerWebhookMutation.mutate()}
        >
          {registerWebhookMutation.isPending ? "Registering…" : "Register Webhook"}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={
            sendTelegramDigestTestMutation.isPending ||
            !telegramSettings?.bot_token_configured ||
            !telegramSettings?.chat_id ||
            !telegramSettings?.enabled
          }
          onClick={() => sendTelegramDigestTestMutation.mutate()}
        >
          {sendTelegramDigestTestMutation.isPending ? "Sending…" : "Send Test Daily Digest"}
        </Button>
        {registerWebhookMutation.isSuccess && (
          <p className="text-xs text-muted-foreground md:col-span-2">
            Webhook registered: {registerWebhookMutation.data?.webhook_url}
          </p>
        )}
        {registerWebhookMutation.isError && (
          <p className="text-xs text-destructive md:col-span-2" role="alert">
            Failed to register webhook. Make sure the bot token is saved and the server is publicly reachable.
          </p>
        )}
        {sendTelegramDigestTestMutation.isSuccess && (
          <p className="text-xs text-muted-foreground md:col-span-2">
            Test daily digest sent to the configured Telegram chat.
          </p>
        )}
        {sendTelegramDigestTestMutation.isError && (
          <p className="text-xs text-destructive md:col-span-2" role="alert">
            Failed to send the test daily digest. Check Telegram is enabled, bot token, chat ID, and daily repos.
          </p>
        )}
      </form>
    </Card>
  );
}
