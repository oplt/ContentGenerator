import { expect, test, devices } from "@playwright/test";

const sessionUser = {
  id: "user-1",
  email: "demo@example.com",
  full_name: "Demo User",
  is_verified: true,
  is_admin: true,
  mfa_enabled: true,
  default_tenant_id: "tenant-1",
  rbac_mode: "role_based_placeholder",
  memberships: [
    {
      tenant_id: "tenant-1",
      tenant_name: "Demo Tenant",
      tenant_slug: "demo",
      status: "active",
      role: {
        id: "role-1",
        name: "Owner",
        slug: "owner",
        permission_codes: [
          "settings:write",
          "audit:read",
          "sources:write",
          "content:write",
          "publishing:write",
          "analytics:read",
        ],
      },
    },
  ],
};

async function mockSession(page: import("@playwright/test").Page) {
  let accessToken: string | null = "token";

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1", "");
    const method = request.method();

    if ((path === "/auth/refresh" || path === "/auth/sign-in") && method === "POST") {
      accessToken = "token";
      await route.fulfill({
        status: 200,
        body: JSON.stringify({ access_token: accessToken, token_type: "bearer", user: sessionUser }),
      });
      return;
    }
    if (path === "/auth/me" && method === "GET") {
      await route.fulfill({ status: 200, body: JSON.stringify(sessionUser) });
      return;
    }
    if (path === "/health/ready" && method === "GET") {
      await route.fulfill({ status: 200, body: JSON.stringify({ status: "ok" }) });
      return;
    }
    if (path === "/stories/trends/dashboard" && method === "GET") {
      await route.fulfill({ status: 200, body: JSON.stringify({ summary: [], clusters: [] }) });
      return;
    }
    if (path === "/analytics/overview" && method === "GET") {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          totals: {},
          engagement_by_platform: [],
          learning_log: [],
        }),
      });
      return;
    }
    if (path === "/audit/logs" && method === "GET") {
      await route.fulfill({
        status: 200,
        body: JSON.stringify([
          {
            id: "1",
            action: "publish.succeeded",
            entity_type: "post",
            entity_id: "p1",
            message: "Published to X",
          },
        ]),
      });
      return;
    }

    await route.fulfill({ status: 200, body: JSON.stringify([]) });
  });
}

test.describe("mobile navigation and tables", () => {
  test.use({ ...devices["Pixel 5"] });

  test("opens drawer destinations and keeps audit table usable", async ({ page }) => {
    await mockSession(page);
    await page.addInitScript(() => {
      localStorage.setItem("signalforge-theme", "light");
    });

    await page.goto("/");
    await page.getByLabel("Email").fill("demo@example.com");
    await page.getByLabel("Password").fill("password1234");
    await page.getByRole("button", { name: "Sign In" }).click();
    await expect(page).toHaveURL(/\/dashboard/);

    await page.getByLabel("Open navigation menu").click();
    const drawer = page.getByRole("dialog");
    await expect(drawer.getByRole("link", { name: "Briefs" })).toBeVisible();
    await expect(drawer.getByRole("link", { name: "Account" })).toBeVisible();
    await drawer.getByRole("link", { name: "Audit" }).click();
    await expect(page).toHaveURL(/\/dashboard\/audit/);

    const tableRegion = page.getByRole("region", { name: "Audit log entries" });
    await expect(tableRegion).toBeVisible();
    await expect(tableRegion.getByText("publish.succeeded")).toBeVisible();
  });
});

test.describe("desktop command palette coverage", () => {
  test("command palette includes previously missing destinations", async ({ page }) => {
    await mockSession(page);
    await page.goto("/");
    await page.getByLabel("Email").fill("demo@example.com");
    await page.getByLabel("Password").fill("password1234");
    await page.getByRole("button", { name: "Sign In" }).click();
    await expect(page).toHaveURL(/\/dashboard/);

    await page.getByLabel("Open command palette").click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("option", { name: "Trending Repos" })).toBeVisible();
    await expect(dialog.getByRole("option", { name: "Brand" })).toBeVisible();
    await expect(dialog.getByLabel("Close dialog")).toBeVisible();
  });
});
