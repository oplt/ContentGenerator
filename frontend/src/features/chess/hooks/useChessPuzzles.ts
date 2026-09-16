import { useQuery } from "@tanstack/react-query";
import {
  getDailyChessPuzzle,
  searchChessPuzzles,
  type ChessPuzzleSearchParams,
} from "../../../api/chessData";
import { useTenantScope } from "../../../hooks/useTenantScope";
import { queryKeys } from "../../../lib/queryKeys";

function filterKey(params: ChessPuzzleSearchParams): string {
  return JSON.stringify(params);
}

export function useChessPuzzles(params: ChessPuzzleSearchParams, enabled = true) {
  const { tenantId } = useTenantScope();
  return useQuery({
    queryKey: queryKeys.chessPuzzles(tenantId ?? "none", filterKey(params)),
    queryFn: () => searchChessPuzzles(params),
    enabled: Boolean(tenantId) && enabled,
  });
}

export function useDailyChessPuzzle(enabled = true) {
  const { tenantId } = useTenantScope();
  return useQuery({
    queryKey: queryKeys.chessDailyPuzzle(tenantId ?? "none"),
    queryFn: () => getDailyChessPuzzle(),
    enabled: Boolean(tenantId) && enabled,
    staleTime: 5 * 60_000,
  });
}
