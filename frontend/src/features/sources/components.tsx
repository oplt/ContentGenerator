/* eslint-disable react-refresh/only-export-components */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { getCatalog, type CatalogEntry, type Source } from "../../api/sources";
import { useTenantScope } from "../../hooks/useTenantScope";
import { queryKeys } from "../../lib/queryKeys";
import { queryPolicy } from "../../lib/queryPolicy";
import { Input } from "../../components/ui/input";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import { Card } from "../../components/ui/card";
import { LoadingState } from "../../components/ui/LoadingState";

export type SourceForm = {
  name: string;
  url: string;
  source_type: string;
  category: string;
  source_tier: string;
  content_vertical: string;
};

export type EditForm = {
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

export const SOURCES_TABS = ["configured", "add", "activity"] as const;
export type SourcesTab = (typeof SOURCES_TABS)[number];

export type AddMode = "catalog" | "manual";

export const SOURCE_CATEGORIES = [
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

export const SOURCE_TIERS = [
  { value: "authoritative", label: "Authoritative (Tier 1)" },
  { value: "signal", label: "Signal (Tier 2)" },
  { value: "amplification", label: "Amplification (Tier 3)" },
] as const;

export const CONTENT_VERTICALS = [
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

export const CATALOG_TABS = [
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

export function SourceEditRow({
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
      <p className="mb-3 text-xs font-medium text-muted-foreground">
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

export function CatalogBrowser({
  existingUrls,
  onImport,
  importingId,
  active = true,
}: {
  existingUrls: Set<string>;
  onImport: (entry: CatalogEntry) => void;
  importingId: string | null;
  active?: boolean;
}) {
  const [activeCategory, setActiveCategory] = useState<string | undefined>(undefined);
  const { tenantId, enabled } = useTenantScope();
  const catalog = useQuery({
    queryKey: queryKeys.sourceCatalog(tenantId ?? "none", activeCategory ?? "all"),
    queryFn: () => getCatalog(activeCategory),
    enabled: enabled && active,
    ...queryPolicy.static,
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
              "rounded px-3 py-1 text-sm font-medium transition-colors",
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
