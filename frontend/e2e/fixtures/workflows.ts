import type { Page } from "@playwright/test";

const DEF = {
  id: "wf-e2e-1",
  tenant_id: "tenant-1",
  name: "E2E Chess Caption",
  slug: "e2e-chess-caption",
  description: null,
  status: "active",
  current_version_id: "ver-e2e-1",
  created_by_user_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const RUN = {
  id: "run-e2e-1",
  tenant_id: "tenant-1",
  automation_id: null,
  workflow_definition_id: DEF.id,
  workflow_version_id: "ver-e2e-1",
  brand_id: null,
  trigger_type: "dry_run",
  status: "succeeded",
  started_at: "2026-01-01T12:00:00Z",
  finished_at: "2026-01-01T12:01:00Z",
  error_message: null,
  correlation_id: "corr-e2e",
};

/** Workflow API stubs — register after dashboard catch-all (LIFO wins). */
export async function installWorkflowApiMocks(page: Page): Promise<void> {
  await page.route("**/api/v1/workflows/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/.*\/api\/v1/, "");
    const method = request.method();

    if (path === "/workflows/definitions" && method === "GET") {
      await route.fulfill({ status: 200, body: JSON.stringify([DEF]) });
      return;
    }
    if (path === "/workflows/definitions" && method === "POST") {
      await route.fulfill({ status: 200, body: JSON.stringify({ ...DEF, id: "wf-e2e-2", name: "Created" }) });
      return;
    }
    if (path.match(/^\/workflows\/definitions\/[^/]+\/draft$/) && method === "PUT") {
      await route.fulfill({ status: 200, body: JSON.stringify({ ok: true }) });
      return;
    }
    if (path === "/workflows/automations" && method === "GET") {
      await route.fulfill({
        status: 200,
        body: JSON.stringify([
          {
            id: "auto-1",
            name: "Chess daily",
            enabled: false,
            trigger_type: "manual",
            next_run_at: null,
            targets: [],
          },
        ]),
      });
      return;
    }
    if (path === "/workflows/brands" && method === "GET") {
      await route.fulfill({
        status: 200,
        body: JSON.stringify([{ id: "brand-1", name: "Chess" }]),
      });
      return;
    }
    if (path === "/workflows/runs" && method === "GET") {
      await route.fulfill({ status: 200, body: JSON.stringify([RUN]) });
      return;
    }
    if (path === `/workflows/runs/${RUN.id}` && method === "GET") {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          run: RUN,
          nodes: [
            {
              id: "nr-1",
              node_id: "generate",
              node_type: "generate_text",
              status: "succeeded",
              attempt: 1,
              input_json: { prompt: "tip" },
              output_json: { text: "ok", provider: "mock" },
              error_json: null,
              resume_token: null,
            },
            {
              id: "nr-2",
              node_id: "publish",
              node_type: "publish",
              status: "succeeded",
              attempt: 1,
              input_json: { idempotency_key: `wf-publish-${RUN.id}` },
              output_json: { dry_run: true, job_ids: [] },
              error_json: null,
              resume_token: null,
            },
          ],
        }),
      });
      return;
    }

    await route.fulfill({ status: 200, body: JSON.stringify([]) });
  });
}
