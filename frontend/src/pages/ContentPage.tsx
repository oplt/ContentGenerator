import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { ApprovalsTab, PlansTab, PublishingTab } from "../features/content";
import { useDeepLinkTab } from "../hooks/useDeepLinkTab";

const TABS = ["plans", "approvals", "publishing"] as const;
type Tab = (typeof TABS)[number];

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

        <TabsContent value="plans" className="mt-6" forceMount hidden={activeTab !== "plans"}>
          <PlansTab active={activeTab === "plans"} />
        </TabsContent>

        <TabsContent value="approvals" className="mt-6" forceMount hidden={activeTab !== "approvals"}>
          <ApprovalsTab active={activeTab === "approvals"} />
        </TabsContent>

        <TabsContent value="publishing" className="mt-6" forceMount hidden={activeTab !== "publishing"}>
          <PublishingTab active={activeTab === "publishing"} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
