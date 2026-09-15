import { useWorkspaceStore } from "../store/workspaceStore";

/** Active tenant id + query enablement for tenant-scoped React Query usage. */
export function useTenantScope() {
  const tenantId = useWorkspaceStore((state) => state.tenantId);
  return {
    tenantId,
    enabled: Boolean(tenantId),
  };
}
