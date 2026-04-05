import type { Source, SourceHealth } from "../../api/sources";
import { Badge } from "../ui/badge";
import { DataTable } from "./DataTable";

export function SourceHealthTable({ sources, health }: { sources: Source[]; health: SourceHealth[] }) {
  const rows = sources.map((source) => ({
    source,
    health: health.find((item) => item.source_id === source.id),
  }));

  return (
    <DataTable
      rows={rows}
      columns={[
        {
          key: "source",
          header: "Source",
          render: ({ source }) => (
            <div>
              <div className="font-medium">{source.name}</div>
              <div className="text-xs text-muted-foreground">{source.url}</div>
            </div>
          ),
        },
        {
          key: "health",
          header: "Health",
          render: ({ health }) => (
            <Badge variant={health?.status === "healthy" ? "success" : "warning"}>
              {health?.status ?? "unknown"}
            </Badge>
          ),
        },
        {
          key: "counts",
          header: "Success / Failure",
          render: ({ source }) => `${source.success_count} / ${source.failure_count}`,
        },
      ]}
    />
  );
}
