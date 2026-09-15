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
  caption = "Data table",
}: {
  columns: Column<T>[];
  rows: T[];
  className?: string;
  caption?: string;
}) {
  return (
    <div
      role="region"
      aria-label={caption}
      tabIndex={0}
      className={cn(
        "border border-border bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className
      )}
      style={{ borderRadius: "var(--radius-card)" }}
    >
      <div className="hidden overflow-x-auto overscroll-x-contain md:block">
        <table className="min-w-full divide-y divide-border text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="bg-muted/60 text-left">
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  scope="col"
                  className="whitespace-nowrap px-4 py-3 text-xs font-normal uppercase tracking-[0.14em] text-muted-foreground"
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {rows.map((row, i) => (
              <tr key={i} className="transition-colors hover:bg-muted/30">
                {columns.map((col) => (
                  <td key={col.key} className="min-w-[8rem] px-4 py-3 align-top">
                    {col.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="divide-y divide-border md:hidden">
        {rows.map((row, i) => (
          <li key={`mobile-${i}`} className="space-y-3 p-4">
            {columns.map((col) => (
              <div key={col.key} className="grid gap-1">
                <span className="text-xs uppercase tracking-[0.14em] text-muted-foreground">{col.header}</span>
                <div className="text-sm">{col.render(row)}</div>
              </div>
            ))}
          </li>
        ))}
      </ul>
    </div>
  );
}
