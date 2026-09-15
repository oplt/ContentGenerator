import { useQuery } from "@tanstack/react-query";
import { getAuditLogs } from "../api/settings";
import { DataTable } from "../components/dashboard/DataTable";
import { Button } from "../components/ui/button";
import { HelpDisclosure } from "../components/ui/HelpDisclosure";
import { QueryBoundary } from "../components/ui/QueryBoundary";
import { useTenantScope } from "../hooks/useTenantScope";
import { queryKeys } from "../lib/queryKeys";

export default function AuditPage() {
  const { tenantId, enabled } = useTenantScope();
  const logs = useQuery({
    queryKey: queryKeys.auditLogs(tenantId ?? "none"),
    queryFn: () => getAuditLogs(),
    enabled,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Audit log</h1>
        <p className="mt-1 text-sm text-muted-foreground">Tenant-scoped operator and system actions.</p>
      </div>
      <HelpDisclosure summary="What appears in the audit log">
        Entries cover publishing, settings changes, approvals, and security-sensitive account actions. Failed loads
        never pretend to be empty—use Retry if the request fails.
      </HelpDisclosure>
      <QueryBoundary
        query={logs}
        loadingLabel="Loading audit logs"
        errorMessage="Audit logs could not be loaded."
        empty={{
          when: (data) => data.length === 0,
          title: "No audit events yet",
          description: "Operator and system actions for this workspace will show up here.",
          action: (
            <Button variant="outline" onClick={() => void logs.refetch()}>
              Refresh
            </Button>
          ),
        }}
      >
        {(data) => (
          <DataTable
            caption="Audit log entries"
            rows={data}
            columns={[
              { key: "action", header: "Action", render: (log) => log.action },
              { key: "entity", header: "Entity", render: (log) => `${log.entity_type} ${log.entity_id ?? ""}` },
              { key: "message", header: "Message", render: (log) => log.message },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}
