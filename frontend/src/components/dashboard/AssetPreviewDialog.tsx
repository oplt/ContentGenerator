import { Dialog, DialogContent, DialogTrigger } from "../ui/dialog";
import { Button } from "../ui/button";
import type { ContentAsset } from "../../api/content";

export function AssetPreviewDialog({ asset }: { asset: ContentAsset }) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          Preview
        </Button>
      </DialogTrigger>
      <DialogContent>
        <h3 className="text-lg font-semibold">{asset.asset_type}</h3>
        {asset.public_url && asset.mime_type.startsWith("video") ? (
          <video controls className="mt-4 w-full rounded-2xl">
            <source src={asset.public_url} type={asset.mime_type} />
          </video>
        ) : asset.public_url && asset.mime_type.startsWith("image") ? (
          <img src={asset.public_url} alt={asset.asset_type} className="mt-4 rounded-2xl" />
        ) : (
          <pre className="mt-4 whitespace-pre-wrap rounded-2xl bg-muted p-4 text-sm">{asset.text_content}</pre>
        )}
      </DialogContent>
    </Dialog>
  );
}
