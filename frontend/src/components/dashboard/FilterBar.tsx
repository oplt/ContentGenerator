import { Search } from "lucide-react";
import { Input } from "../ui/input";

export function FilterBar({
  value,
  onChange,
  actions,
}: {
  value: string;
  onChange: (value: string) => void;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-[1.5rem] border border-border bg-card p-4 md:flex-row md:items-center md:justify-between">
      <div className="relative w-full max-w-md">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input value={value} onChange={(event) => onChange(event.target.value)} className="pl-9" placeholder="Filter results" />
      </div>
      {actions}
    </div>
  );
}
