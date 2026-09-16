import { expect, test } from "@playwright/test";
import { mockSignedOutDashboard, signInAsDemo } from "./fixtures/auth";
import { installWorkflowApiMocks } from "./fixtures/workflows";

test("workflows list → automations → run monitor", async ({ page }) => {
  await mockSignedOutDashboard(page);
  await installWorkflowApiMocks(page);
  await signInAsDemo(page);

  await page.goto("/dashboard/workflows");
  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();
  await expect(page.getByText("E2E Chess Caption")).toBeVisible();

  await page.goto("/dashboard/automations");
  await expect(page.getByRole("heading", { name: "Automations" })).toBeVisible();
  await expect(page.getByText("Chess daily")).toBeVisible();

  await page.goto("/dashboard/runs");
  await expect(page.getByRole("heading", { name: "Workflow runs" })).toBeVisible();
  await expect(page.getByText("succeeded")).toBeVisible();
  await page.getByRole("link", { name: "Open" }).click();
  await expect(page.getByText(/generate · generate_text/)).toBeVisible();
  await expect(page.getByText(/publish · publish/)).toBeVisible();
});
