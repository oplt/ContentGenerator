import { test } from "@playwright/test";
import { mockSignedOutDashboard, signInAsDemo } from "./fixtures/auth";
import {
  approveViaWhatsAppWebhook,
  assertPublishedAndAnalytics,
  createSourceAndIngest,
  generateAndReviseContent,
  planFromStory,
} from "./fixtures/contentPipeline";

test("sources → stories → content → approvals → publishing", async ({ page }) => {
  await mockSignedOutDashboard(page);
  await signInAsDemo(page);
  await createSourceAndIngest(page);
  await planFromStory(page);
  await generateAndReviseContent(page);
  await approveViaWhatsAppWebhook(page);
  await assertPublishedAndAnalytics(page);
});
