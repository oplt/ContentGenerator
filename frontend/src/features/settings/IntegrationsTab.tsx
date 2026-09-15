import type { IntegrationsTabProps } from "./types";
import { TelegramIntegrationCard } from "./TelegramIntegrationCard";
import { WhatsAppIntegrationCard } from "./WhatsAppIntegrationCard";

export function IntegrationsTab(props: IntegrationsTabProps) {
  return (
    <>
      <WhatsAppIntegrationCard
        whatsappForm={props.whatsappForm}
        whatsappMutation={props.whatsappMutation}
        whatsappSettings={props.whatsappSettings}
        whatsappProvider={props.whatsappProvider}
      />
      <TelegramIntegrationCard
        telegramForm={props.telegramForm}
        telegramMutation={props.telegramMutation}
        registerWebhookMutation={props.registerWebhookMutation}
        sendTelegramDigestTestMutation={props.sendTelegramDigestTestMutation}
        telegramSettings={props.telegramSettings}
      />
    </>
  );
}
