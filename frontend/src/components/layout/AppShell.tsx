import { type PropsWithChildren } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { CommandPalette } from "./CommandPalette";
import { useWorkspaceStore } from "../../store/workspaceStore";

export function AppShell({ children }: PropsWithChildren) {
  const setOpen = useWorkspaceStore((state) => state.setCommandPaletteOpen);

  return (
    <div className="flex min-h-screen bg-transparent">
      <Sidebar />
      <div className="flex min-h-screen flex-1 flex-col">
        <Topbar onOpenPalette={() => setOpen(true)} />
        <main className="flex-1 px-4 py-6 md:px-8">
          <div className="mx-auto max-w-7xl space-y-6">{children ?? <Outlet />}</div>
        </main>
      </div>
      <CommandPalette />
    </div>
  );
}
