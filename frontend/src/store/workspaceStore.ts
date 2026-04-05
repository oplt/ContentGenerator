import { create } from "zustand";

type WorkspaceState = {
  tenantId: string | null;
  tenantName: string | null;
  theme: "light" | "dark";
  commandPaletteOpen: boolean;
  setTenant: (tenantId: string | null, tenantName: string | null) => void;
  toggleTheme: () => void;
  setCommandPaletteOpen: (open: boolean) => void;
};

const initialTheme =
  (localStorage.getItem("signalforge-theme") as "light" | "dark" | null) ?? "dark";

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  tenantId: null,
  tenantName: null,
  theme: initialTheme,
  commandPaletteOpen: false,
  setTenant: (tenantId, tenantName) => set({ tenantId, tenantName }),
  toggleTheme: () => {
    const next = get().theme === "dark" ? "light" : "dark";
    localStorage.setItem("signalforge-theme", next);
    document.documentElement.classList.toggle("dark", next === "dark");
    set({ theme: next });
  },
  setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),
}));

document.documentElement.classList.toggle("dark", initialTheme === "dark");
