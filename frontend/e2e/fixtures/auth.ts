import { expect, type Page } from "@playwright/test";
import { createMockApiContext, installDashboardApiMocks, type MockApiContext } from "./mockApi";

export async function mockSignedOutDashboard(page: Page): Promise<MockApiContext> {
  const ctx = createMockApiContext();
  await installDashboardApiMocks(page, ctx);
  return ctx;
}

export async function signInAsDemo(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByPlaceholder("Email").fill("demo@example.com");
  await page.getByPlaceholder("Password").fill("password1234");
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page).toHaveURL(/dashboard$/);
}
