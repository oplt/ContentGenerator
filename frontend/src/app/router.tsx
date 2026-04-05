import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "../features/auth/AuthContext";
import { LoadingState } from "../components/ui/LoadingState";
import { AppShell } from "../components/layout/AppShell";
import AuthHomePage from "../pages/AuthHomePage";
import DashboardPage from "../pages/DashboardPage";
import SourcesPage from "../pages/SourcesPage";
import StoriesPage from "../pages/StoriesPage";
import StoryDetailPage from "../pages/StoryDetailPage";
import ContentPage from "../pages/ContentPage";
import ContentDetailPage from "../pages/ContentDetailPage";
import AnalyticsPage from "../pages/AnalyticsPage";
import BrandProfilePage from "../pages/BrandProfilePage";
import SettingsPage from "../pages/SettingsPage";
import AuditPage from "../pages/AuditPage";
import VerifyEmailPage from "../pages/VerifyEmailPage";
import ResetPasswordPage from "../pages/ResetPasswordPage";

function ProtectedApp() {
  const { isReady, isAuthenticated } = useAuth();
  if (!isReady) {
    return <LoadingState label="Restoring workspace" />;
  }
  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AuthHomePage />} />
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/dashboard" element={<ProtectedApp />}>
          <Route index element={<DashboardPage />} />
          <Route path="sources" element={<SourcesPage />} />
          <Route path="stories" element={<StoriesPage />} />
          <Route path="stories/:id" element={<StoryDetailPage />} />
          <Route path="content" element={<ContentPage />} />
          <Route path="content/:id" element={<ContentDetailPage />} />
          <Route path="approvals" element={<Navigate to="/dashboard/content?tab=approvals" replace />} />
          <Route path="publishing" element={<Navigate to="/dashboard/content?tab=publishing" replace />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="brand-profile" element={<BrandProfilePage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="audit" element={<AuditPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
