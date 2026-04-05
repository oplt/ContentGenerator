import type { ContentAsset } from "../../api/content";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs";

export function ContentVariantTabs({ assets }: { assets: ContentAsset[] }) {
  const textAssets = assets.filter((asset) => asset.asset_type === "text_variant");
  const grouped = textAssets.reduce<Record<string, ContentAsset[]>>((acc, asset) => {
    const key = asset.platform ?? "general";
    acc[key] = acc[key] ? [...acc[key], asset] : [asset];
    return acc;
  }, {});
  const platforms = Object.keys(grouped);
  if (platforms.length === 0) {
    return null;
  }
  return (
    <Tabs defaultValue={platforms[0]}>
      <TabsList>
        {platforms.map((platform) => (
          <TabsTrigger key={platform} value={platform}>
            {platform}
          </TabsTrigger>
        ))}
      </TabsList>
      {platforms.map((platform) => (
        <TabsContent key={platform} value={platform} className="mt-4 space-y-3">
          {grouped[platform].map((asset) => (
            <div key={asset.id} className="rounded-2xl border border-border bg-muted/40 p-4">
              <div className="mb-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">
                Variant {asset.variant_label}
              </div>
              <div className="text-sm leading-6">{asset.text_content}</div>
            </div>
          ))}
        </TabsContent>
      ))}
    </Tabs>
  );
}
