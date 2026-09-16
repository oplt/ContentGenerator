import { CheckCircle2, Upload, X } from "lucide-react";
import type {
  ChessBoardTheme,
  ChessInputFormat,
  ChessVideoValidation,
} from "../../../api/chessVideos";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../../components/ui/tabs";
import { Textarea } from "../../../components/ui/textarea";
import { BOARD_THEMES } from "./status";

export function SectionHeader({ title, description }: { title: string; description?: string }) {
  return (
    <div>
      <h2 className="text-sm font-medium text-foreground">{title}</h2>
      {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
    </div>
  );
}

export function GameSourceInput({
  inputMode,
  setInputMode,
  sourceText,
  setSourceText,
  uploadedFileName,
  uploadInputKey,
  onUploadFile,
  onRemoveUploadedFile,
}: {
  inputMode: "paste" | "upload";
  setInputMode: (value: "paste" | "upload") => void;
  sourceText: string;
  setSourceText: (value: string) => void;
  uploadedFileName: string | null;
  uploadInputKey: number;
  onUploadFile: (file: File | null) => void;
  onRemoveUploadedFile: () => void;
}) {
  return (
    <Tabs value={inputMode} onValueChange={(value) => setInputMode(value as "paste" | "upload")}>
      <TabsList>
        <TabsTrigger value="paste">Paste Moves</TabsTrigger>
        <TabsTrigger value="upload">Upload PGN</TabsTrigger>
      </TabsList>
      <TabsContent value="paste" className="mt-4">
        <Textarea
          className="min-h-[240px] resize-y font-mono text-sm"
          value={sourceText}
          onChange={(e) => setSourceText(e.target.value)}
          placeholder="Paste PGN, SAN, or UCI moves..."
        />
      </TabsContent>
      <TabsContent value="upload" className="mt-4 space-y-3">
        <label className="flex min-h-[160px] cursor-pointer flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border bg-muted/20 p-5 text-center text-sm transition-colors hover:bg-muted/35">
          <Upload className="size-6 text-muted-foreground" />
          <span className="font-medium text-foreground">
            {uploadedFileName ? uploadedFileName : "Drop or choose a PGN file"}
          </span>
          <span className="text-muted-foreground">PGN or plain text files are supported.</span>
          <Input
            key={uploadInputKey}
            className="sr-only"
            type="file"
            accept=".pgn,.txt,text/plain"
            onChange={(e) => onUploadFile(e.target.files?.[0] ?? null)}
          />
        </label>
        {sourceText ? (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-muted-foreground">
                {uploadedFileName ? `Loaded ${uploadedFileName}` : "Loaded PGN text"}
              </p>
              <Button type="button" variant="ghost" size="sm" onClick={onRemoveUploadedFile}>
                <X className="size-4" />
                Remove
              </Button>
            </div>
            <Textarea rows={6} value={sourceText} readOnly className="font-mono text-xs" />
          </div>
        ) : null}
      </TabsContent>
    </Tabs>
  );
}

export function GameSummary({
  validation,
  validating,
}: {
  validation: ChessVideoValidation | null;
  validating: boolean;
}) {
  if (validating) {
    return (
      <div className="rounded-md border border-border bg-muted/25 p-4 text-sm text-muted-foreground">
        Validating game...
      </div>
    );
  }

  if (!validation) return null;

  if (!validation.valid) {
    return (
      <div className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
        {validation.errors[0] || "Invalid game. Review the move text and validate again."}
      </div>
    );
  }

  return (
    <div className="rounded-md border border-border bg-muted/25 p-4">
      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
        <CheckCircle2 className="size-4 text-primary" />
        Game detected
      </div>
      <div className="mt-3 grid gap-3 text-sm sm:grid-cols-[1fr_auto_1fr] sm:items-center">
        <p className="font-medium">{validation.white_player || "White"}</p>
        <span className="text-muted-foreground">vs</span>
        <p className="font-medium">{validation.black_player || "Black"}</p>
      </div>
      <p className="mt-2 text-sm text-muted-foreground">
        {validation.event || "Untitled game"}
        {" · "}
        {validation.move_count} moves
        {" · "}
        {(validation.detected_format || validation.input_format).toUpperCase()}
        {validation.result ? ` · Result ${validation.result}` : ""}
      </p>
    </div>
  );
}

export function BoardThemeSelector({
  boardTheme,
  setBoardTheme,
}: {
  boardTheme: ChessBoardTheme;
  setBoardTheme: (value: ChessBoardTheme) => void;
}) {
  return (
    <fieldset>
      <legend className="sr-only">Board theme</legend>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        {BOARD_THEMES.map((theme) => {
          const selected = boardTheme === theme.value;
          return (
            <button
              key={theme.value}
              type="button"
              aria-pressed={selected}
              onClick={() => setBoardTheme(theme.value)}
              className={`min-h-16 rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                selected
                  ? "border-primary bg-primary/5 text-foreground ring-1 ring-primary/30"
                  : "border-border bg-background text-muted-foreground hover:border-foreground/30 hover:text-foreground"
              }`}
            >
              <span className="flex items-center gap-2">
                <span className="grid size-8 shrink-0 grid-cols-2 grid-rows-2 overflow-hidden rounded-sm border border-border">
                  <span style={{ background: theme.light }} />
                  <span style={{ background: theme.dark }} />
                  <span style={{ background: theme.dark }} />
                  <span style={{ background: theme.light }} />
                </span>
                <span className="min-w-0 flex-1 font-medium">{theme.label}</span>
                {selected ? <CheckCircle2 className="size-4 shrink-0 text-primary" /> : null}
              </span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

