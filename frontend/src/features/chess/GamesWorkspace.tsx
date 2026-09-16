import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  createChessVideoFromGame,
  enqueueChessGameAnalysis,
  type ChessGame,
} from "../../api/chessData";
import { Card } from "../../components/ui/card";
import { EmptyState } from "../../components/ui/EmptyState";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../components/ui/tabs";
import { useTenantScope } from "../../hooks/useTenantScope";
import { queryKeys } from "../../lib/queryKeys";
import { CHESS_GAMES_TABS, type ChessGamesTab } from "./constants";
import { FamousGamesPanel } from "./FamousGamesPanel";
import { CatalogAdminSyncPanel } from "./CatalogAdminSyncPanel";
import { GameDetails } from "./GameDetails";
import { GameDetailsDialog } from "./GameDetailsDialog";
import { GameSearchPanel } from "./GameSearchPanel";
import { ImportedGamesPanel } from "./ImportedGamesPanel";

export type GamesWorkspaceProps = {
  onUseInCreator?: (game: ChessGame) => void;
  onVideoJobCreated?: (jobId: string) => void;
};

function isCompactViewport(): boolean {
  return typeof window !== "undefined" && !window.matchMedia("(min-width: 1280px)").matches;
}

export function GamesWorkspace({ onUseInCreator, onVideoJobCreated }: GamesWorkspaceProps) {
  const [tab, setTab] = useState<ChessGamesTab>("search");
  const [selectedGame, setSelectedGame] = useState<ChessGame | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [analyzingId, setAnalyzingId] = useState<string | null>(null);
  const { tenantId } = useTenantScope();
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: (game: ChessGame) => createChessVideoFromGame(game.id, {}),
    onSuccess: async (job) => {
      if (tenantId) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.chessVideos(tenantId) });
      }
      onVideoJobCreated?.(job.id);
    },
  });

  const analyzeMutation = useMutation({
    mutationFn: (game: ChessGame) => enqueueChessGameAnalysis(game.id, {}),
    onMutate: (game) => setAnalyzingId(game.id),
    onSettled: () => setAnalyzingId(null),
    onSuccess: async (job, game) => {
      if (tenantId) {
        queryClient.setQueryData(queryKeys.chessAnalysisJob(tenantId, job.id), job);
        queryClient.setQueryData(queryKeys.chessGameAnalysis(tenantId, game.id), job);
        await queryClient.invalidateQueries({
          queryKey: queryKeys.chessGameAnalysis(tenantId, game.id),
        });
      }
    },
  });

  function selectGame(game: ChessGame, openDialog = false) {
    setSelectedGame(game);
    if (openDialog || isCompactViewport()) setDetailOpen(true);
  }

  const cardActions = {
    onView: (game: ChessGame) => selectGame(game, true),
    onAnalyze: (game: ChessGame) => {
      selectGame(game);
      analyzeMutation.mutate(game);
    },
    onCreateVideo: (game: ChessGame) => {
      selectGame(game);
      createMutation.mutate(game);
    },
    creating: createMutation.isPending,
    analyzingId,
  };

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(280px,420px)]">
      <div className="space-y-4">
        <Tabs value={tab} onValueChange={(value) => setTab(value as ChessGamesTab)}>
          <TabsList>
            {CHESS_GAMES_TABS.map((item) => (
              <TabsTrigger key={item} value={item} className="capitalize">
                {item === "search" ? "Search" : item}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value="search" className="mt-4">
            <GameSearchPanel
              selectedId={selectedGame?.id}
              onSelect={(game) => selectGame(game)}
              {...cardActions}
            />
          </TabsContent>
          <TabsContent value="famous" className="mt-4">
            <FamousGamesPanel
              selectedId={selectedGame?.id}
              onSelect={(game) => selectGame(game)}
              {...cardActions}
            />
          </TabsContent>
          <TabsContent value="imported" className="mt-4">
            <ImportedGamesPanel
              selectedId={selectedGame?.id}
              onSelect={(game) => selectGame(game)}
              {...cardActions}
            />
          </TabsContent>
        </Tabs>
        <CatalogAdminSyncPanel />
      </div>

      <Card className="hidden space-y-4 p-4 sm:p-5 xl:block">
        {selectedGame ? (
          <GameDetails
            game={selectedGame}
            creating={createMutation.isPending}
            onUseInCreator={onUseInCreator}
            onCreateVideo={(game) => createMutation.mutate(game)}
          />
        ) : (
          <EmptyState
            title="Pick a game to study"
            description="Search historical games, open a famous match, or browse imports — then analyze or create a video."
          />
        )}
        {createMutation.isError ? (
          <p className="text-sm text-destructive">
            {createMutation.error instanceof Error
              ? createMutation.error.message
              : "Could not start video job"}
          </p>
        ) : null}
        {analyzeMutation.isError ? (
          <p className="text-sm text-destructive">
            {analyzeMutation.error instanceof Error
              ? analyzeMutation.error.message
              : "Could not queue analysis"}
          </p>
        ) : null}
      </Card>

      <GameDetailsDialog
        game={selectedGame}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        creating={createMutation.isPending}
        onUseInCreator={onUseInCreator}
        onCreateVideo={(game) => createMutation.mutate(game)}
      />
    </div>
  );
}
