import {
  canAccessAdminRoutes,
  canAccessAuditLogs,
  canAccessTenantSettings,
  requiresAdminMfa,
  requiresEmailVerification,
} from "./access";
import type { AuthUser } from "../../api/auth";

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
    memberships: [
      {
        tenant_id: "tenant-1",
        tenant_name: "Tenant",
        tenant_slug: "tenant",
        status: "active",
        role: {
          id: "role-1",
          name: "Owner",
          slug: "owner",
          permission_codes: [],
        },
      },
    ],
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

  it("allows settings for users with settings:write permission", () => {
    expect(
      canAccessTenantSettings(
        makeUser({
          memberships: [
            {
              tenant_id: "tenant-1",
              tenant_name: "Tenant",
              tenant_slug: "tenant",
              status: "active",
              role: {
                id: "role-1",
                name: "Owner",
                slug: "owner",
                permission_codes: ["settings:write"],
              },
            },
          ],
        })
      )
    ).toBe(true);
    expect(canAccessTenantSettings(makeUser())).toBe(false);
  });

  it("allows audit for users with audit:read permission", () => {
    expect(
      canAccessAuditLogs(
        makeUser({
          memberships: [
            {
              tenant_id: "tenant-1",
              tenant_name: "Tenant",
              tenant_slug: "tenant",
              status: "active",
              role: {
                id: "role-1",
                name: "Owner",
                slug: "owner",
                permission_codes: ["audit:read"],
              },
            },
          ],
        })
      )
    ).toBe(true);
    expect(canAccessAuditLogs(makeUser())).toBe(false);
  });
});
