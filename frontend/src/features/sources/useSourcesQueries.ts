import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getRawArticles, getSourceHealth, getSources } from "../../api/sources";
import { getTenantSettings } from "../../api/settings";
import { useTenantScope } from "../../hooks/useTenantScope";
import { queryKeyFactories, queryKeys } from "../../lib/queryKeys";
import { queryPolicy } from "../../lib/queryPolicy";
import type { AddMode, SourcesTab } from "./components";

type UseSourcesQueriesArgs = {
  sourcesTab: SourcesTab;
  addMode: AddMode;
};

export function useSourcesQueries({ sourcesTab, addMode }: UseSourcesQueriesArgs) {
  const { tenantId, enabled } = useTenantScope();
  const onConfigured = enabled && sourcesTab === "configured";
  const onAdd = enabled && sourcesTab === "add";

  const tenantSettings = useQuery({
    queryKey: queryKeys.tenantSettings(tenantId ?? "none"),
    queryFn: getTenantSettings,
    enabled: onAdd && addMode === "manual",
    ...queryPolicy.moderate,
  });
  const sources = useQuery({
    queryKey: queryKeys.sources(tenantId ?? "none"),
    queryFn: getSources,
    enabled,
    ...queryPolicy.moderate,
  });
  const health = useQuery({
    queryKey: queryKeys.sourceHealth(tenantId ?? "none"),
    queryFn: getSourceHealth,
    enabled: onConfigured,
    ...queryPolicy.health,
  });
  const rawArticles = useQuery({
    queryKey: queryKeyFactories.sources.articlePage(tenantId ?? "none", 8),
    queryFn: () => getRawArticles({ limit: 8 }),
    enabled: onConfigured,
    ...queryPolicy.moderate,
  });

  const defaultPollingInterval = Number(
    tenantSettings.data?.settings["ingestion.default_polling_interval_minutes"] ?? 30,
  );

  const existingUrls = useMemo(
    () => new Set((sources.data ?? []).map((source) => source.url)),
    [sources.data],
  );

  const healthBySourceId = useMemo(() => {
    const map = new Map<string, NonNullable<typeof health.data>[number]>();
    for (const item of health.data ?? []) {
      map.set(item.source_id, item);
    }
    return map;
  }, [health.data]);

  const sourceNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const source of sources.data ?? []) {
      map.set(source.id, source.name);
    }
    return map;
  }, [sources.data]);

  return {
    tenantId,
    enabled,
    tenantSettings,
    sources,
    health,
    rawArticles,
    defaultPollingInterval,
    existingUrls,
    healthBySourceId,
    sourceNameById,
  };
}
