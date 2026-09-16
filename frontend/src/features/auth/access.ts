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

export function getActiveMembership(user: AuthUser | null, tenantId: string | null) {
  if (!user || !tenantId) {
    return null;
  }
  return user.memberships.find((membership) => membership.tenant_id === tenantId) ?? null;
}

function hasPermission(user: AuthUser | null, permissionCode: string, tenantId: string | null) {
  const membership = getActiveMembership(user, tenantId);
  return Boolean(membership?.role?.permission_codes.includes(permissionCode));
}

export function canAccessTenantSettings(user: AuthUser | null, tenantId: string | null) {
  return hasPermission(user, "settings:write", tenantId);
}

export function canAccessAuditLogs(user: AuthUser | null, tenantId: string | null) {
  return hasPermission(user, "audit:read", tenantId);
}

export function canWriteBriefs(user: AuthUser | null, tenantId: string | null) {
  return hasPermission(user, "briefs:write", tenantId);
}

export function canWriteContent(user: AuthUser | null, tenantId: string | null) {
  return hasPermission(user, "content:write", tenantId);
}
