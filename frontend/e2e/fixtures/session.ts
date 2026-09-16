/** Shared demo session for mocked E2E flows. */
export const DEMO_SESSION_USER = {
    id: "user-1",
    email: "demo@example.com",
    full_name: "Demo User",
    is_verified: true,
    is_admin: true,
    mfa_enabled: true,
    default_tenant_id: "tenant-1",
    memberships: [
      {
        tenant_id: "tenant-1",
        tenant_name: "Demo Tenant",
        tenant_slug: "demo",
        status: "active",
        role: {
          id: "role-1",
          name: "Owner",
          slug: "owner",
          permission_codes: ["sources:write", "content:write", "publishing:write", "settings:write", "analytics:read"],
        },
      },
    ],
  };
  