import { Film, Upload } from "lucide-react";
import { Button } from "../../components/ui/button";

export type CreateVideoActionProps = {
  onCreateVideo?: () => void;
  onUseInCreator?: () => void;
  creating?: boolean;
  disabled?: boolean;
};

/** Bridge actions: enqueue from catalog or hand off PGN to Create tab. */
export function CreateVideoAction({
  onCreateVideo,
  onUseInCreator,
  creating = false,
  disabled = false,
}: CreateVideoActionProps) {
  if (!onCreateVideo && !onUseInCreator) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {onUseInCreator ? (
        <Button type="button" variant="secondary" disabled={disabled} onClick={onUseInCreator}>
          <Upload className="size-4" />
          Use in Create
        </Button>
      ) : null}
      {onCreateVideo ? (
        <Button type="button" disabled={disabled || creating} onClick={onCreateVideo}>
          <Film className="size-4" />
          {creating ? "Starting…" : "Create video"}
        </Button>
      ) : null}
    </div>
  );
}
