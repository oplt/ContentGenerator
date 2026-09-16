import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  Cog,
  FileEdit,
  FolderKanban,
  Gauge,
  GitBranch,
  Layers,
  Newspaper,
  PlayCircle,
  RadioTower,
  Send,
  Settings2,
  ShieldCheck,
  TrendingUp,
  Workflow,
  Crown,
} from "lucide-react";
import type { AuthUser } from "../api/auth";
import { canAccessAuditLogs, canAccessTenantSettings } from "../features/auth/access";

export type NavRouteRequirement = "settings" | "audit";

export type NavRoute = {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Extra command-palette search terms */
  keywords?: string[];
  requires?: NavRouteRequirement;
  end?: boolean;
};

/**
 * Single permission-aware destination list for sidebar, mobile drawer, and command palette.
 * Keep this in sync with dashboard routes in `app/router.tsx`.
 */
export const NAV_ROUTES: readonly NavRoute[] = [
  { to: "/dashboard", label: "Overview", icon: Gauge, end: true, keywords: ["home"] },
  { to: "/dashboard/sources", label: "Sources", icon: Newspaper, keywords: ["ingest", "rss"] },
  {
    to: "/dashboard/stories",
    label: "Trend Candidates",
    icon: FolderKanban,
    keywords: ["stories", "trends", "candidates"],
  },
  { to: "/dashboard/briefs", label: "Briefs", icon: FileEdit, keywords: ["editorial"] },
  { to: "/dashboard/approvals", label: "Approvals", icon: RadioTower },
  {
    to: "/dashboard/content",
    label: "Asset Packages",
    icon: Workflow,
    keywords: ["content", "plans", "jobs"],
  },
  {
    to: "/dashboard/workflows",
    label: "Workflows",
    icon: GitBranch,
    keywords: ["automation", "dag", "editor"],
  },
  {
    to: "/dashboard/automations",
    label: "Automations",
    icon: Layers,
    keywords: ["schedule", "targets"],
  },
  {
    to: "/dashboard/runs",
    label: "Runs",
    icon: PlayCircle,
    keywords: ["workflow", "execution", "status"],
  },
  {
    to: "/dashboard/publishing",
    label: "Publish Queue",
    icon: Send,
    keywords: ["publishing", "posts"],
  },
  {
    to: "/dashboard/accounts",
    label: "Connected Accounts",
    icon: Settings2,
    keywords: ["social", "oauth"],
  },
  { to: "/dashboard/analytics", label: "Analytics", icon: BarChart3 },
  {
    to: "/dashboard/trending-repos",
    label: "Trending Repos",
    icon: TrendingUp,
    keywords: ["github"],
  },
  {
    to: "/dashboard/chess-video",
    label: "ChessMaster",
    icon: Crown,
    keywords: ["chess", "pgn", "video", "san", "uci"],
  },
  { to: "/dashboard/brand-profile", label: "Brand", icon: Settings2, keywords: ["voice"] },
  {
    to: "/dashboard/settings",
    label: "Settings",
    icon: Cog,
    keywords: ["workspace", "telegram", "whatsapp", "account", "security", "mfa", "profile"],
  },
  {
    to: "/dashboard/audit",
    label: "Audit",
    icon: ShieldCheck,
    requires: "audit",
    keywords: ["logs"],
  },
] as const;

export function getVisibleNavRoutes(
  user: AuthUser | null,
  tenantId: string | null
): NavRoute[] {
  return NAV_ROUTES.filter((route) => {
    if (route.requires === "settings") {
      return canAccessTenantSettings(user, tenantId);
    }
    if (route.requires === "audit") {
      return canAccessAuditLogs(user, tenantId);
    }
    return true;
  });
}

export function filterNavRoutes(routes: readonly NavRoute[], query: string): NavRoute[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return [...routes];
  }
  return routes.filter((route) => {
    const haystack = [route.label, route.to, ...(route.keywords ?? [])].join(" ").toLowerCase();
    return haystack.includes(normalized);
  });
}
