import { useRef, useState, type PropsWithChildren } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { CommandPalette } from "./CommandPalette";
import { MobileNavDrawer } from "./MobileNavDrawer";
import { useWorkspaceStore } from "../../store/workspaceStore";

export function AppShell({ children }: PropsWithChildren) {
  const setOpen = useWorkspaceStore((state) => state.setCommandPaletteOpen);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <div className="flex min-h-screen flex-1 flex-col">
        <Topbar
          ref={menuButtonRef}
          mobileNavOpen={mobileNavOpen}
          onOpenPalette={() => setOpen(true)}
          onOpenMobileNav={() => setMobileNavOpen(true)}
        />
        <main className="flex-1 px-4 py-6 md:px-8">
          <div className="mx-auto max-w-7xl space-y-6">{children ?? <Outlet />}</div>
        </main>
      </div>
      <MobileNavDrawer
        open={mobileNavOpen}
        onOpenChange={(open) => {
          setMobileNavOpen(open);
          if (!open) {
            window.requestAnimationFrame(() => menuButtonRef.current?.focus());
          }
        }}
      />
      <CommandPalette />
    </div>
  );
}
