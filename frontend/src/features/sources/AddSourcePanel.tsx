import type { UseFormReturn } from "react-hook-form";
import type { UseMutationResult } from "@tanstack/react-query";
import type { CatalogEntry, Source } from "../../api/sources";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { FormField } from "../../components/ui/HelpDisclosure";
import { Input } from "../../components/ui/input";
import {
  CatalogBrowser,
  CONTENT_VERTICALS,
  SOURCE_CATEGORIES,
  SOURCE_TIERS,
  type AddMode,
  type SourceForm,
} from "./components";

type CreateSourceMutation = UseMutationResult<Source, Error, Record<string, unknown>>;
type ImportCatalogMutation = UseMutationResult<Source, Error, string>;

export type AddSourcePanelProps = {
  addMode: AddMode;
  setAddMode: (mode: AddMode) => void;
  form: UseFormReturn<SourceForm>;
  catalogActive: boolean;
  existingUrls: Set<string>;
  importingCatalogId: string | null;
  setImportingCatalogId: (id: string | null) => void;
  defaultPollingInterval: number;
  createMutation: CreateSourceMutation;
  importMutation: ImportCatalogMutation;
  onSourceAdded: () => void;
};

export function AddSourcePanel({
  addMode,
  setAddMode,
  form,
  catalogActive,
  existingUrls,
  importingCatalogId,
  setImportingCatalogId,
  defaultPollingInterval,
  createMutation,
  importMutation,
  onSourceAdded,
}: AddSourcePanelProps) {
  return (
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
            active={catalogActive}
            existingUrls={existingUrls}
            importingId={importingCatalogId}
            onImport={async (entry: CatalogEntry) => {
              setImportingCatalogId(entry.id);
              try {
                await importMutation.mutateAsync(entry.id);
                onSourceAdded();
              } finally {
                setImportingCatalogId(null);
              }
            }}
          />
        ) : (
          <form
            className="grid gap-3 md:grid-cols-2 lg:grid-cols-3"
            onSubmit={form.handleSubmit(async (values) => {
              await createMutation.mutateAsync({
                ...values,
                parser_type: "auto",
                trust_score: 0.7,
                polling_interval_minutes: defaultPollingInterval,
                config: {},
                active: true,
              });
              form.reset({
                source_type: "rss",
                category: "technology",
                source_tier: "signal",
                content_vertical: "general",
              });
              onSourceAdded();
            })}
          >
            <FormField label="Name" htmlFor="source-name">
              <Input id="source-name" placeholder="Name" {...form.register("name")} />
            </FormField>
            <FormField label="URL" htmlFor="source-url">
              <Input id="source-url" placeholder="URL" {...form.register("url")} />
            </FormField>
            <FormField label="Type" htmlFor="source-type" help="rss, web, api, or sitemap">
              <Input id="source-type" placeholder="rss" {...form.register("source_type")} />
            </FormField>
            <FormField label="Category" htmlFor="source-category">
              <select id="source-category" aria-label="Category" className="select-field" {...form.register("category")}>
                {SOURCE_CATEGORIES.map((cat) => (
                  <option key={cat} value={cat}>
                    {cat[0].toUpperCase() + cat.slice(1)}
                  </option>
                ))}
              </select>
            </FormField>
            <FormField
              label="Source tier"
              htmlFor="source-tier"
              help="Authoritative (Tier 1) sources confirm stories before generation."
            >
              <select id="source-tier" aria-label="Source tier" className="select-field" {...form.register("source_tier")}>
                {SOURCE_TIERS.map((tier) => (
                  <option key={tier.value} value={tier.value}>
                    {tier.label}
                  </option>
                ))}
              </select>
            </FormField>
            <FormField label="Content vertical" htmlFor="source-vertical">
              <select
                id="source-vertical"
                aria-label="Content vertical"
                className="select-field"
                {...form.register("content_vertical")}
              >
                {CONTENT_VERTICALS.map((vertical) => (
                  <option key={vertical} value={vertical}>
                    {vertical[0].toUpperCase() + vertical.slice(1)}
                  </option>
                ))}
              </select>
            </FormField>
            <Button type="submit" disabled={createMutation.isPending} className="md:col-span-2 lg:col-span-3">
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
  );
}
