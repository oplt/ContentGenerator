import { expect, type Page } from "@playwright/test";

export async function createSourceAndIngest(page: Page): Promise<void> {
  await page.goto("/dashboard/sources");
  await page.getByPlaceholder("Name").fill("TechCrunch");
  await page.getByPlaceholder("URL").fill("https://techcrunch.com/feed/");
  await page.getByRole("button", { name: "Create Source" }).click();
  await page.getByRole("button", { name: "Ingest Now" }).click();
}

export async function planFromStory(page: Page): Promise<void> {
  await page.goto("/dashboard/stories");
  await expect(page.getByText("AI editor launches for social teams")).toBeVisible();
  await page.getByText("AI editor launches for social teams").click();
  await page.getByRole("button", { name: "Create Content Plan" }).click();
}

export async function generateAndReviseContent(page: Page): Promise<void> {
  await page.goto("/dashboard/content");
  await page.getByRole("button", { name: "Generate Content" }).click();
  await page.getByRole("link", { name: "Open" }).click();
  await page.getByPlaceholder("Give revision feedback").fill("Make it tighter");
  await page.getByRole("button", { name: "Regenerate" }).click();
}

export async function approveViaWhatsAppWebhook(page: Page): Promise<void> {
  await page.goto("/dashboard/approvals");
  await page.getByRole("button", { name: /Send text for approval/i }).click();
  await page.evaluate(async () => {
    await fetch("http://localhost:8000/api/v1/approvals/whatsapp/webhook", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approval_request_id: "approval-1", text: "APPROVE approval-1" }),
    });
  });
  await page.reload();
  await expect(page.getByText("approved")).toBeVisible();
}

export async function assertPublishedAndAnalytics(page: Page): Promise<void> {
  await page.goto("/dashboard/publishing");
  await expect(page.getByText("https://example.invalid/x/post-1").first()).toBeVisible();
  await page.goto("/dashboard/analytics");
  await expect(page.getByRole("heading", { name: "Analytics" })).toBeVisible();
}
