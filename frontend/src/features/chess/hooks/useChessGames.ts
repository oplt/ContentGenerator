import { useQuery } from "@tanstack/react-query";
import {
  getChessGame,
  getChessGameMoves,
  listFamousChessGames,
  searchChessGames,
  type ChessGameSearchParams,
} from "../../../api/chessData";
import { useTenantScope } from "../../../hooks/useTenantScope";
import { queryKeys } from "../../../lib/queryKeys";

function filterKey(params: ChessGameSearchParams): string {
  return JSON.stringify(params);
}

export function useChessGames(params: ChessGameSearchParams, enabled = true) {
  const { tenantId } = useTenantScope();
  return useQuery({
    queryKey: queryKeys.chessGames(tenantId ?? "none", filterKey(params)),
    queryFn: () => searchChessGames(params),
    enabled: Boolean(tenantId) && enabled,
  });
}

export function useFamousChessGames(limit = 20) {
  const { tenantId } = useTenantScope();
  return useQuery({
    queryKey: queryKeys.chessFamousGames(tenantId ?? "none"),
    queryFn: () => listFamousChessGames({ limit }),
    enabled: Boolean(tenantId),
  });
}

export function useChessGame(gameId: string | null) {
  const { tenantId } = useTenantScope();
  return useQuery({
    queryKey: queryKeys.chessGame(tenantId ?? "none", gameId ?? ""),
    queryFn: () => getChessGame(gameId!),
    enabled: Boolean(tenantId && gameId),
  });
}

export function useChessGameMoves(gameId: string | null) {
  const { tenantId } = useTenantScope();
  return useQuery({
    queryKey: queryKeys.chessGameMoves(tenantId ?? "none", gameId ?? ""),
    queryFn: () => getChessGameMoves(gameId!),
    enabled: Boolean(tenantId && gameId),
  });
}
