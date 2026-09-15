import type { AuthUser } from "../api/auth";
import { useWorkspaceStore } from "../store/workspaceStore";
import { queryClient } from "./queryClient";
import { isTenantQueryFor, isTenantQueryKey } from "./queryKeys";

/**
 * Atomic tenant switch: cancel in-flight tenant queries → set active tenant →
 * drop other tenants' cached data → refetch active tenant observers.
 */
export async function switchActiveTenant(tenantId: string, user: AuthUser | null): Promise<boolean> {
  const membership = user?.memberships.find((item) => item.tenant_id === tenantId);
  if (!membership) {
    return false;
  }

  const previousTenantId = useWorkspaceStore.getState().tenantId;
  if (previousTenantId === membership.tenant_id) {
    return true;
  }

  await queryClient.cancelQueries({
    predicate: (query) => isTenantQueryKey(query.queryKey),
  });

  useWorkspaceStore.getState().setTenant(membership.tenant_id, membership.tenant_name);

  queryClient.removeQueries({
    predicate: (query) =>
      isTenantQueryKey(query.queryKey) && !isTenantQueryFor(membership.tenant_id, query.queryKey),
  });

  await queryClient.invalidateQueries({
    predicate: (query) => isTenantQueryFor(membership.tenant_id, query.queryKey),
  });

  return true;
}

export async function clearTenantQueryCache(): Promise<void> {
  await queryClient.cancelQueries({
    predicate: (query) => isTenantQueryKey(query.queryKey),
  });
  queryClient.removeQueries({
    predicate: (query) => isTenantQueryKey(query.queryKey),
  });
}
