import { Navigate } from "react-router-dom";
import { Box, CircularProgress } from "@mui/material";

type Props = {
    isReady: boolean;
    isAuthenticated: boolean;
    isAdmin?: boolean;
    requireAdmin?: boolean;
    redirectTo?: string;
    children?: React.ReactNode;
};

export function ProtectedRoute({
    isReady,
    isAuthenticated,
    isAdmin = false,
    requireAdmin = false,
    redirectTo = "/",
    children,
}: Props) {
    if (!isReady) {
        return (
            <Box sx={{ display: "grid", placeItems: "center", minHeight: "100vh" }}>
                <CircularProgress />
            </Box>
        );
    }
    if (!isAuthenticated) return <Navigate to={redirectTo} replace />;
    if (requireAdmin && !isAdmin) return <Navigate to="/dashboard" replace />;
    return <>{children}</>;
}
