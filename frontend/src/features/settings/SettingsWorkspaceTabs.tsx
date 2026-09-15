import { lazy, Suspense } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../components/ui/tabs";
import { LoadingState } from "../../components/ui/LoadingState";
import type { SettingsTab } from "./constants";
import type { SettingsWorkspaceTabsProps } from "./types";

const GeneralTab = lazy(() =>
  import("./GeneralTab").then((m) => ({ default: m.GeneralTab })),
);
const PublishingTab = lazy(() =>
  import("./PublishingTab").then((m) => ({ default: m.PublishingTab })),
);
const IntegrationsTab = lazy(() =>
  import("./IntegrationsTab").then((m) => ({ default: m.IntegrationsTab })),
);
const SocialTab = lazy(() =>
  import("./SocialTab").then((m) => ({ default: m.SocialTab })),
);

function TabFallback() {
  return <LoadingState label="Loading settings section" />;
}

export function SettingsWorkspaceTabs({
  settingsTab,
  setSettingsTab,
  workspaceForm,
  workflowForm,
  whatsappForm,
  telegramForm,
  tenantMutation,
  whatsappMutation,
  telegramMutation,
  socialMutation,
  registerWebhookMutation,
  sendTelegramDigestTestMutation,
  tenantSettings,
  whatsappSettings,
  telegramSettings,
  socialAccounts,
  whatsappProvider,
  activeMembership,
  defaultSocialPlatform,
  savingPlatform,
  setSavingPlatform,
}: SettingsWorkspaceTabsProps) {
  return (
    <Tabs
      value={settingsTab}
      onValueChange={(value) => setSettingsTab(value as SettingsTab)}
      className="space-y-6"
    >
      <TabsList className="grid w-full grid-cols-2 gap-2 md:grid-cols-4">
        <TabsTrigger value="general">General</TabsTrigger>
        <TabsTrigger value="publishing">Publishing</TabsTrigger>
        <TabsTrigger value="integrations">Integrations</TabsTrigger>
        <TabsTrigger value="social">Social</TabsTrigger>
      </TabsList>

      <TabsContent value="general" className="space-y-6">
        {settingsTab === "general" && tenantSettings.data ? (
          <Suspense fallback={<TabFallback />}>
            <GeneralTab
              workspaceForm={workspaceForm}
              tenantMutation={tenantMutation}
              tenantSettings={tenantSettings.data}
              activeMembership={activeMembership}
            />
          </Suspense>
        ) : null}
      </TabsContent>

      <TabsContent value="publishing" className="space-y-6">
        {settingsTab === "publishing" ? (
          <Suspense fallback={<TabFallback />}>
            <PublishingTab workflowForm={workflowForm} tenantMutation={tenantMutation} />
          </Suspense>
        ) : null}
      </TabsContent>

      <TabsContent value="integrations" className="space-y-6">
        {settingsTab === "integrations" ? (
          whatsappSettings.data ? (
            <Suspense fallback={<TabFallback />}>
              <IntegrationsTab
                whatsappForm={whatsappForm}
                telegramForm={telegramForm}
                whatsappMutation={whatsappMutation}
                telegramMutation={telegramMutation}
                registerWebhookMutation={registerWebhookMutation}
                sendTelegramDigestTestMutation={sendTelegramDigestTestMutation}
                whatsappSettings={whatsappSettings.data}
                telegramSettings={telegramSettings.data}
                whatsappProvider={whatsappProvider}
              />
            </Suspense>
          ) : (
            <TabFallback />
          )
        ) : null}
      </TabsContent>

      <TabsContent value="social" className="space-y-6">
        {settingsTab === "social" ? (
          socialAccounts.isPending && socialAccounts.data === undefined ? (
            <TabFallback />
          ) : (
            <Suspense fallback={<TabFallback />}>
              <SocialTab
                socialAccounts={socialAccounts.data}
                socialMutation={socialMutation}
                defaultSocialPlatform={defaultSocialPlatform}
                savingPlatform={savingPlatform}
                setSavingPlatform={setSavingPlatform}
              />
            </Suspense>
          )
        ) : null}
      </TabsContent>
    </Tabs>
  );
}
