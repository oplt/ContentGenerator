import { forwardRef } from "react";
import { Command, Menu, Moon, Sun } from "lucide-react";
import { useAuth } from "../../features/auth/AuthContext";
import { useWorkspaceStore } from "../../store/workspaceStore";
import { Button } from "../ui/button";

export const Topbar = forwardRef<
  HTMLButtonElement,
  {
    onOpenPalette: () => void;
    onOpenMobileNav: () => void;
    mobileNavOpen?: boolean;
  }
>(function Topbar({ onOpenPalette, onOpenMobileNav, mobileNavOpen = false }, menuButtonRef) {
  const { currentUser, signOut, setActiveTenant } = useAuth();
  const { tenantId, theme, toggleTheme } = useWorkspaceStore();

  return (
    <header className="flex flex-col gap-3 border-b border-border bg-card px-4 py-3 md:flex-row md:items-center md:justify-between md:px-8">
      <div className="flex items-center gap-3">
        <Button
          ref={menuButtonRef}
          type="button"
          variant="outline"
          size="icon"
          className="min-h-11 min-w-11 lg:hidden"
          aria-label="Open navigation menu"
          aria-expanded={mobileNavOpen}
          aria-controls="mobile-nav-drawer"
          onClick={onOpenMobileNav}
        >
          <Menu className="size-4" aria-hidden />
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="min-h-11"
          aria-label="Open command palette"
          onClick={onOpenPalette}
        >
          <Command className="size-4" aria-hidden />
          <span className="hidden sm:inline">Command</span>
        </Button>
        <label className="sr-only" htmlFor="tenant-switcher">
          Active workspace
        </label>
        <select
          id="tenant-switcher"
          value={tenantId ?? ""}
          onChange={(e) => setActiveTenant(e.target.value)}
          className="select-field h-11 min-h-11 w-auto text-xs"
          aria-label="Active workspace"
        >
          {currentUser?.memberships.map((m) => (
            <option key={m.tenant_id} value={m.tenant_id}>
              {m.tenant_name}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-3">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="min-h-11 min-w-11"
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          onClick={toggleTheme}
        >
          {theme === "dark" ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />}
        </Button>
        <div className="text-right">
          <div className="text-sm">{currentUser?.full_name ?? currentUser?.email}</div>
          <button
            type="button"
            className="min-h-11 text-xs uppercase tracking-wider text-muted-foreground transition hover:text-foreground"
            onClick={() => void signOut()}
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
});
