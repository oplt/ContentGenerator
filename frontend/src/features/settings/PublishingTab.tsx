import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { FormField } from "../../components/ui/HelpDisclosure";
import { Input } from "../../components/ui/input";
import type { PublishingTabProps } from "./types";

export function PublishingTab({ workflowForm, tenantMutation }: PublishingTabProps) {
  return (
    <Card className="p-6">
      <h2 className="text-xl font-semibold">Approval and publishing defaults</h2>
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
        <FormField
          label="Approval sender label"
          htmlFor="settings-approval-sender"
          help="Display name shown on outbound approval messages."
        >
          <Input
            id="settings-approval-sender"
            placeholder="SignalForge Ops"
            {...workflowForm.register("approval_sender_label")}
          />
        </FormField>
        <FormField label="Default publish timezone" htmlFor="settings-publish-tz">
          <Input
            id="settings-publish-tz"
            placeholder="UTC"
            {...workflowForm.register("publishing_default_timezone")}
          />
        </FormField>
        <FormField
          label="Default dry run"
          htmlFor="settings-dry-run"
          help='Use "true" to stage publishes without posting live.'
        >
          <Input
            id="settings-dry-run"
            placeholder="true or false"
            {...workflowForm.register("publishing_default_dry_run")}
          />
        </FormField>
        <FormField
          label="Source update interval (minutes)"
          htmlFor="settings-poll-interval"
          help="Applied when creating new sources. Existing sources keep their own interval."
        >
          <Input
            id="settings-poll-interval"
            type="number"
            min={5}
            max={1440}
            placeholder="30"
            {...workflowForm.register("ingestion_default_polling_interval_minutes")}
          />
        </FormField>
        <p
          className="rounded-2xl border border-border bg-muted/40 p-4 text-sm text-muted-foreground md:col-span-2"
          role="note"
        >
          Telegram is the primary approval channel. Keep WhatsApp only as a legacy or fallback path under
          Integrations.
        </p>
        <Button type="submit" className="md:col-span-2" disabled={tenantMutation.isPending}>
          Save publishing defaults
        </Button>
      </form>
    </Card>
  );
}
