import { Command, Moon, Sun } from "lucide-react";
import { useAuth } from "../../features/auth/AuthContext";
import { useWorkspaceStore } from "../../store/workspaceStore";
import { Button } from "../ui/button";

export function Topbar({ onOpenPalette }: { onOpenPalette: () => void }) {
  const { currentUser, signOut, setActiveTenant } = useAuth();
  const { tenantId, theme, toggleTheme } = useWorkspaceStore();

  return (
    <header className="flex flex-col gap-3 border-b border-border bg-card px-4 py-3 md:flex-row md:items-center md:justify-between md:px-8">
      <div className="flex items-center gap-3">
        <Button variant="outline" size="sm" onClick={onOpenPalette}>
          <Command className="size-4" />
          Command
        </Button>
        <select
          value={tenantId ?? ""}
          onChange={(e) => setActiveTenant(e.target.value)}
          className="select-field h-9 w-auto text-xs"
        >
          {currentUser?.memberships.map((m) => (
            <option key={m.tenant_id} value={m.tenant_id}>
              {m.tenant_name}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={toggleTheme}>
          {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </Button>
        <div className="text-right">
          <div className="text-sm">{currentUser?.full_name ?? currentUser?.email}</div>
          <button
            className="text-xs uppercase tracking-wider text-muted-foreground transition hover:text-foreground"
            onClick={() => void signOut()}
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}
