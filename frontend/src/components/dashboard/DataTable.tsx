import { cn } from "../../lib/utils";

export type Column<T> = {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
};

export function DataTable<T>({
  columns,
  rows,
  className,
}: {
  columns: Column<T>[];
  rows: T[];
  className?: string;
}) {
  return (
    <div className={cn("overflow-hidden rounded-[1.5rem] border border-border bg-card", className)}>
      <table className="min-w-full divide-y divide-border text-sm">
        <thead className="bg-muted/60 text-left text-xs uppercase tracking-[0.16em] text-muted-foreground">
          <tr>
            {columns.map((column) => (
              <th key={column.key} className="px-4 py-3 font-medium">
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border/70">
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="hover:bg-muted/30">
              {columns.map((column) => (
                <td key={column.key} className="px-4 py-3 align-top">
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
