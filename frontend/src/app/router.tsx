import React from "react";
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

// Lazy load heavy components
const AuthHomePage = React.lazy(() => import("../pages/AuthHomePage"));
const DashboardPage = React.lazy(() => import("../pages/DashboardPage"));
const SourcesPage = React.lazy(() => import("../pages/SourcesPage"));
const StoriesPage = React.lazy(() => import("../pages/StoriesPage"));
const StoryDetailPage = React.lazy(() => import("../pages/StoryDetailPage"));
const ApprovalsPage = React.lazy(() => import("../pages/ApprovalsPage"));
const ContentPage = React.lazy(() => import("../pages/ContentPage"));
const ContentDetailPage = React.lazy(() => import("../pages/ContentDetailPage"));
const AnalyticsPage = React.lazy(() => import("../pages/AnalyticsPage"));
const BrandProfilePage = React.lazy(() => import("../pages/BrandProfilePage"));
const ConnectedAccountsPage = React.lazy(() => import("../pages/ConnectedAccountsPage"));
const SettingsPage = React.lazy(() => import("../pages/SettingsPage"));
const AuditPage = React.lazy(() => import("../pages/AuditPage"));
const EditorialBriefsPage = React.lazy(() => import("../pages/EditorialBriefsPage"));
const PublishingQueuePage = React.lazy(() => import("../pages/PublishingQueuePage"));
const VerifyEmailPage = React.lazy(() => import("../pages/VerifyEmailPage"));
const ResetPasswordPage = React.lazy(() => import("../pages/ResetPasswordPage"));
const TrendingReposPage = React.lazy(() => import("../pages/TrendingReposPage"));

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
        <Route path="/" element={
          <React.Suspense fallback={<LoadingState label="Loading page..." />}>  
            <AuthHomePage />
          </React.Suspense>
        } />
        <Route path="/verify-email" element={
          <React.Suspense fallback={<LoadingState label="Loading page..." />}>  
            <VerifyEmailPage />
          </React.Suspense>
        } />
        <Route path="/reset-password" element={
          <React.Suspense fallback={<LoadingState label="Loading page..." />}>  
            <ResetPasswordPage />
          </React.Suspense>
        } />
        <Route path="/dashboard" element={<ProtectedApp />}>          
          <Route index element={
            <React.Suspense fallback={<LoadingState label="Loading dashboard..." />}>  
              <DashboardPage />
            </React.Suspense>
          } />
          <Route path="sources" element={
            <React.Suspense fallback={<LoadingState label="Loading sources..." />}>  
              <SourcesPage />
            </React.Suspense>
          } />
          <Route path="trends" element={
            <React.Suspense fallback={<LoadingState label="Loading trends..." />}>  
              <StoriesPage />
            </React.Suspense>
          } />
          <Route path="trends/:id" element={
            <React.Suspense fallback={<LoadingState label="Loading story..." />}>  
              <StoryDetailPage />
            </React.Suspense>
          } />
          <Route path="stories" element={
            <React.Suspense fallback={<LoadingState label="Loading stories..." />}>  
              <StoriesPage />
            </React.Suspense>
          } />
          <Route path="stories/:id" element={
            <React.Suspense fallback={<LoadingState label="Loading story..." />}>  
              <StoryDetailPage />
            </React.Suspense>
          } />
          <Route path="content" element={
            <React.Suspense fallback={<LoadingState label="Loading content..." />}>  
              <ContentPage />
            </React.Suspense>
          } />
          <Route path="content/:id" element={
            <React.Suspense fallback={<LoadingState label="Loading content..." />}>  
              <ContentDetailPage />
            </React.Suspense>
          } />
          <Route path="approvals" element={
            <React.Suspense fallback={<LoadingState label="Loading approvals..." />}>  
              <ApprovalsPage />
            </React.Suspense>
          } />
          <Route path="publishing" element={
            <React.Suspense fallback={<LoadingState label="Loading publishing..." />}>  
              <PublishingQueuePage />
            </React.Suspense>
          } />
          <Route path="briefs" element={
            <React.Suspense fallback={<LoadingState label="Loading briefs..." />}>  
              <EditorialBriefsPage />
            </React.Suspense>
          } />
          <Route path="analytics" element={
            <React.Suspense fallback={<LoadingState label="Loading analytics..." />}>  
              <AnalyticsPage />
            </React.Suspense>
          } />
          <Route path="accounts" element={
            <React.Suspense fallback={<LoadingState label="Loading accounts..." />}>  
              <ConnectedAccountsPage />
            </React.Suspense>
          } />
          <Route path="brand-profile" element={
            <React.Suspense fallback={<LoadingState label="Loading profile..." />}>  
              <BrandProfilePage />
            </React.Suspense>
          } />
          <Route path="trending-repos" element={
            <React.Suspense fallback={<LoadingState label="Loading trending..." />}>  
              <TrendingReposPage />
            </React.Suspense>
          } />
          <Route element={<SettingsRoute />}>            
            <Route path="settings" element={
              <React.Suspense fallback={<LoadingState label="Loading settings..." />}>  
                <SettingsPage />
              </React.Suspense>
            } />
          </Route>
          <Route element={<AuditRoute />}>            
            <Route path="audit" element={
              <React.Suspense fallback={<LoadingState label="Loading audit..." />}>  
                <AuditPage />
              </React.Suspense>
            } />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
