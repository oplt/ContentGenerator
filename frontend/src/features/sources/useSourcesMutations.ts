import { useMutation } from "@tanstack/react-query";
import {
  createSource,
  deleteSource,
  disableSource,
  importCatalogSource,
  triggerIngestion,
  triggerManualPoll,
  updateSource,
} from "../../api/sources";
import { queryClient } from "../../lib/queryClient";
import { queryKeys } from "../../lib/queryKeys";

type UseSourcesMutationsArgs = {
  tenantId: string | null;
  onIngestRunId?: (fetchRunId: string) => void;
};

export function useSourcesMutations({ tenantId, onIngestRunId }: UseSourcesMutationsArgs) {
  const invalidateSourceLists = async () => {
    if (!tenantId) return;
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.sources(tenantId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.sourceHealth(tenantId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.sourceArticles(tenantId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.sourceFetchRuns(tenantId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.stories(tenantId) }),
    ]);
  };

  const createMutation = useMutation({
    mutationFn: createSource,
    onSuccess: async () => {
      await invalidateSourceLists();
    },
  });
  const importMutation = useMutation({
    mutationFn: (catalogId: string) => importCatalogSource(catalogId),
    onSuccess: async () => {
      await invalidateSourceLists();
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
    onSuccess: async (result) => {
      if (result.fetch_run_id) {
        onIngestRunId?.(result.fetch_run_id);
      }
      await invalidateSourceLists();
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteSource,
    onSuccess: async () => {
      await invalidateSourceLists();
    },
  });
  const manualPollMutation = useMutation({
    mutationFn: triggerManualPoll,
    onSuccess: async (result) => {
      if (result.fetch_run_id) {
        onIngestRunId?.(result.fetch_run_id);
      }
      await invalidateSourceLists();
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

  return {
    createMutation,
    importMutation,
    updateMutation,
    ingestMutation,
    deleteMutation,
    manualPollMutation,
    disableMutation,
  };
}
