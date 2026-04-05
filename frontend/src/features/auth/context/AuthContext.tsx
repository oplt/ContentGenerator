import {
    useEffect,
    useState,
    type PropsWithChildren,
} from "react";
import { logout as logoutRequest, refresh, type AuthUser } from "../../../api/auth";
import { authStore } from "../store/authStore";
import { AuthContext } from "./authContext";

export function AuthProvider({ children }: PropsWithChildren) {
    const [isReady, setIsReady] = useState(false);
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);

    useEffect(() => {
        refresh()
            .then((data) => {
                authStore.setAccessToken(data.access_token);
                setCurrentUser(data.user);
                setIsAuthenticated(true);
            })
            .catch(() => {
                authStore.setAccessToken(null);
                setCurrentUser(null);
                setIsAuthenticated(false);
            })
            .finally(() => setIsReady(true));
    }, []);

    async function logout() {
        await logoutRequest().catch(() => undefined);
        authStore.setAccessToken(null);
        setCurrentUser(null);
        setIsAuthenticated(false);
    }

    function setAuthenticated(token: string, user: AuthUser) {
        authStore.setAccessToken(token);
        setCurrentUser(user);
        setIsAuthenticated(true);
    }

    return (
        <AuthContext.Provider
            value={{
                isReady,
                isAuthenticated,
                isAdmin: currentUser?.is_admin ?? false,
                currentUser,
                logout,
                setAuthenticated,
            }}
        >
            {children}
        </AuthContext.Provider>
    );
}
