import type { AuthUser } from "../../api/auth";

export function requiresEmailVerification(user: AuthUser | null) {
  return Boolean(user && !user.is_verified);
}

export function requiresAdminMfa(user: AuthUser | null) {
  return Boolean(user?.is_admin && !user.mfa_enabled);
}

export function canAccessAdminRoutes(user: AuthUser | null) {
  return Boolean(user?.is_admin && user.mfa_enabled);
}

function hasPermission(user: AuthUser | null, permissionCode: string) {
  return Boolean(
    user?.memberships.some((membership) => membership.role?.permission_codes.includes(permissionCode))
  );
}

export function canAccessTenantSettings(user: AuthUser | null) {
  return hasPermission(user, "settings:write");
}

export function canAccessAuditLogs(user: AuthUser | null) {
  return hasPermission(user, "audit:read");
}
