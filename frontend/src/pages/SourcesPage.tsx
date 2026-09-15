import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import {
  createSource,
  disableSource,
  deleteSource,
  getRawArticles,
  getSourceHealth,
  getSources,
  importCatalogSource,
  triggerManualPoll,
  triggerIngestion,
  updateSource,
} from "../api/sources";
import { getTenantSettings } from "../api/settings";
import { useTenantScope } from "../hooks/useTenantScope";
import { queryClient } from "../lib/queryClient";
import { queryKeys } from "../lib/queryKeys";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { LoadingState } from "../components/ui/LoadingState";
import { EmptyState } from "../components/ui/EmptyState";
import { ErrorState } from "../components/ui/ErrorState";
import { HelpDisclosure } from "../components/ui/HelpDisclosure";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { resolveQueriesStatus } from "../components/ui/QueryBoundary";
import { useDeepLinkTab } from "../hooks/useDeepLinkTab";
import {
  CatalogBrowser,
  CONTENT_VERTICALS,
  SOURCE_CATEGORIES,
  SOURCE_TIERS,
  SOURCES_TABS,
  SourceEditRow,
  type AddMode,
  type SourceForm,
  type SourcesTab,
} from "../features/sources";

export default function SourcesPage() {
  const [deletingSourceId, setDeletingSourceId] = useState<string | null>(null);
  const [editingSourceId, setEditingSourceId] = useState<string | null>(null);
  const [savingSourceId, setSavingSourceId] = useState<string | null>(null);
  const [importingCatalogId, setImportingCatalogId] = useState<string | null>(null);
  const [addMode, setAddMode] = useState<AddMode>("catalog");
  const [sourcesTab, setSourcesTab] = useDeepLinkTab<SourcesTab>("tab", SOURCES_TABS, "configured");

  const form = useForm<SourceForm>({ defaultValues: { source_type: "rss", category: "technology", source_tier: "signal", content_vertical: "general" } });
  const { tenantId, enabled } = useTenantScope();
  const tenantSettings = useQuery({
    queryKey: queryKeys.tenantSettings(tenantId ?? "none"),
    queryFn: getTenantSettings,
    enabled,
  });
  const sources = useQuery({
    queryKey: queryKeys.sources(tenantId ?? "none"),
    queryFn: getSources,
    enabled,
  });
  const health = useQuery({
    queryKey: queryKeys.sourceHealth(tenantId ?? "none"),
    queryFn: getSourceHealth,
    enabled,
  });
  const rawArticles = useQuery({
    queryKey: queryKeys.sourceArticles(tenantId ?? "none"),
    queryFn: getRawArticles,
    enabled,
  });

  const defaultPollingInterval = Number(
    tenantSettings.data?.settings["ingestion.default_polling_interval_minutes"] ?? 30
  );

  const existingUrls = new Set((sources.data ?? []).map((s) => s.url));

  const createMutation = useMutation({
    mutationFn: createSource,
    onSuccess: async () => {
      if (!tenantId) return;
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.sources(tenantId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceHealth(tenantId) }),
      ]);
    },
  });
  const importMutation = useMutation({
    mutationFn: (catalogId: string) => importCatalogSource(catalogId),
    onSuccess: async () => {
      if (!tenantId) return;
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.sources(tenantId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceHealth(tenantId) }),
      ]);
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      updateSource(id, payload),
    onSuccess: async () => {
      if (!tenantId) return;
      await queryClient.invalidateQueries({ queryKey: queryKeys.sources(tenantId) });
    },
  });
  const ingestMutation = useMutation({
    mutationFn: triggerIngestion,
    onSuccess: async () => {
      if (!tenantId) return;
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceArticles(tenantId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.stories(tenantId) }),
      ]);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteSource,
    onSuccess: async () => {
      if (!tenantId) return;
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.sources(tenantId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceHealth(tenantId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceArticles(tenantId) }),
      ]);
    },
  });
  const manualPollMutation = useMutation({
    mutationFn: triggerManualPoll,
    onSuccess: async () => {
      if (!tenantId) return;
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceArticles(tenantId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.stories(tenantId) }),
      ]);
    },
  });
  const disableMutation = useMutation({
    mutationFn: disableSource,
    onSuccess: async () => {
      if (!tenantId) return;
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.sources(tenantId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceHealth(tenantId) }),
      ]);
    },
  });

  const shellStatus = resolveQueriesStatus([sources, health]);

  if (shellStatus.status === "loading") {
    return <LoadingState label="Loading sources" />;
  }
  if (shellStatus.status === "error") {
    return (
      <ErrorState
        message="Sources could not be loaded."
        onRetry={shellStatus.retry}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Sources</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Configure ingestion inputs and review health for this workspace.
        </p>
      </div>

      <HelpDisclosure summary="Source tiers and polling">
        Authoritative (Tier 1) sources confirm stories before content generation. Polling intervals inherit workspace
        defaults unless overridden per source. Destructive deletes require confirmation and cannot be undone from the UI.
      </HelpDisclosure>

      <Tabs value={sourcesTab} onValueChange={(value) => setSourcesTab(value as SourcesTab)} className="space-y-6">
        <TabsList>
          <TabsTrigger value="configured">Configured</TabsTrigger>
          <TabsTrigger value="add">Add source</TabsTrigger>
        </TabsList>

        <TabsContent value="add" className="space-y-6" forceMount hidden={sourcesTab !== "add"}>
          <Card className="p-6">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Add source</h2>
              <div className="flex rounded-xl border border-border overflow-hidden">
                <button
                  type="button"
                  onClick={() => setAddMode("catalog")}
                  className={[
                    "px-4 py-1.5 text-sm font-medium transition-colors",
                    addMode === "catalog"
                      ? "bg-primary text-primary-foreground"
                      : "bg-card text-muted-foreground hover:bg-muted",
                  ].join(" ")}
                >
                  From Library
                </button>
                <button
                  type="button"
                  onClick={() => setAddMode("manual")}
                  className={[
                    "px-4 py-1.5 text-sm font-medium transition-colors",
                    addMode === "manual"
                      ? "bg-primary text-primary-foreground"
                      : "bg-card text-muted-foreground hover:bg-muted",
                  ].join(" ")}
                >
                  Manual
                </button>
              </div>
            </div>

            <div className="mt-5">
              {addMode === "catalog" ? (
                <CatalogBrowser
                  existingUrls={existingUrls}
                  importingId={importingCatalogId}
                  onImport={async (entry) => {
                    setImportingCatalogId(entry.id);
                    try {
                      await importMutation.mutateAsync(entry.id);
                      setSourcesTab("configured");
                    } finally {
                      setImportingCatalogId(null);
                    }
                  }}
                />
              ) : (
                <form
                  className="grid gap-3 md:grid-cols-4"
                  onSubmit={form.handleSubmit(async (values) => {
                    await createMutation.mutateAsync({
                      ...values,
                      parser_type: "auto",
                      trust_score: 0.7,
                      polling_interval_minutes: defaultPollingInterval,
                      config: {},
                      active: true,
                    });
                    form.reset({ source_type: "rss", category: "technology", source_tier: "signal", content_vertical: "general" });
                    setSourcesTab("configured");
                  })}
                >
                  <Input placeholder="Name" {...form.register("name")} />
                  <Input placeholder="URL" {...form.register("url")} />
                  <Input placeholder="Type (rss/web/api/sitemap)" {...form.register("source_type")} />
                  <select
                    aria-label="Category"
                    className="select-field"
                    {...form.register("category")}
                  >
                    {SOURCE_CATEGORIES.map((cat) => (
                      <option key={cat} value={cat}>
                        {cat[0].toUpperCase() + cat.slice(1)}
                      </option>
                    ))}
                  </select>
                  <select
                    aria-label="Source tier"
                    className="select-field"
                    {...form.register("source_tier")}
                  >
                    {SOURCE_TIERS.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                  <select
                    aria-label="Content vertical"
                    className="select-field"
                    {...form.register("content_vertical")}
                  >
                    {CONTENT_VERTICALS.map((v) => (
                      <option key={v} value={v}>{v[0].toUpperCase() + v.slice(1)}</option>
                    ))}
                  </select>
                  <Button type="submit" disabled={createMutation.isPending} className="md:col-span-2">
                    {createMutation.isPending ? "Creating…" : "Create Source"}
                  </Button>
                </form>
              )}
            </div>
            {createMutation.isError || importMutation.isError ? (
              <p className="mt-3 text-sm text-destructive" role="alert">
                Source could not be added. Check the URL and try again.
              </p>
            ) : null}
          </Card>
        </TabsContent>

        <TabsContent value="configured" className="space-y-6">
      {/* Source list */}
      {sources.data && sources.data.length > 0 ? (
        <>
          <div className="grid gap-4">
            {sources.data.map((source) => {
              const sourceHealth = health.data?.find((h) => h.source_id === source.id);
              return editingSourceId === source.id ? (
                <SourceEditRow
                  key={source.id}
                  source={source}
                  isSaving={savingSourceId === source.id && updateMutation.isPending}
                  onCancel={() => setEditingSourceId(null)}
                  onSave={async (values) => {
                    setSavingSourceId(source.id);
                    try {
                      await updateMutation.mutateAsync({ id: source.id, payload: values });
                      setEditingSourceId(null);
                    } finally {
                      setSavingSourceId(null);
                    }
                  }}
                />
              ) : (
                <Card
                  key={source.id}
                  className="flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between"
                >
                  <div className="flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="font-semibold">{source.name}</h2>
                      <Badge variant={sourceHealth?.status === "healthy" ? "success" : "warning"}>
                        {sourceHealth?.status ?? "unknown"}
                      </Badge>
                      <Badge variant="muted" className="capitalize">
                        {source.category}
                      </Badge>
                      <Badge variant={source.source_tier === "authoritative" ? "default" : "muted"} className="capitalize">
                        {source.source_tier ?? "signal"}
                      </Badge>
                      <Badge variant="muted" className="capitalize">
                        {source.content_vertical ?? "general"}
                      </Badge>
                      {source.legal_risk && (
                        <Badge variant="warning">Legal Risk</Badge>
                      )}
                      {source.tier1_confirmation_required && (
                        <Badge variant="warning">Tier1 Required</Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground">{source.url}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {source.source_type} · every {source.polling_interval_minutes} min · freshness {source.freshness_decay_hours}h · {source.success_count} ok / {source.failure_count} fail
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-3">
                    <Button variant="outline" onClick={() => ingestMutation.mutate(source.id)}>
                      Ingest Now
                    </Button>
                    <Button variant="outline" onClick={() => manualPollMutation.mutate(source.id)}>
                      Manual Poll
                    </Button>
                    <Button variant="outline" onClick={() => setEditingSourceId(source.id)}>
                      Edit
                    </Button>
                    {source.active && (
                      <Button variant="outline" onClick={() => disableMutation.mutate(source.id)}>
                        Disable
                      </Button>
                    )}
                    <Button
                      variant="destructive"
                      onClick={async () => {
                        if (!window.confirm(`Delete source "${source.name}"?`)) return;
                        setDeletingSourceId(source.id);
                        try {
                          await deleteMutation.mutateAsync(source.id);
                        } finally {
                          setDeletingSourceId(null);
                        }
                      }}
                      disabled={deleteMutation.isPending && deletingSourceId === source.id}
                    >
                      {deleteMutation.isPending && deletingSourceId === source.id ? "Deleting…" : "Delete"}
                    </Button>
                  </div>
                </Card>
              );
            })}
          </div>

          <Card className="p-5">
            <h2 className="text-lg font-semibold">Latest Raw Articles</h2>
            <div className="mt-4 space-y-3">
              {rawArticles.isError ? (
                <ErrorState
                  message="Raw articles could not be loaded."
                  onRetry={() => {
                    void rawArticles.refetch();
                  }}
                />
              ) : (rawArticles.data?.length ?? 0) === 0 ? (
                <EmptyState title="No articles yet" description="Ingest a source to populate the raw article feed." />
              ) : (
                rawArticles.data?.slice(0, 8).map((article) => (
                  <div key={article.id} className="inset-panel">
                    <a
                      href={article.canonical_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium hover:underline hover:text-primary"
                    >
                      {article.title}
                    </a>
                    <p className="mt-1 text-sm text-muted-foreground">{article.summary}</p>
                  </div>
                ))
              )}
            </div>
          </Card>
        </>
      ) : (
        <EmptyState
          title="No sources configured"
          description="Add from the library or create a manual source."
          action={
            <Button variant="outline" onClick={() => setSourcesTab("add")}>
              Add source
            </Button>
          }
        />
      )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
