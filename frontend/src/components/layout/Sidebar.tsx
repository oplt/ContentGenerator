import { NavLink } from "react-router-dom";
import { BarChart3, Cog, FolderKanban, Gauge, Newspaper, Settings2, ShieldCheck, Workflow } from "lucide-react";
import { cn } from "../../lib/utils";

const items = [
  { to: "/dashboard", label: "Overview", icon: Gauge },
  { to: "/dashboard/sources", label: "Sources", icon: Newspaper },
  { to: "/dashboard/stories", label: "Stories", icon: FolderKanban },
  { to: "/dashboard/content", label: "Content", icon: Workflow },
  { to: "/dashboard/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/dashboard/brand-profile", label: "Brand", icon: Settings2 },
  { to: "/dashboard/settings", label: "Settings", icon: Cog },
  { to: "/dashboard/audit", label: "Audit", icon: ShieldCheck },
];

export function Sidebar() {
  return (
    <aside className="hidden w-72 flex-col border-r border-border bg-card/70 px-4 py-6 backdrop-blur lg:flex">
      <div className="rounded-[1.5rem] border border-border bg-background/70 p-5">
        <p className="text-xs uppercase tracking-[0.16em] text-primary">SignalForge</p>
        <h1 className="mt-3 text-2xl font-semibold">AI Social Control Center</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Ingest signals, craft drafts, route approvals, publish, and track lift.
        </p>
      </div>
      <nav className="mt-6 flex-1 space-y-1">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/dashboard"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground",
                isActive && "bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground"
              )
            }
          >
            <item.icon className="size-4" />
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
