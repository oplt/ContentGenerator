import { SocialConnectionsPanel } from "./SocialConnectionsPanel";
import type { SocialTabProps } from "./types";

export function SocialTab({
  socialAccounts,
  socialMutation,
  defaultSocialPlatform,
  savingPlatform,
  setSavingPlatform,
}: SocialTabProps) {
  return (
    <SocialConnectionsPanel
      accounts={socialAccounts}
      defaultPlatform={defaultSocialPlatform}
      savingPlatform={savingPlatform}
      isSaving={socialMutation.isPending}
      onSave={async (platform, payload) => {
        setSavingPlatform(platform);
        try {
          await socialMutation.mutateAsync(payload);
        } finally {
          setSavingPlatform(null);
        }
      }}
    />
  );
}
