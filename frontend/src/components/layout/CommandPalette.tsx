import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Dialog, DialogContent, DialogTitle } from "../ui/dialog";
import { Input } from "../ui/input";
import { useWorkspaceStore } from "../../store/workspaceStore";
import { filterNavRoutes } from "../../navigation/routeManifest";
import { useNavRoutes } from "../../navigation/useNavRoutes";

export function CommandPalette() {
  const navigate = useNavigate();
  const open = useWorkspaceStore((state) => state.commandPaletteOpen);
  const setOpen = useWorkspaceStore((state) => state.setCommandPaletteOpen);
  const routes = useNavRoutes();
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const results = useMemo(() => filterNavRoutes(routes, query), [query, routes]);

  useEffect(() => {
    if (open) {
      setQuery("");
      window.requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent aria-describedby={undefined}>
        <DialogTitle className="sr-only">Jump to a destination</DialogTitle>
        <Input
          ref={inputRef}
          aria-label="Search destinations"
          placeholder="Jump to..."
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <div className="mt-4 max-h-[50vh] space-y-2 overflow-y-auto" role="listbox" aria-label="Destinations">
          {results.length === 0 ? (
            <p className="px-1 text-sm text-muted-foreground">No matching destinations.</p>
          ) : (
            results.map((command) => (
              <button
                key={command.to}
                type="button"
                role="option"
                aria-label={command.label}
                className="flex min-h-11 w-full items-center justify-between border border-border px-4 py-3 text-left transition-colors hover:bg-muted"
                style={{ borderRadius: "var(--radius-sm)" }}
                onClick={() => {
                  navigate(command.to);
                  setOpen(false);
                }}
              >
                <span className="inline-flex items-center gap-3 font-medium">
                  <command.icon className="size-4 shrink-0" aria-hidden />
                  {command.label}
                </span>
                <span className="text-xs font-medium text-muted-foreground">Go</span>
              </button>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
