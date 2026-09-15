import type { SocialAccountUpsertPayload } from "../../api/publishing";
import type { SocialAccount } from "../../api/publishing";
import { SocialPlatformSettingsCard } from "../../components/dashboard/SocialPlatformSettingsCard";
import { Card } from "../../components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../components/ui/tabs";
import { SOCIAL_PLATFORM_DEFINITIONS } from "./constants";

type SocialConnectionsPanelProps = {
  accounts: SocialAccount[] | undefined;
  defaultPlatform: string;
  savingPlatform: string | null;
  isSaving: boolean;
  onSave: (platform: string, payload: SocialAccountUpsertPayload) => Promise<void>;
};

export function SocialConnectionsPanel({
  accounts,
  defaultPlatform,
  savingPlatform,
  isSaving,
  onSave,
}: SocialConnectionsPanelProps) {
  return (
    <>
      <Card className="p-6">
        <h2 className="text-xl font-semibold">Social Media Connections</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Connect each destination account here. Provider-specific configuration variables are grouped under the platform that uses them.
        </p>
      </Card>

      <Tabs defaultValue={defaultPlatform} className="space-y-6">
        <TabsList className="grid w-full grid-cols-2 gap-2 md:grid-cols-5">
          {SOCIAL_PLATFORM_DEFINITIONS.map((definition) => (
            <TabsTrigger key={definition.platform} value={definition.platform}>
              {definition.label}
            </TabsTrigger>
          ))}
        </TabsList>

        {SOCIAL_PLATFORM_DEFINITIONS.map((definition) => {
          const account = accounts?.find((item) => item.platform === definition.platform);

          return (
            <TabsContent key={definition.platform} value={definition.platform}>
              <SocialPlatformSettingsCard
                platform={definition.platform}
                label={definition.label}
                description={definition.description}
                account={account}
                configFields={definition.configFields}
                hiddenFields={definition.hiddenFields}
                accessTokenConfig={definition.accessTokenConfig}
                isSaving={savingPlatform === definition.platform && isSaving}
                onSave={async (payload: SocialAccountUpsertPayload) => {
                  await onSave(definition.platform, payload);
                }}
              />
            </TabsContent>
          );
        })}
      </Tabs>
    </>
  );
}
