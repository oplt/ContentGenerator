import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { FormField } from "../../components/ui/HelpDisclosure";
import { Input } from "../../components/ui/input";
import type { GeneralTabProps } from "./types";

export function GeneralTab({
  workspaceForm,
  tenantMutation,
  tenantSettings,
  activeMembership,
}: GeneralTabProps) {
  const permissionCodes = activeMembership?.role?.permission_codes ?? [];

  return (
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
        <FormField label="Workspace name" htmlFor="settings-workspace-name">
          <Input id="settings-workspace-name" placeholder="Workspace name" {...workspaceForm.register("name")} />
        </FormField>
        <FormField
          label="Timezone"
          htmlFor="settings-workspace-timezone"
          help="IANA timezone used for scheduling defaults across the tenant."
        >
          <Input
            id="settings-workspace-timezone"
            placeholder="Europe/Brussels"
            {...workspaceForm.register("timezone")}
          />
        </FormField>
        <div className="grid gap-3 rounded-2xl border border-border bg-muted/40 p-4 text-sm md:col-span-2 md:grid-cols-3">
          <div>
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Slug</p>
            <p className="mt-2 font-medium">{tenantSettings.slug}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Plan</p>
            <p className="mt-2 font-medium">{tenantSettings.plan_tier}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Status</p>
            <p className="mt-2 font-medium">{tenantSettings.status}</p>
          </div>
        </div>
        <div className="grid gap-3 rounded-2xl border border-border bg-muted/40 p-4 text-sm md:col-span-2 md:grid-cols-3">
          <div>
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">RBAC Mode</p>
            <p className="mt-2 font-medium">{tenantSettings.rbac_mode}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Active Role</p>
            <p className="mt-2 font-medium">{activeMembership?.role?.name ?? "Workspace operator"}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Permission Count</p>
            <p className="mt-2 font-medium">{permissionCodes.length}</p>
          </div>
          <div className="md:col-span-3">
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Permission Placeholders</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {permissionCodes.length > 0 ? (
                permissionCodes.map((code) => (
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
  );
}
