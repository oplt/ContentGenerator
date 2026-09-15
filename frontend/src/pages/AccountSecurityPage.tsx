import { Navigate } from "react-router-dom";

/** Legacy route — account lives under Settings → Account. */
export default function AccountSecurityPage() {
  return <Navigate to="/dashboard/settings?tab=account" replace />;
}
