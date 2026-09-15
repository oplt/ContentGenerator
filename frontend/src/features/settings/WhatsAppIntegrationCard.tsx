import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { FormField } from "../../components/ui/HelpDisclosure";
import { Input } from "../../components/ui/input";
import { PasswordInput } from "../../components/ui/PasswordInput";
import { WHATSAPP_CONFIG_VARIABLES } from "./constants";
import type { IntegrationsTabProps } from "./types";

type WhatsAppIntegrationCardProps = Pick<
  IntegrationsTabProps,
  "whatsappForm" | "whatsappMutation" | "whatsappSettings" | "whatsappProvider"
>;

export function WhatsAppIntegrationCard({
  whatsappForm,
  whatsappMutation,
  whatsappSettings,
  whatsappProvider,
}: WhatsAppIntegrationCardProps) {
  return (
    <Card className="space-y-6 p-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-xl font-semibold">Legacy WhatsApp delivery</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={whatsappSettings.provider === "meta" ? "success" : "muted"}>
            {whatsappSettings.provider === "meta" ? "Meta Cloud API" : "Stub Provider"}
          </Badge>
          <Badge variant={whatsappSettings.using_tenant_recipient ? "success" : "muted"}>
            {whatsappSettings.using_tenant_recipient ? "Tenant recipient" : "Global recipient fallback"}
          </Badge>
          <Badge variant={whatsappSettings.using_tenant_credentials ? "success" : "muted"}>
            {whatsappSettings.using_tenant_credentials ? "Tenant credentials" : "Global credentials fallback"}
          </Badge>
        </div>
      </div>

      <div className="grid gap-3 rounded-2xl border border-border bg-muted/40 p-4 text-sm md:grid-cols-3">
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Recipient</p>
          <p className="mt-2 font-medium">{whatsappSettings.recipient || "Not configured"}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Access Token</p>
          <p className="mt-2 font-medium">
            {whatsappSettings.access_token_configured ? "Configured" : "Not configured"}
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">App Secret</p>
          <p className="mt-2 font-medium">
            {whatsappSettings.app_secret_configured ? "Configured" : "Not configured"}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {WHATSAPP_CONFIG_VARIABLES.map((field) => (
          <Badge key={field.key} variant="muted" className="font-mono normal-case tracking-normal">
            {field.key}
          </Badge>
        ))}
      </div>
      <p className="text-sm text-muted-foreground" role="note">
        Leave secrets blank to keep stored values. Submitting an empty secret clears the tenant override and
        falls back to global env config.
      </p>

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
          </div>
        </div>

        <FormField
          label="Approval recipient"
          htmlFor="wa-recipient"
          help="E.164 phone used when approval requests omit an explicit recipient."
        >
          <Input id="wa-recipient" placeholder="+15551234567" {...whatsappForm.register("recipient")} />
        </FormField>
        <FormField
          label="Verify token"
          htmlFor="wa-verify"
          help="Must match the Meta webhook subscription verify token."
        >
          <Input id="wa-verify" placeholder="meta-webhook-verify-token" {...whatsappForm.register("verify_token")} />
        </FormField>
        <FormField label="Phone number ID" htmlFor="wa-phone" help="Required for Meta Cloud API outbound messages.">
          <Input id="wa-phone" placeholder="123456789012345" {...whatsappForm.register("phone_number_id")} />
        </FormField>
        <FormField
          label="Business account ID"
          htmlFor="wa-biz"
          help="Optional Meta business account for multi-account operators."
        >
          <Input id="wa-biz" placeholder="987654321098765" {...whatsappForm.register("business_account_id")} />
        </FormField>
        <FormField
          label="Access token"
          htmlFor="wa-token"
          help={
            whatsappSettings.access_token_configured
              ? "A tenant access token is already stored."
              : "No tenant access token is stored yet."
          }
        >
          <PasswordInput
            id="wa-token"
            placeholder="Meta Cloud API access token"
            {...whatsappForm.register("access_token")}
          />
        </FormField>
        <FormField
          label="Access token secret reference"
          htmlFor="wa-token-ref"
          help="Optional vault reference; runtime resolves this instead of the stored token."
        >
          <Input
            id="wa-token-ref"
            placeholder="vault://meta/whatsapp/access-token"
            {...whatsappForm.register("access_token_secret_ref")}
          />
        </FormField>
        <FormField
          label="App secret"
          htmlFor="wa-secret"
          help={
            whatsappSettings.app_secret_configured
              ? "A tenant app secret is already stored."
              : "No tenant app secret is stored yet."
          }
        >
          <PasswordInput id="wa-secret" placeholder="Meta app secret" {...whatsappForm.register("app_secret")} />
        </FormField>
        <FormField
          label="App secret reference"
          htmlFor="wa-secret-ref"
          help="Keep the webhook verification secret in an external secret manager."
        >
          <Input
            id="wa-secret-ref"
            placeholder="vault://meta/whatsapp/app-secret"
            {...whatsappForm.register("app_secret_secret_ref")}
          />
        </FormField>
        <Button type="submit" className="md:col-span-2" disabled={whatsappMutation.isPending}>
          {whatsappMutation.isPending ? "Saving WhatsApp Settings..." : "Save WhatsApp Settings"}
        </Button>
      </form>
    </Card>
  );
}
