import { NavLink } from "react-router-dom";
import {
  BarChart3, Cog, FileEdit, FolderKanban, Gauge,
  Newspaper, RadioTower, Send, Settings2, ShieldCheck, TrendingUp, Workflow,
} from "lucide-react";
import { useAuth } from "../../features/auth/AuthContext";
import { canAccessAuditLogs, canAccessTenantSettings } from "../../features/auth/access";
import { cn } from "../../lib/utils";

const items = [
  { to: "/dashboard",           label: "Overview",          icon: Gauge      },
  { to: "/dashboard/sources",   label: "Sources",           icon: Newspaper  },
  { to: "/dashboard/trends",    label: "Trend Candidates",  icon: FolderKanban },
  { to: "/dashboard/briefs",    label: "Briefs",            icon: FileEdit   },
  { to: "/dashboard/approvals", label: "Approvals",         icon: RadioTower },
  { to: "/dashboard/content",   label: "Asset Packages",    icon: Workflow   },
  { to: "/dashboard/publishing","label": "Publish Queue",   icon: Send       },
  { to: "/dashboard/accounts",  label: "Connected Accounts",icon: Settings2  },
  { to: "/dashboard/analytics", label: "Analytics",         icon: BarChart3  },
  { to: "/dashboard/trending-repos", label: "Trending Repos", icon: TrendingUp },
  { to: "/dashboard/brand-profile", label: "Brand",         icon: Settings2  },
  { to: "/dashboard/settings",  label: "Settings",          icon: Cog        },
  { to: "/dashboard/audit",     label: "Audit",             icon: ShieldCheck},
];

export function Sidebar() {
  const { currentUser } = useAuth();
  const visibleItems = items.filter((item) => {
    if (item.to === "/dashboard/settings") {
      return canAccessTenantSettings(currentUser);
    }
    if (item.to === "/dashboard/audit") {
      return canAccessAuditLogs(currentUser);
    }
    return true;
  });

  return (
    <aside className="hidden w-64 flex-col border-r border-border bg-card px-4 py-6 lg:flex">
      {/* Brand identity */}
      <div className="px-2">
        {/* Mistral block gradient strip */}
        <div className="h-1 w-full block-gradient mb-4" />
        <p className="eyebrow text-primary">SignalForge</p>
        <h1 className="mt-2 text-lg text-foreground">AI Content Operations</h1>
        <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
          Ingest signals, brief, approve, publish, and track.
        </p>
      </div>

      {/* Navigation */}
      <nav className="mt-6 flex-1 space-y-0.5">
        {visibleItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/dashboard"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 px-3 py-2.5 text-sm transition-colors",
                isActive
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )
            }
            style={{ borderRadius: "var(--radius-sm)" }}
          >
            <item.icon className="size-4 shrink-0" />
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
