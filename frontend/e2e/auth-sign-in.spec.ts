import { test } from "@playwright/test";
import { mockSignedOutDashboard, signInAsDemo } from "./fixtures/auth";

test("signs in to the dashboard with mocked credentials", async ({ page }) => {
  await mockSignedOutDashboard(page);
  await signInAsDemo(page);
});
