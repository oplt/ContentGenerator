import { createContext, useCallback, useContext, useEffect, useState, type PropsWithChildren } from "react";
import { logout, refresh, signIn, signUp, type AuthResponse, type AuthUser } from "../../api/auth";
import { useWorkspaceStore } from "../../store/workspaceStore";

type AuthContextValue = {
  isReady: boolean;
  isAuthenticated: boolean;
  currentUser: AuthUser | null;
  reloadSession: () => Promise<void>;
  signInWithPassword: (payload: { email: string; password: string; mfa_code?: string }) => Promise<void>;
  signUpWithPassword: (payload: { email: string; password: string; full_name?: string }) => Promise<AuthResponse>;
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

  const loadSession = useCallback(async () => {
    try {
      const data = await refresh();
      setCurrentUser(data.user ?? null);
      syncTenantSelection(setTenant, data.user ?? null);
    } catch {
      setCurrentUser(null);
      syncTenantSelection(setTenant, null);
    }
  }, [setTenant]);

  useEffect(() => {
    let active = true;

    refresh()
      .then((data) => {
        if (!active) {
          return;
        }
        setCurrentUser(data.user ?? null);
        syncTenantSelection(setTenant, data.user ?? null);
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setCurrentUser(null);
        syncTenantSelection(setTenant, null);
      })
      .finally(() => {
        if (active) {
          setIsReady(true);
        }
      });

    return () => {
      active = false;
    };
  }, [setTenant]);

  const value: AuthContextValue = {
    isReady,
    isAuthenticated: Boolean(currentUser),
    currentUser,
    reloadSession: loadSession,
    signInWithPassword: async (payload) => {
      const data = await signIn(payload);
      if (!data.user) {
        throw new Error("Session could not be established.");
      }
      setCurrentUser(data.user);
      syncTenantSelection(setTenant, data.user);
    },
    signUpWithPassword: async (payload) => {
      const data = await signUp(payload);
      setCurrentUser(data.user ?? null);
      syncTenantSelection(setTenant, null);
      return data;
    },
    signOut: async () => {
      await logout().catch(() => undefined);
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
