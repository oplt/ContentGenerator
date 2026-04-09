import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import {
  createSource,
  disableSource,
  deleteSource,
  getCatalog,
  getRawArticles,
  getSourceHealth,
  getSources,
  importCatalogSource,
  triggerManualPoll,
  triggerIngestion,
  updateSource,
  type CatalogEntry,
  type Source,
} from "../api/sources";
import { getTenantSettings } from "../api/settings";
import { queryClient } from "../lib/queryClient";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { LoadingState } from "../components/ui/LoadingState";
import { EmptyState } from "../components/ui/EmptyState";

type SourceForm = {
  name: string;
  url: string;
  source_type: string;
  category: string;
  source_tier: string;
  content_vertical: string;
};

type EditForm = {
  name: string;
  category: string;
  source_tier: string;
  content_vertical: string;
  freshness_decay_hours: number;
  legal_risk: boolean;
  tier1_confirmation_required: boolean;
  polling_interval_minutes: number;
  trust_score: number;
};

type AddMode = "catalog" | "manual";

const SOURCE_CATEGORIES = [
  "technology",
  "politics",
  "conflicts",
  "general",
  "business",
  "world",
  "science",
  "health",
  "gaming",
  "ai",
  "crypto",
] as const;

const SOURCE_TIERS = [
  { value: "authoritative", label: "Authoritative (Tier 1)" },
  { value: "signal", label: "Signal (Tier 2)" },
  { value: "amplification", label: "Amplification (Tier 3)" },
] as const;

const CONTENT_VERTICALS = [
  "general",
  "politics",
  "conflicts",
  "economy",
  "gaming",
  "fashion",
  "beauty",
  "tech",
  "entertainment",
] as const;

const CATALOG_TABS = [
  { key: undefined, label: "All" },
  { key: "ai", label: "AI" },
  { key: "technology", label: "Tech" },
  { key: "politics", label: "Politics" },
  { key: "gaming", label: "Gaming" },
  { key: "science", label: "Science" },
  { key: "business", label: "Business" },
  { key: "health", label: "Health" },
  { key: "crypto", label: "Crypto" },
] as const;

function SourceEditRow({
  source,
  onSave,
  onCancel,
  isSaving,
}: {
  source: Source;
  onSave: (values: EditForm) => Promise<void>;
  onCancel: () => void;
  isSaving: boolean;
}) {
  const form = useForm<EditForm>({
    defaultValues: {
      name: source.name,
      category: source.category,
      source_tier: source.source_tier ?? "signal",
      content_vertical: source.content_vertical ?? "general",
      freshness_decay_hours: source.freshness_decay_hours ?? 24,
      legal_risk: source.legal_risk ?? false,
      tier1_confirmation_required: source.tier1_confirmation_required ?? false,
      polling_interval_minutes: source.polling_interval_minutes,
      trust_score: source.trust_score,
    },
  });

  return (
    <Card className="p-5">
      <p className="mb-3 text-xs uppercase tracking-[0.16em] text-muted-foreground">
        Editing — {source.url}
      </p>
      <form
        className="grid gap-3 sm:grid-cols-4"
        onSubmit={form.handleSubmit(async (values) => {
          await onSave(values);
        })}
      >
        <label className="space-y-1 text-sm">
          <span className="font-medium">Name</span>
          <Input {...form.register("name")} />
        </label>
        <label className="space-y-1 text-sm">
          <span className="font-medium">Category</span>
          <Input {...form.register("category")} />
        </label>
        <label className="space-y-1 text-sm">
          <span className="font-medium">Source Tier</span>
          <select
            aria-label="Source tier"
            className="select-field"
            {...form.register("source_tier")}
          >
            {SOURCE_TIERS.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="font-medium">Content Vertical</span>
          <select
            aria-label="Content vertical"
            className="select-field"
            {...form.register("content_vertical")}
          >
            {CONTENT_VERTICALS.map((v) => (
              <option key={v} value={v}>{v[0].toUpperCase() + v.slice(1)}</option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="font-medium">Freshness decay (h)</span>
          <Input
            type="number"
            min={0}
            {...form.register("freshness_decay_hours", { valueAsNumber: true })}
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="font-medium">Poll interval (min)</span>
          <Input
            type="number"
            min={5}
            max={1440}
            {...form.register("polling_interval_minutes", { valueAsNumber: true })}
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="font-medium">Trust score (0–1)</span>
          <Input
            type="number"
            step="0.1"
            min={0}
            max={1}
            {...form.register("trust_score", { valueAsNumber: true })}
          />
        </label>
        <div className="flex flex-col gap-2 sm:col-span-1 justify-center pt-4">
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" {...form.register("legal_risk")} className="h-4 w-4 rounded" />
            <span>Legal risk</span>
          </label>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" {...form.register("tier1_confirmation_required")} className="h-4 w-4 rounded" />
            <span>Require Tier 1 confirmation</span>
          </label>
        </div>
        <div className="flex gap-2 sm:col-span-4">
          <Button type="submit" disabled={isSaving}>
            {isSaving ? "Saving…" : "Save"}
          </Button>
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}

function CatalogBrowser({
  existingUrls,
  onImport,
  importingId,
}: {
  existingUrls: Set<string>;
  onImport: (entry: CatalogEntry) => void;
  importingId: string | null;
}) {
  const [activeCategory, setActiveCategory] = useState<string | undefined>(undefined);
  const catalog = useQuery({
    queryKey: ["sources", "catalog", activeCategory],
    queryFn: () => getCatalog(activeCategory),
  });

  return (
    <div className="space-y-4">
      {/* Category tabs */}
      <div className="flex flex-wrap gap-2">
        {CATALOG_TABS.map((tab) => (
          <button
            key={tab.label}
            type="button"
            onClick={() => setActiveCategory(tab.key)}
            className={[
              "rounded-full px-3 py-1 text-sm font-medium transition-colors",
              activeCategory === tab.key
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-muted/70",
            ].join(" ")}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {catalog.isLoading && <LoadingState label="Loading catalog" />}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {catalog.data?.map((entry) => {
          const alreadyAdded = existingUrls.has(entry.url);
          return (
            <div
              key={entry.id}
              className="flex flex-col gap-2 rounded-2xl border border-border bg-card p-4"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-medium text-sm">{entry.name}</p>
                  <Badge variant="muted" className="mt-1 text-xs capitalize">
                    {entry.category}
                  </Badge>
                </div>
                <Button
                  size="sm"
                  variant={alreadyAdded ? "outline" : "default"}
                  disabled={alreadyAdded || importingId === entry.id}
                  onClick={() => onImport(entry)}
                  className="shrink-0"
                >
                  {alreadyAdded ? "Added" : importingId === entry.id ? "Adding…" : "+ Add"}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground line-clamp-2">{entry.description}</p>
              <p className="truncate text-xs text-muted-foreground/60">{entry.url}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function SourcesPage() {
  const [deletingSourceId, setDeletingSourceId] = useState<string | null>(null);
  const [editingSourceId, setEditingSourceId] = useState<string | null>(null);
  const [savingSourceId, setSavingSourceId] = useState<string | null>(null);
  const [importingCatalogId, setImportingCatalogId] = useState<string | null>(null);
  const [addMode, setAddMode] = useState<AddMode>("catalog");

  const form = useForm<SourceForm>({ defaultValues: { source_type: "rss", category: "technology", source_tier: "signal", content_vertical: "general" } });
  const tenantSettings = useQuery({ queryKey: ["tenant-settings"], queryFn: getTenantSettings });
  const sources = useQuery({ queryKey: ["sources"], queryFn: getSources });
  const health = useQuery({ queryKey: ["sources", "health"], queryFn: getSourceHealth });
  const rawArticles = useQuery({ queryKey: ["sources", "articles"], queryFn: getRawArticles });

  const defaultPollingInterval = Number(
    tenantSettings.data?.settings["ingestion.default_polling_interval_minutes"] ?? 30
  );

  const existingUrls = new Set((sources.data ?? []).map((s) => s.url));

  const createMutation = useMutation({
    mutationFn: createSource,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["sources"] }),
        queryClient.invalidateQueries({ queryKey: ["sources", "health"] }),
      ]);
    },
  });
  const importMutation = useMutation({
    mutationFn: (catalogId: string) => importCatalogSource(catalogId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["sources"] }),
        queryClient.invalidateQueries({ queryKey: ["sources", "health"] }),
      ]);
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      updateSource(id, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
  });
  const ingestMutation = useMutation({
    mutationFn: triggerIngestion,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["sources", "articles"] }),
        queryClient.invalidateQueries({ queryKey: ["stories"] }),
      ]);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteSource,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["sources"] }),
        queryClient.invalidateQueries({ queryKey: ["sources", "health"] }),
        queryClient.invalidateQueries({ queryKey: ["sources", "articles"] }),
      ]);
    },
  });
  const manualPollMutation = useMutation({
    mutationFn: triggerManualPoll,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["sources", "articles"] }),
        queryClient.invalidateQueries({ queryKey: ["stories"] }),
      ]);
    },
  });
  const disableMutation = useMutation({
    mutationFn: disableSource,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["sources"] }),
        queryClient.invalidateQueries({ queryKey: ["sources", "health"] }),
      ]);
    },
  });

  if (sources.isLoading || health.isLoading) {
    return <LoadingState label="Loading sources" />;
  }

  return (
    <div className="space-y-6">
      {/* Add source panel */}
      <Card className="p-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Sources</h1>
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
      </Card>

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
              {rawArticles.data?.slice(0, 8).map((article) => (
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
              ))}
            </div>
          </Card>
        </>
      ) : (
        <EmptyState title="No sources configured" description="Add from the library above or create a manual source." />
      )}
    </div>
  );
}
