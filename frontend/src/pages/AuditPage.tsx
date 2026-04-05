import { useQuery } from "@tanstack/react-query";
import { getAuditLogs } from "../api/settings";
import { DataTable } from "../components/dashboard/DataTable";
import { LoadingState } from "../components/ui/LoadingState";

export default function AuditPage() {
  const logs = useQuery({ queryKey: ["audit", "logs"], queryFn: getAuditLogs });
  if (logs.isLoading || !logs.data) {
    return <LoadingState label="Loading audit logs" />;
  }
  return (
    <DataTable
      rows={logs.data}
      columns={[
        { key: "action", header: "Action", render: (log) => log.action },
        { key: "entity", header: "Entity", render: (log) => `${log.entity_type} ${log.entity_id ?? ""}` },
        { key: "message", header: "Message", render: (log) => log.message },
      ]}
    />
  );
}
