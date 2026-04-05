import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Dialog, DialogContent } from "../ui/dialog";
import { Input } from "../ui/input";
import { useWorkspaceStore } from "../../store/workspaceStore";

const commands = [
  { label: "Overview", path: "/dashboard" },
  { label: "Sources", path: "/dashboard/sources" },
  { label: "Stories", path: "/dashboard/stories" },
  { label: "Content", path: "/dashboard/content" },
  { label: "Approvals", path: "/dashboard/approvals" },
  { label: "Publishing", path: "/dashboard/publishing" },
  { label: "Analytics", path: "/dashboard/analytics" },
];

export function CommandPalette() {
  const navigate = useNavigate();
  const open = useWorkspaceStore((state) => state.commandPaletteOpen);
  const setOpen = useWorkspaceStore((state) => state.setCommandPaletteOpen);
  const [query, setQuery] = useState("");
  const results = useMemo(
    () => commands.filter((command) => command.label.toLowerCase().includes(query.toLowerCase())),
    [query]
  );

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent>
        <Input placeholder="Jump to..." value={query} onChange={(event) => setQuery(event.target.value)} />
        <div className="mt-4 space-y-2">
          {results.map((command) => (
            <button
              key={command.path}
              className="flex w-full items-center justify-between rounded-2xl border border-border px-4 py-3 text-left hover:bg-muted"
              onClick={() => {
                navigate(command.path);
                setOpen(false);
              }}
            >
              <span className="font-medium">{command.label}</span>
              <span className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Go</span>
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
