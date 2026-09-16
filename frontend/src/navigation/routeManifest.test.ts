import { describe, expect, it } from "vitest";
import type { AuthUser } from "../api/auth";
import { filterNavRoutes, getVisibleNavRoutes, NAV_ROUTES } from "./routeManifest";

const baseUser: AuthUser = {
  id: "u1",
  email: "ops@example.com",
  full_name: "Ops",
  is_verified: true,
  is_admin: false,
  mfa_enabled: false,
  default_tenant_id: "t1",
  rbac_mode: "role_based_placeholder",
  memberships: [
    {
      tenant_id: "t1",
      tenant_name: "Tenant",
      tenant_slug: "tenant",
      status: "active",
      role: {
        id: "r1",
        name: "Operator",
        slug: "operator",
        permission_codes: [],
      },
    },
  ],
};

describe("routeManifest", () => {
  it("lists every dashboard destination used by navigation surfaces", () => {
    const paths = NAV_ROUTES.map((route) => route.to);
    expect(paths).toEqual([
      "/dashboard",
      "/dashboard/sources",
      "/dashboard/stories",
      "/dashboard/briefs",
      "/dashboard/approvals",
      "/dashboard/content",
      "/dashboard/workflows",
      "/dashboard/automations",
      "/dashboard/runs",
      "/dashboard/publishing",
      "/dashboard/accounts",
      "/dashboard/analytics",
      "/dashboard/trending-repos",
      "/dashboard/chess-video",
      "/dashboard/brand-profile",
      "/dashboard/settings",
      "/dashboard/audit",
    ]);
  });

  it("hides audit without permissions; settings stays visible for account access", () => {
    const visible = getVisibleNavRoutes(baseUser, "t1").map((route) => route.to);
    expect(visible).toContain("/dashboard/settings");
    expect(visible).not.toContain("/dashboard/audit");
    expect(visible).toContain("/dashboard/briefs");
    expect(visible).not.toContain("/dashboard/account");
    expect(visible).toContain("/dashboard/trending-repos");
    expect(visible).toContain("/dashboard/brand-profile");
  });

  it("includes settings and audit when membership grants them", () => {
    const privileged: AuthUser = {
      ...baseUser,
      memberships: [
        {
          ...baseUser.memberships[0],
          role: {
            id: "r1",
            name: "Owner",
            slug: "owner",
            permission_codes: ["settings:write", "audit:read"],
          },
        },
      ],
    };
    const visible = getVisibleNavRoutes(privileged, "t1").map((route) => route.to);
    expect(visible).toContain("/dashboard/settings");
    expect(visible).toContain("/dashboard/audit");
  });

  it("filters command palette results by label and keywords", () => {
    const matches = filterNavRoutes(NAV_ROUTES, "mfa").map((route) => route.to);
    expect(matches).toEqual(["/dashboard/settings"]);
  });
});
