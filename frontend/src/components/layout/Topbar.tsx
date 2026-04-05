import { Command, Moon, Sun } from "lucide-react";
import { useAuth } from "../../features/auth/AuthContext";
import { useWorkspaceStore } from "../../store/workspaceStore";
import { Button } from "../ui/button";

export function Topbar({ onOpenPalette }: { onOpenPalette: () => void }) {
  const { currentUser, signOut, setActiveTenant } = useAuth();
  const { tenantId, theme, toggleTheme } = useWorkspaceStore();

  return (
    <header className="flex flex-col gap-3 border-b border-border bg-background/70 px-4 py-4 backdrop-blur md:flex-row md:items-center md:justify-between md:px-8">
      <div className="flex items-center gap-3">
        <Button variant="outline" size="sm" onClick={onOpenPalette}>
          <Command className="size-4" />
          Command
        </Button>
        <select
          value={tenantId ?? ""}
          onChange={(event) => setActiveTenant(event.target.value)}
          className="h-10 rounded-xl border border-input bg-card px-3 text-sm"
        >
          {currentUser?.memberships.map((membership) => (
            <option key={membership.tenant_id} value={membership.tenant_id}>
              {membership.tenant_name}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-3">
        <Button variant="outline" size="sm" onClick={toggleTheme}>
          {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
          {theme}
        </Button>
        <div className="text-right">
          <div className="text-sm font-medium">{currentUser?.full_name ?? currentUser?.email}</div>
          <button className="text-xs text-muted-foreground" onClick={() => void signOut()}>
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}
