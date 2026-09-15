import { QueryClient } from "@tanstack/react-query";
import type { AuthUser } from "../api/auth";
import { queryClient } from "./queryClient";
import { queryKeys } from "./queryKeys";
import { clearTenantQueryCache, switchActiveTenant } from "./tenantCache";
import { useWorkspaceStore } from "../store/workspaceStore";

vi.mock("./queryClient", () => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return { queryClient: client };
});

function makeUser(): AuthUser {
  return {
    id: "user-1",
    email: "user@example.com",
    full_name: "User",
    is_verified: true,
    is_admin: false,
    mfa_enabled: false,
    default_tenant_id: "tenant-a",
    rbac_mode: "tenant",
    memberships: [
      {
        tenant_id: "tenant-a",
        tenant_name: "Tenant A",
        tenant_slug: "a",
        status: "active",
        role: { id: "r1", name: "Owner", slug: "owner", permission_codes: ["settings:write"] },
      },
      {
        tenant_id: "tenant-b",
        tenant_name: "Tenant B",
        tenant_slug: "b",
        status: "active",
        role: { id: "r2", name: "Viewer", slug: "viewer", permission_codes: ["audit:read"] },
      },
    ],
  };
}

describe("switchActiveTenant", () => {
  beforeEach(() => {
    queryClient.clear();
    useWorkspaceStore.setState({ tenantId: "tenant-a", tenantName: "Tenant A" });
  });

  it("cancels in-flight tenant-A work, drops A cache, keeps B headers ready", async () => {
    let resolveA: ((value: string) => void) | undefined;
    const delayedA = new Promise<string>((resolve) => {
      resolveA = resolve;
    });

    const fetchA = vi.fn().mockImplementation(() => delayedA);
    const fetchB = vi.fn().mockResolvedValue("b-data");

    const queryA = queryClient.fetchQuery({
      queryKey: queryKeys.sources("tenant-a"),
      queryFn: fetchA,
    });
    queryClient.setQueryData(queryKeys.analytics("tenant-a"), "stale-a");
    queryClient.setQueryData(queryKeys.sources("tenant-b"), "cached-b");

    const switched = await switchActiveTenant("tenant-b", makeUser());
    expect(switched).toBe(true);
    expect(useWorkspaceStore.getState().tenantId).toBe("tenant-b");
    expect(queryClient.getQueryData(queryKeys.analytics("tenant-a"))).toBeUndefined();
    expect(queryClient.getQueryData(queryKeys.sources("tenant-a"))).toBeUndefined();
    expect(queryClient.getQueryData(queryKeys.sources("tenant-b"))).toBe("cached-b");

    resolveA?.("late-a");
    await expect(queryA).rejects.toBeTruthy();
    expect(queryClient.getQueryData(queryKeys.sources("tenant-a"))).toBeUndefined();

    await queryClient.fetchQuery({
      queryKey: queryKeys.sources("tenant-b"),
      queryFn: fetchB,
    });
    expect(fetchB).toHaveBeenCalled();
  });

  it("clears all tenant cache on logout helper", async () => {
    queryClient.setQueryData(queryKeys.sources("tenant-a"), "a");
    queryClient.setQueryData(queryKeys.appConfig, { mfa_access: false });
    await clearTenantQueryCache();
    expect(queryClient.getQueryData(queryKeys.sources("tenant-a"))).toBeUndefined();
    expect(queryClient.getQueryData(queryKeys.appConfig)).toEqual({ mfa_access: false });
  });
});
