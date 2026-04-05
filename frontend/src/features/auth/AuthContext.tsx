import { createContext, useContext, useEffect, useState, type PropsWithChildren } from "react";
import { logout, refresh, signIn, signUp, type AuthUser } from "../../api/auth";
import { authStore } from "./authStore";
import { useWorkspaceStore } from "../../store/workspaceStore";

type AuthContextValue = {
  isReady: boolean;
  isAuthenticated: boolean;
  currentUser: AuthUser | null;
  signInWithPassword: (payload: { email: string; password: string }) => Promise<void>;
  signUpWithPassword: (payload: { email: string; password: string; full_name?: string }) => Promise<void>;
  signOut: () => Promise<void>;
  setActiveTenant: (tenantId: string) => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function syncTenantSelection(
  setTenant: (tenantId: string | null, tenantName: string | null) => void,
  user: AuthUser | null
) {
  if (!user) {
    setTenant(null, null);
    return;
  }

  const membership =
    user.memberships.find((item) => item.tenant_id === user.default_tenant_id) ?? user.memberships[0];
  setTenant(membership?.tenant_id ?? null, membership?.tenant_name ?? null);
}

export function AuthProvider({ children }: PropsWithChildren) {
  const [isReady, setIsReady] = useState(false);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const setTenant = useWorkspaceStore((state) => state.setTenant);

  useEffect(() => {
    refresh()
      .then((data) => {
        authStore.setAccessToken(data.access_token);
        setCurrentUser(data.user);
        syncTenantSelection(setTenant, data.user);
      })
      .catch(() => {
        authStore.setAccessToken(null);
        setCurrentUser(null);
      })
      .finally(() => {
        setIsReady(true);
      });
  }, [setTenant]);

  const value: AuthContextValue = {
    isReady,
    isAuthenticated: Boolean(currentUser),
    currentUser,
    signInWithPassword: async (payload) => {
      const data = await signIn(payload);
      authStore.setAccessToken(data.access_token);
      setCurrentUser(data.user);
      syncTenantSelection(setTenant, data.user);
    },
    signUpWithPassword: async (payload) => {
      const data = await signUp(payload);
      authStore.setAccessToken(data.access_token);
      setCurrentUser(data.user);
      syncTenantSelection(setTenant, data.user);
    },
    signOut: async () => {
      await logout().catch(() => undefined);
      authStore.setAccessToken(null);
      setCurrentUser(null);
      syncTenantSelection(setTenant, null);
    },
    setActiveTenant: (tenantId) => {
      const membership = currentUser?.memberships.find((item) => item.tenant_id === tenantId);
      if (membership) {
        setTenant(membership.tenant_id, membership.tenant_name);
      }
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
