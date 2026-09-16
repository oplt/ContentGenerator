import type { ChessPuzzleSearchParams } from "../../api/chessData";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";

export type PuzzleFiltersProps = {
  value: ChessPuzzleSearchParams;
  onChange: (next: ChessPuzzleSearchParams) => void;
  onSubmit: () => void;
};

export function PuzzleFilters({ value, onChange, onSubmit }: PuzzleFiltersProps) {
  function set<K extends keyof ChessPuzzleSearchParams>(key: K, next: ChessPuzzleSearchParams[K]) {
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
        <span className="text-muted-foreground">Min rating</span>
        <Input
          type="number"
          value={value.min_rating ?? ""}
          onChange={(e) =>
            set("min_rating", e.target.value ? Number(e.target.value) : undefined)
          }
        />
      </label>
      <label className="space-y-1 text-sm">
        <span className="text-muted-foreground">Max rating</span>
        <Input
          type="number"
          value={value.max_rating ?? ""}
          onChange={(e) =>
            set("max_rating", e.target.value ? Number(e.target.value) : undefined)
          }
        />
      </label>
      <label className="space-y-1 text-sm">
        <span className="text-muted-foreground">Theme</span>
        <Input
          value={value.theme ?? ""}
          onChange={(e) => set("theme", e.target.value || undefined)}
          placeholder="mate"
        />
      </label>
      <label className="space-y-1 text-sm">
        <span className="text-muted-foreground">Opening tag</span>
        <Input
          value={value.opening ?? ""}
          onChange={(e) => set("opening", e.target.value || undefined)}
        />
      </label>
      <div className="flex items-end sm:col-span-2 lg:col-span-4">
        <Button type="submit">Search puzzles</Button>
      </div>
    </form>
  );
}
