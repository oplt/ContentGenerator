import {
  canAccessAdminRoutes,
  canAccessAuditLogs,
  canAccessTenantSettings,
  getActiveMembership,
  requiresAdminMfa,
  requiresEmailVerification,
} from "./access";
import type { AuthUser } from "../../api/auth";

function makeMembership(
  tenantId: string,
  permissionCodes: string[],
  overrides: Partial<AuthUser["memberships"][number]> = {}
): AuthUser["memberships"][number] {
  return {
    tenant_id: tenantId,
    tenant_name: `Tenant ${tenantId}`,
    tenant_slug: tenantId,
    status: "active",
    role: {
      id: `role-${tenantId}`,
      name: "Role",
      slug: "role",
      permission_codes: permissionCodes,
    },
    ...overrides,
  };
}

function makeUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: "user-1",
    email: "user@example.com",
    full_name: "User",
    is_verified: true,
    is_admin: false,
    mfa_enabled: false,
    default_tenant_id: null,
    rbac_mode: "tenant",
    memberships: [makeMembership("tenant-1", [])],
    ...overrides,
  };
}

describe("auth access helpers", () => {
  it("requires email verification until the user is verified", () => {
    expect(requiresEmailVerification(makeUser({ is_verified: false }))).toBe(true);
    expect(requiresEmailVerification(makeUser({ is_verified: true }))).toBe(false);
  });

  it("requires MFA for admin accounts that do not have it enabled", () => {
    expect(requiresAdminMfa(makeUser({ is_admin: true, mfa_enabled: false }))).toBe(true);
    expect(requiresAdminMfa(makeUser({ is_admin: true, mfa_enabled: true }))).toBe(false);
    expect(requiresAdminMfa(makeUser({ is_admin: false, mfa_enabled: false }))).toBe(false);
  });

  it("allows admin routes only for admin accounts with MFA enabled", () => {
    expect(canAccessAdminRoutes(makeUser({ is_admin: true, mfa_enabled: true }))).toBe(true);
    expect(canAccessAdminRoutes(makeUser({ is_admin: true, mfa_enabled: false }))).toBe(false);
    expect(canAccessAdminRoutes(makeUser({ is_admin: false, mfa_enabled: true }))).toBe(false);
  });

  it("scopes settings permission to the active tenant only", () => {
    const user = makeUser({
      memberships: [
        makeMembership("tenant-a", ["settings:write"]),
        makeMembership("tenant-b", ["audit:read"]),
      ],
    });

    expect(canAccessTenantSettings(user, "tenant-a")).toBe(true);
    expect(canAccessTenantSettings(user, "tenant-b")).toBe(false);
    expect(canAccessTenantSettings(user, null)).toBe(false);
  });

  it("scopes audit permission to the active tenant only", () => {
    const user = makeUser({
      memberships: [
        makeMembership("tenant-a", ["settings:write"]),
        makeMembership("tenant-b", ["audit:read"]),
      ],
    });

    expect(canAccessAuditLogs(user, "tenant-b")).toBe(true);
    expect(canAccessAuditLogs(user, "tenant-a")).toBe(false);
    expect(canAccessAuditLogs(makeUser(), "tenant-1")).toBe(false);
  });

  it("returns the membership for the active tenant", () => {
    const user = makeUser({
      memberships: [makeMembership("tenant-a", []), makeMembership("tenant-b", ["audit:read"])],
    });

    expect(getActiveMembership(user, "tenant-b")?.tenant_id).toBe("tenant-b");
    expect(getActiveMembership(user, "missing")).toBeNull();
  });
});
