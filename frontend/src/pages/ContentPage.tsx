import { lazy, Suspense } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { LoadingState } from "../components/ui/LoadingState";
import { useDeepLinkTab } from "../hooks/useDeepLinkTab";

const PlansTab = lazy(() =>
  import("../features/content/PlansTab").then((m) => ({ default: m.PlansTab })),
);
const ApprovalsTab = lazy(() =>
  import("../features/content/ApprovalsTab").then((m) => ({ default: m.ApprovalsTab })),
);
const PublishingTab = lazy(() =>
  import("../features/content/PublishingTab").then((m) => ({ default: m.PublishingTab })),
);

const TABS = ["plans", "approvals", "publishing"] as const;
type Tab = (typeof TABS)[number];

function TabFallback() {
  return <LoadingState label="Loading content section" />;
}

export default function ContentPage() {
  const [activeTab, setActiveTab] = useDeepLinkTab<Tab>("tab", TABS, "plans");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Content</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage content plans, route approvals, and track publishing.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as Tab)}>
        <TabsList>
          <TabsTrigger value="plans">Plans &amp; Jobs</TabsTrigger>
          <TabsTrigger value="approvals">Approvals</TabsTrigger>
          <TabsTrigger value="publishing">Publishing</TabsTrigger>
        </TabsList>

        <TabsContent value="plans" className="mt-6">
          {activeTab === "plans" ? (
            <Suspense fallback={<TabFallback />}>
              <PlansTab active />
            </Suspense>
          ) : null}
        </TabsContent>
        <TabsContent value="approvals" className="mt-6">
          {activeTab === "approvals" ? (
            <Suspense fallback={<TabFallback />}>
              <ApprovalsTab active />
            </Suspense>
          ) : null}
        </TabsContent>
        <TabsContent value="publishing" className="mt-6">
          {activeTab === "publishing" ? (
            <Suspense fallback={<TabFallback />}>
              <PublishingTab active />
            </Suspense>
          ) : null}
        </TabsContent>
      </Tabs>
    </div>
  );
}
