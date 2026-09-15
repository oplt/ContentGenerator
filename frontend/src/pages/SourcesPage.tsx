import { lazy, Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import { SectionHelp } from "../components/ui/HelpDisclosure";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { resolveQueriesStatus } from "../components/ui/QueryBoundary";
import { useDeepLinkTab } from "../hooks/useDeepLinkTab";
import {
  SOURCES_TABS,
  useSourcesMutations,
  useSourcesQueries,
  type AddMode,
  type SourceForm,
  type SourcesTab,
} from "../features/sources";

const AddSourcePanel = lazy(() =>
  import("../features/sources/AddSourcePanel").then((m) => ({ default: m.AddSourcePanel })),
);
const ConfiguredSourcesPanel = lazy(() =>
  import("../features/sources/ConfiguredSourcesPanel").then((m) => ({
    default: m.ConfiguredSourcesPanel,
  })),
);
const FetchRunsPanel = lazy(() =>
  import("../features/sources/FetchRunsPanel").then((m) => ({ default: m.FetchRunsPanel })),
);

function TabFallback() {
  return <LoadingState label="Loading sources section" />;
}

export default function SourcesPage() {
  const [deletingSourceId, setDeletingSourceId] = useState<string | null>(null);
  const [editingSourceId, setEditingSourceId] = useState<string | null>(null);
  const [savingSourceId, setSavingSourceId] = useState<string | null>(null);
  const [importingCatalogId, setImportingCatalogId] = useState<string | null>(null);
  const [addMode, setAddMode] = useState<AddMode>("catalog");
  const [lastIngestRunId, setLastIngestRunId] = useState<string | null>(null);
  const [sourcesTab, setSourcesTab] = useDeepLinkTab<SourcesTab>("tab", SOURCES_TABS, "configured");

  const form = useForm<SourceForm>({
    defaultValues: {
      source_type: "rss",
      category: "technology",
      source_tier: "signal",
      content_vertical: "general",
    },
  });

  const {
    tenantId,
    sources,
    health,
    rawArticles,
    defaultPollingInterval,
    existingUrls,
    healthBySourceId,
    sourceNameById,
  } = useSourcesQueries({ sourcesTab, addMode });

  const {
    createMutation,
    importMutation,
    updateMutation,
    ingestMutation,
    deleteMutation,
    manualPollMutation,
    disableMutation,
  } = useSourcesMutations({
    tenantId,
    onIngestRunId: setLastIngestRunId,
  });

  const shellStatus = resolveQueriesStatus([sources]);

  if (shellStatus.status === "loading") {
    return <LoadingState label="Loading sources" />;
  }
  if (shellStatus.status === "error") {
    return <ErrorState message="Sources could not be loaded." onRetry={shellStatus.retry} />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Sources</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Configure ingestion inputs and review health for this workspace.
        </p>
      </div>

      <SectionHelp summary="Source tiers and polling">
        Authoritative (Tier 1) sources confirm stories before content generation. Polling intervals inherit workspace
        defaults unless overridden per source. Destructive deletes require confirmation and cannot be undone from the UI.
      </SectionHelp>

      <Tabs value={sourcesTab} onValueChange={(value) => setSourcesTab(value as SourcesTab)} className="space-y-6">
        <TabsList>
          <TabsTrigger value="configured">Configured</TabsTrigger>
          <TabsTrigger value="add">Add source</TabsTrigger>
          <TabsTrigger value="activity">Activity / Fetch Runs</TabsTrigger>
        </TabsList>

        <TabsContent value="add" className="space-y-6">
          {sourcesTab === "add" ? (
            <Suspense fallback={<TabFallback />}>
              <AddSourcePanel
                addMode={addMode}
                setAddMode={setAddMode}
                form={form}
                catalogActive={sourcesTab === "add"}
                existingUrls={existingUrls}
                importingCatalogId={importingCatalogId}
                setImportingCatalogId={setImportingCatalogId}
                defaultPollingInterval={defaultPollingInterval}
                createMutation={createMutation}
                importMutation={importMutation}
                onSourceAdded={() => setSourcesTab("configured")}
              />
            </Suspense>
          ) : null}
        </TabsContent>

        <TabsContent value="configured" className="space-y-6">
          {sourcesTab === "configured" ? (
            <Suspense fallback={<TabFallback />}>
              <ConfiguredSourcesPanel
                sources={sources.data ?? []}
                health={health}
                rawArticles={rawArticles}
                healthBySourceId={healthBySourceId}
                editingSourceId={editingSourceId}
                setEditingSourceId={setEditingSourceId}
                savingSourceId={savingSourceId}
                setSavingSourceId={setSavingSourceId}
                deletingSourceId={deletingSourceId}
                setDeletingSourceId={setDeletingSourceId}
                lastIngestRunId={lastIngestRunId}
                updateMutation={updateMutation}
                ingestMutation={ingestMutation}
                manualPollMutation={manualPollMutation}
                disableMutation={disableMutation}
                deleteMutation={deleteMutation}
                onOpenActivity={() => setSourcesTab("activity")}
                onAddSource={() => setSourcesTab("add")}
              />
            </Suspense>
          ) : null}
        </TabsContent>

        <TabsContent value="activity" className="space-y-6">
          {sourcesTab === "activity" ? (
            <Suspense fallback={<TabFallback />}>
              <FetchRunsPanel active sourceNameById={sourceNameById} />
            </Suspense>
          ) : null}
        </TabsContent>
      </Tabs>
    </div>
  );
}
