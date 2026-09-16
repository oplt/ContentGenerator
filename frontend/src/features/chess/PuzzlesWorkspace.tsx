import { useState } from "react";
import type { ChessPuzzle } from "../../api/chessData";
import { Card } from "../../components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../components/ui/tabs";
import { CHESS_PUZZLES_TABS, type ChessPuzzlesTab } from "./constants";
import { DailyPuzzlePanel } from "./DailyPuzzlePanel";
import { PuzzleBrowserPanel } from "./PuzzleBrowserPanel";
import { PuzzleViewer } from "./PuzzleViewer";

export function PuzzlesWorkspace() {
  const [tab, setTab] = useState<ChessPuzzlesTab>("browse");
  const [selectedPuzzle, setSelectedPuzzle] = useState<ChessPuzzle | null>(null);

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(280px,420px)]">
      <div className="space-y-4">
        <Tabs value={tab} onValueChange={(value) => setTab(value as ChessPuzzlesTab)}>
          <TabsList>
            {CHESS_PUZZLES_TABS.map((item) => (
              <TabsTrigger key={item} value={item} className="capitalize">
                {item}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value="browse" className="mt-4">
            <PuzzleBrowserPanel
              selectedId={selectedPuzzle?.id}
              onSelect={setSelectedPuzzle}
            />
          </TabsContent>
          <TabsContent value="daily" className="mt-4">
            <DailyPuzzlePanel selectedId={selectedPuzzle?.id} onSelect={setSelectedPuzzle} />
          </TabsContent>
        </Tabs>
      </div>

      <Card className="space-y-4 p-4 sm:p-5">
        <PuzzleViewer puzzle={selectedPuzzle} />
      </Card>
    </div>
  );
}
