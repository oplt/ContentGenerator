import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "../features/auth/AuthContext";
import {
  canAccessAuditLogs,
  canAccessTenantSettings,
  requiresAdminMfa,
  requiresEmailVerification,
} from "../features/auth/access";
import { LoadingState } from "../components/ui/LoadingState";
import { AppShell } from "../components/layout/AppShell";
import AuthHomePage from "../pages/AuthHomePage";
import DashboardPage from "../pages/DashboardPage";
import SourcesPage from "../pages/SourcesPage";
import StoriesPage from "../pages/StoriesPage";
import StoryDetailPage from "../pages/StoryDetailPage";
import ApprovalsPage from "../pages/ApprovalsPage";
import ContentPage from "../pages/ContentPage";
import ContentDetailPage from "../pages/ContentDetailPage";
import AnalyticsPage from "../pages/AnalyticsPage";
import BrandProfilePage from "../pages/BrandProfilePage";
import ConnectedAccountsPage from "../pages/ConnectedAccountsPage";
import SettingsPage from "../pages/SettingsPage";
import AuditPage from "../pages/AuditPage";
import EditorialBriefsPage from "../pages/EditorialBriefsPage";
import PublishingQueuePage from "../pages/PublishingQueuePage";
import VerifyEmailPage from "../pages/VerifyEmailPage";
import ResetPasswordPage from "../pages/ResetPasswordPage";
import TrendingReposPage from "../pages/TrendingReposPage";

function ProtectedApp() {
  const { isReady, isAuthenticated, currentUser } = useAuth();
  if (!isReady) {
    return <LoadingState label="Restoring workspace" />;
  }
  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }
  if (requiresEmailVerification(currentUser)) {
    return <Navigate to="/verify-email" replace />;
  }
  if (requiresAdminMfa(currentUser)) {
    return <Navigate to="/verify-email?required=mfa" replace />;
  }
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}

function SettingsRoute() {
  const { isReady, isAuthenticated, currentUser } = useAuth();
  if (!isReady) {
    return <LoadingState label="Checking access" />;
  }
  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }
  if (requiresEmailVerification(currentUser)) {
    return <Navigate to="/verify-email" replace />;
  }
  if (!canAccessTenantSettings(currentUser)) {
    return <Navigate to="/dashboard" replace />;
  }
  return <Outlet />;
}

function AuditRoute() {
  const { isReady, isAuthenticated, currentUser } = useAuth();
  if (!isReady) {
    return <LoadingState label="Checking access" />;
  }
  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }
  if (requiresEmailVerification(currentUser)) {
    return <Navigate to="/verify-email" replace />;
  }
  if (!canAccessAuditLogs(currentUser)) {
    return <Navigate to="/dashboard" replace />;
  }
  return <Outlet />;
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
          <Route path="trends" element={<StoriesPage />} />
          <Route path="trends/:id" element={<StoryDetailPage />} />
          <Route path="stories" element={<StoriesPage />} />
          <Route path="stories/:id" element={<StoryDetailPage />} />
          <Route path="content" element={<ContentPage />} />
          <Route path="content/:id" element={<ContentDetailPage />} />
          <Route path="approvals" element={<ApprovalsPage />} />
          <Route path="publishing" element={<PublishingQueuePage />} />
          <Route path="briefs" element={<EditorialBriefsPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="accounts" element={<ConnectedAccountsPage />} />
          <Route path="brand-profile" element={<BrandProfilePage />} />
          <Route path="trending-repos" element={<TrendingReposPage />} />
          <Route element={<SettingsRoute />}>
            <Route path="settings" element={<SettingsPage />} />
          </Route>
          <Route element={<AuditRoute />}>
            <Route path="audit" element={<AuditPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
