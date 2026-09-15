import { useMemo } from "react";
import { useAuth } from "../features/auth/AuthContext";
import { useWorkspaceStore } from "../store/workspaceStore";
import { getVisibleNavRoutes, type NavRoute } from "./routeManifest";

export function useNavRoutes(): NavRoute[] {
  const { currentUser } = useAuth();
  const tenantId = useWorkspaceStore((state) => state.tenantId);
  return useMemo(() => getVisibleNavRoutes(currentUser, tenantId), [currentUser, tenantId]);
}
