import type { ChessGameSearchParams } from "../../api/chessData";
import { Button } from "../../components/ui/button";
import { FieldHelp } from "../../components/ui/HelpDisclosure";
import { Input } from "../../components/ui/input";
import { RESULT_OPTIONS } from "./constants";

export type GameFiltersProps = {
  value: ChessGameSearchParams;
  onChange: (next: ChessGameSearchParams) => void;
  onSubmit: () => void;
};

export function GameFilters({ value, onChange, onSubmit }: GameFiltersProps) {
  function set<K extends keyof ChessGameSearchParams>(key: K, next: ChessGameSearchParams[K]) {
    onChange({ ...value, [key]: next });
  }

  return (
    <form
      className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <label className="space-y-1 text-sm">
        <span className="inline-flex items-center gap-1.5 text-muted-foreground">
          Player
          <FieldHelp content="Matches white or black. Use a surname for historical research." />
        </span>
        <Input
          value={value.player ?? ""}
          onChange={(e) => set("player", e.target.value || undefined)}
          placeholder="Player"
        />
      </label>
      <label className="space-y-1 text-sm">
        <span className="inline-flex items-center gap-1.5 text-muted-foreground">
          Opening
          <FieldHelp content="Opening name or fragment (e.g. Queen's Gambit)." />
        </span>
        <Input
          value={value.opening ?? ""}
          onChange={(e) => set("opening", e.target.value || undefined)}
          placeholder="Opening"
        />
      </label>
      <label className="space-y-1 text-sm">
        <span className="text-muted-foreground">From year</span>
        <Input
          type="number"
          value={value.year_from ?? ""}
          onChange={(e) =>
            set("year_from", e.target.value ? Number(e.target.value) : undefined)
          }
          placeholder="From year"
        />
      </label>
      <label className="space-y-1 text-sm">
        <span className="text-muted-foreground">To year</span>
        <Input
          type="number"
          value={value.year_to ?? ""}
          onChange={(e) => set("year_to", e.target.value ? Number(e.target.value) : undefined)}
          placeholder="To year"
        />
      </label>
      <label className="space-y-1 text-sm">
        <span className="text-muted-foreground">Result</span>
        <select
          className="h-11 w-full rounded-md border border-border bg-background px-3"
          value={value.result ?? ""}
          onChange={(e) => set("result", e.target.value || undefined)}
        >
          <option value="">Any</option>
          {RESULT_OPTIONS.map((result) => (
            <option key={result} value={result}>
              {result}
            </option>
          ))}
        </select>
      </label>
      <label className="space-y-1 text-sm">
        <span className="inline-flex items-center gap-1.5 text-muted-foreground">
          ECO
          <FieldHelp content="Optional Encyclopedia of Chess Openings code (e.g. D59)." />
        </span>
        <Input
          value={value.eco ?? ""}
          onChange={(e) => set("eco", e.target.value || undefined)}
          placeholder="ECO"
        />
      </label>
      <label className="flex items-end gap-2 pb-2 text-sm">
        <input
          type="checkbox"
          checked={Boolean(value.famous_only)}
          onChange={(e) => set("famous_only", e.target.checked || undefined)}
        />
        <span className="inline-flex items-center gap-1.5 text-muted-foreground">
          Famous only
          <FieldHelp content="Limit to curated classics tagged in the famous-game catalog." />
        </span>
      </label>
      <div className="flex items-end">
        <Button type="submit" className="w-full">
          Search games
        </Button>
      </div>
    </form>
  );
}
