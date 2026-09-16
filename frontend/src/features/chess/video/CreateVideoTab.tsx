import { Play } from "lucide-react";
import type {
  ChessBoardTheme,
  ChessInputFormat,
  ChessRenderPreset,
  ChessVideoJob,
  ChessVideoValidation,
} from "../../../api/chessVideos";
import { Button } from "../../../components/ui/button";
import { Card } from "../../../components/ui/card";
import { ErrorState } from "../../../components/ui/ErrorState";
import { Input } from "../../../components/ui/input";
import { PRESETS, GenerationStatus } from "./status";
import { BoardThemeSelector, GameSourceInput, GameSummary, SectionHeader } from "./createParts";

export function CreateVideoTab({
  inputMode,
  setInputMode,
  sourceText,
  setSourceText,
  uploadedFileName,
  uploadInputKey,
  onUploadFile,
  onRemoveUploadedFile,
  inputFormat,
  setInputFormat,
  renderPreset,
  setRenderPreset,
  orientation,
  setOrientation,
  secondsPerMove,
  setSecondsPerMove,
  boardTheme,
  setBoardTheme,
  includeCoordinates,
  setIncludeCoordinates,
  includeMoveText,
  setIncludeMoveText,
  title,
  setTitle,
  validation,
  validatePending,
  validateError,
  createPending,
  createError,
  canGenerate,
  activeJob,
  retrying,
  onValidate,
  onGenerate,
  onRetry,
  onViewVideo,
}: {
  inputMode: "paste" | "upload";
  setInputMode: (value: "paste" | "upload") => void;
  sourceText: string;
  setSourceText: (value: string) => void;
  uploadedFileName: string | null;
  uploadInputKey: number;
  onUploadFile: (file: File | null) => void;
  onRemoveUploadedFile: () => void;
  inputFormat: ChessInputFormat;
  setInputFormat: (value: ChessInputFormat) => void;
  renderPreset: ChessRenderPreset;
  setRenderPreset: (value: ChessRenderPreset) => void;
  orientation: "white" | "black";
  setOrientation: (value: "white" | "black") => void;
  secondsPerMove: number;
  setSecondsPerMove: (value: number) => void;
  boardTheme: ChessBoardTheme;
  setBoardTheme: (value: ChessBoardTheme) => void;
  includeCoordinates: boolean;
  setIncludeCoordinates: (value: boolean) => void;
  includeMoveText: boolean;
  setIncludeMoveText: (value: boolean) => void;
  title: string;
  setTitle: (value: string) => void;
  validation: ChessVideoValidation | null;
  validatePending: boolean;
  validateError: unknown;
  createPending: boolean;
  createError: unknown;
  canGenerate: boolean;
  activeJob: ChessVideoJob | undefined;
  retrying: boolean;
  onValidate: () => void;
  onGenerate: () => void;
  onRetry: () => void;
  onViewVideo: () => void;
}) {
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <Card className="space-y-6 p-4 sm:p-6">
        <section className="space-y-3">
          <SectionHeader title="Game source" description="Paste moves or upload a PGN to validate the game." />
          <GameSourceInput
            inputMode={inputMode}
            setInputMode={setInputMode}
            sourceText={sourceText}
            setSourceText={setSourceText}
            uploadedFileName={uploadedFileName}
            uploadInputKey={uploadInputKey}
            onUploadFile={onUploadFile}
            onRemoveUploadedFile={onRemoveUploadedFile}
          />
          <GameSummary validation={validation} validating={validatePending} />
          {validateError ? (
            <ErrorState
              message={
                validateError instanceof Error
                  ? validateError.message
                  : "Validation request failed. Check the moves and try again."
              }
              onRetry={onValidate}
            />
          ) : null}
        </section>

        <section className="space-y-4 border-t border-border pt-5">
          <SectionHeader title="Video settings" description="Choose the output format and playback rhythm." />
          <div className="grid gap-4 lg:grid-cols-4">
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Input format</span>
              <select
                className="h-11 w-full rounded-md border border-border bg-background px-3 py-2"
                value={inputFormat}
                onChange={(e) => setInputFormat(e.target.value as ChessInputFormat)}
              >
                <option value="auto">Auto</option>
                <option value="pgn">PGN</option>
                <option value="san">SAN</option>
                <option value="uci">UCI</option>
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Video preset</span>
              <select
                className="h-11 w-full rounded-md border border-border bg-background px-3 py-2"
                value={renderPreset}
                onChange={(e) => setRenderPreset(e.target.value as ChessRenderPreset)}
              >
                {PRESETS.map((preset) => (
                  <option key={preset.value} value={preset.value}>
                    {preset.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Board orientation</span>
              <select
                className="h-11 w-full rounded-md border border-border bg-background px-3 py-2"
                value={orientation}
                onChange={(e) => setOrientation(e.target.value as "white" | "black")}
              >
                <option value="white">White</option>
                <option value="black">Black</option>
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Seconds per move</span>
              <Input
                className="h-11"
                type="number"
                min={0.2}
                max={10}
                step={0.1}
                value={secondsPerMove}
                onChange={(e) => setSecondsPerMove(Number(e.target.value) || 1)}
              />
            </label>
          </div>
        </section>

        <section className="space-y-4 border-t border-border pt-5">
          <SectionHeader title="Board appearance" description="Pick a board style for the rendered video." />
          <BoardThemeSelector boardTheme={boardTheme} setBoardTheme={setBoardTheme} />
        </section>

        <section className="grid gap-4 border-t border-border pt-5 md:grid-cols-[1fr_1.4fr]">
          <div className="space-y-3">
            <SectionHeader title="Display options" />
            <div className="flex flex-wrap gap-4 text-sm">
              <label className="flex min-h-11 items-center gap-2">
                <input
                  type="checkbox"
                  checked={includeCoordinates}
                  onChange={(e) => setIncludeCoordinates(e.target.checked)}
                />
                Coordinates
              </label>
              <label className="flex min-h-11 items-center gap-2">
                <input
                  type="checkbox"
                  checked={includeMoveText}
                  onChange={(e) => setIncludeMoveText(e.target.checked)}
                />
                Move notation
              </label>
            </div>
          </div>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Video title</span>
            <Input
              className="h-11"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Match title"
            />
          </label>
        </section>

        <div className="flex flex-col gap-3 border-t border-border pt-5 sm:flex-row sm:items-center sm:justify-end">
          {sourceText.trim() && !validation?.valid ? (
            <p className="text-sm text-muted-foreground sm:mr-auto">
              Validate the game before generating.
            </p>
          ) : null}
          <Button
            type="button"
            variant="secondary"
            disabled={!sourceText.trim() || validatePending}
            onClick={onValidate}
          >
            {validatePending ? "Validating..." : "Validate Game"}
          </Button>
          <Button
            type="button"
            variant="primary"
            disabled={!canGenerate || createPending}
            onClick={onGenerate}
          >
            <Play className="size-4" />
            {createPending ? "Queuing..." : "Generate Video"}
          </Button>
        </div>

        {createError ? (
          <ErrorState
            message={
              createError instanceof Error
                ? createError.message
                : "Could not queue chess video job. Try again after checking the source."
            }
            onRetry={onGenerate}
          />
        ) : null}
      </Card>

      <aside className="space-y-4">
        {activeJob ? (
          <GenerationStatus
            job={activeJob}
            onViewVideo={onViewVideo}
            onRetry={onRetry}
            retrying={retrying}
          />
        ) : (
          <div className="rounded-md border border-dashed border-border bg-muted/20 p-4 text-sm text-muted-foreground">
            Generation status will appear here after you queue a video.
          </div>
        )}
      </aside>
    </div>
  );
}

