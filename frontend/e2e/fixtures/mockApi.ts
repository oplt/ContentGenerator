import type { Page } from "@playwright/test";
import { DEMO_SESSION_USER } from "./session";

export type FlowState = {
  sources: Array<Record<string, unknown>>;
  clusters: Array<Record<string, unknown>>;
  plans: Array<Record<string, unknown>>;
  jobs: Array<Record<string, unknown>>;
  approvals: Array<Record<string, unknown>>;
  publishingJobs: Array<Record<string, unknown>>;
  posts: Array<Record<string, unknown>>;
};

export function createFlowState(): FlowState {
  return {
    sources: [],
    clusters: [],
    plans: [],
    jobs: [],
    approvals: [],
    publishingJobs: [],
    posts: [],
  };
}

export type MockApiContext = {
  state: FlowState;
  accessToken: string | null;
};

export function createMockApiContext(state: FlowState = createFlowState()): MockApiContext {
  return { state, accessToken: null };
}

/** Install the shared /api/v1 mock used by domain E2E specs. Contracts unchanged from full-flow. */
export async function installDashboardApiMocks(page: Page, ctx: MockApiContext): Promise<void> {
  const sessionUser = DEMO_SESSION_USER;
  const state = ctx.state;

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1", "");
    const method = request.method();

    if (path === "/auth/refresh" && method === "POST") {
      if (!ctx.accessToken) {
        await route.fulfill({ status: 401, body: JSON.stringify({ error: { message: "Session expired" } }) });
        return;
      }

      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          access_token: ctx.accessToken,
          token_type: "bearer",
          user: sessionUser,
        }),
      });
      return;
    }

    if (path === "/auth/sign-in" && method === "POST") {
      ctx.accessToken = "token";
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          access_token: ctx.accessToken,
          token_type: "bearer",
          user: sessionUser,
        }),
      });
      return;
    }

    if (path === "/stories/trends/dashboard" && method === "GET") {
      await route.fulfill({ status: 200, body: JSON.stringify({ summary: [], clusters: state.clusters }) });
      return;
    }

    if (path === "/analytics/overview" && method === "GET") {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          summary: [
            { key: "posts", label: "Published posts", value: state.posts.length },
            { key: "views", label: "Views", value: 1200 },
            { key: "engagement", label: "Engagement", value: 220 },
          ],
          posts_over_time: [{ label: "2026-04-05", value: 1200 }],
          engagement_by_platform: [{ label: "x", value: 400 }],
          format_performance: [{ label: "text", value: 900 }],
          topic_performance: [{ label: "ai", value: 1200 }],
          publishing_funnel: [{ label: "Generated", value: state.jobs.length }],
          source_reliability: [{ label: "TechCrunch", value: 1, secondary: 0 }],
        }),
      });
      return;
    }

    if (path === "/sources" && method === "GET") {
      await route.fulfill({ status: 200, body: JSON.stringify(state.sources) });
      return;
    }

    if (path === "/sources" && method === "POST") {
      const payload = JSON.parse(request.postData() ?? "{}");
      const source = {
        id: "source-1",
        parser_type: "auto",
        trust_score: 0.7,
        active: true,
        failure_count: 0,
        success_count: 0,
        circuit_state: "closed",
        last_polled_at: null,
        last_success_at: null,
        ...payload,
      };
      state.sources = [source];
      await route.fulfill({ status: 201, body: JSON.stringify(source) });
      return;
    }

    if (path === "/sources/health" && method === "GET") {
      await route.fulfill({ status: 200, body: JSON.stringify(state.sources.map((source) => ({
        source_id: source.id,
        status: "healthy",
        failure_count: 0,
        success_count: 1,
        circuit_state: "closed",
        negative_cache_until: null,
        last_success_at: null,
      }))) });
      return;
    }

    if (path === "/sources/articles" && method === "GET") {
      await route.fulfill({ status: 200, body: JSON.stringify([]) });
      return;
    }

    if (path === "/sources/source-1/ingest" && method === "POST") {
      state.clusters = [
        {
          id: "cluster-1",
          slug: "ai-editor",
          headline: "AI editor launches for social teams",
          summary: "A startup shipped a new editor for content operations.",
          primary_topic: "ai",
          article_count: 2,
          trend_direction: "up",
          worthy_for_content: true,
          risk_level: "safe",
          explainability: { keywords: "ai,editor", score: "0.82" },
          latest_trend_score: 0.82,
        },
      ];
      await route.fulfill({ status: 200, body: JSON.stringify({ status: "success", raw_articles_ingested: 1, clusters_updated: 1 }) });
      return;
    }

    if (path === "/stories/clusters" && method === "GET") {
      await route.fulfill({ status: 200, body: JSON.stringify(state.clusters) });
      return;
    }

    if (path === "/stories/clusters/cluster-1" && method === "GET") {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          ...state.clusters[0],
          articles: [
            {
              id: "article-1",
              title: "AI editor launches for social teams",
              summary: "Story summary",
              canonical_url: "https://example.com/article",
              source_name: "TechCrunch",
              keywords: ["ai", "editor"],
              topic_tags: ["ai"],
              published_at: null,
            },
          ],
          trend_score: { score: 0.82, freshness_score: 0.9, credibility_score: 0.8, momentum_score: 0.6, worthiness_score: 0.82 },
        }),
      });
      return;
    }

    if (path === "/content/brand-profile" && method === "GET") {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          id: "brand-1",
          name: "Default Brand",
          niche: "general",
          tone: "authoritative",
          audience: "Busy operators",
          voice_notes: null,
          preferred_platforms: ["x", "bluesky"],
          default_cta: "Follow for more.",
          hashtags_strategy: "balanced",
          risk_tolerance: "medium",
          require_whatsapp_approval: true,
          guardrails: {},
          visual_style: {},
        }),
      });
      return;
    }

    if (path === "/content/plans" && method === "GET") {
      await route.fulfill({ status: 200, body: JSON.stringify(state.plans) });
      return;
    }

    if (path === "/content/plans" && method === "POST") {
      const plan = {
        id: "plan-1",
        story_cluster_id: "cluster-1",
        brand_profile_id: "brand-1",
        status: "ready",
        decision: "generate",
        content_format: "text",
        target_platforms: ["x", "bluesky"],
        tone: "authoritative",
        urgency: "normal",
        risk_flags: [],
        recommended_cta: "Follow for more.",
        hashtags_strategy: "balanced",
        approval_required: true,
        safe_to_publish: true,
        policy_trace: { score: "0.82" },
        scheduled_for: null,
      };
      state.plans = [plan];
      await route.fulfill({ status: 201, body: JSON.stringify(plan) });
      return;
    }

    if (path === "/content/jobs" && method === "GET") {
      await route.fulfill({ status: 200, body: JSON.stringify(state.jobs) });
      return;
    }

    if (path === "/content/generate" && method === "POST") {
      const job = {
        id: "job-1",
        content_plan_id: "plan-1",
        revision_of_job_id: null,
        job_type: "text",
        status: "completed",
        stage: "completed",
        progress: 100,
        feedback: null,
        error_message: null,
        started_at: null,
        completed_at: null,
        assets: [
          {
            id: "asset-1",
            asset_type: "text_variant",
            platform: "x",
            variant_label: "A",
            public_url: null,
            mime_type: "text/markdown",
            metadata: {},
            source_trace: {},
            text_content: "AI editor launches for social teams. Follow for more.",
          },
        ],
      };
      state.jobs = [job];
      await route.fulfill({ status: 201, body: JSON.stringify(job) });
      return;
    }

    if (path === "/content/jobs/job-1" && method === "GET") {
      await route.fulfill({ status: 200, body: JSON.stringify(state.jobs[0]) });
      return;
    }

    if (path === "/content/jobs/job-1/regenerate" && method === "POST") {
      state.jobs[0] = { ...state.jobs[0], id: "job-2", revision_of_job_id: "job-1", feedback: "Make it tighter" };
      await route.fulfill({ status: 200, body: JSON.stringify(state.jobs[0]) });
      return;
    }

    if (path === "/approvals" && method === "GET") {
      await route.fulfill({ status: 200, body: JSON.stringify(state.approvals) });
      return;
    }

    if (path === "/approvals" && method === "POST") {
      const approval = {
        id: "approval-1",
        content_job_id: state.jobs[0]?.id ?? "job-2",
        status: "pending",
        channel: "whatsapp",
        recipient: "+10000000000",
        provider: "stub",
        provider_request_id: "msg-1",
        requested_at: null,
        responded_at: null,
        revision_count: 0,
        expires_at: null,
        last_sent_at: null,
        messages: [{ id: "message-1", direction: "outbound", channel: "whatsapp", provider_message_id: "msg-1", message_type: "text", raw_text: "Preview", parsed_intent: "unknown", intent_confidence: 1, user_feedback: null, payload: {} }],
      };
      state.approvals = [approval];
      await route.fulfill({ status: 201, body: JSON.stringify(approval) });
      return;
    }

    if (path === "/approvals/whatsapp/webhook" && method === "POST") {
      state.approvals[0] = {
        ...state.approvals[0],
        status: "approved",
        messages: [
          ...state.approvals[0].messages,
          { id: "message-2", direction: "inbound", channel: "whatsapp", provider_message_id: "msg-2", message_type: "text", raw_text: "APPROVE approval-1", parsed_intent: "approve", intent_confidence: 0.98, user_feedback: null, payload: {} },
        ],
      };
      state.publishingJobs = [
        {
          id: "publish-1",
          content_job_id: state.jobs[0]?.id ?? "job-2",
          social_account_id: "account-1",
          approval_request_id: "approval-1",
          platform: "x",
          status: "succeeded",
          provider: "stub",
          idempotency_key: "job-2:x",
          dry_run: true,
          scheduled_for: null,
          published_at: null,
          retry_count: 0,
          failure_reason: null,
          external_post_id: "post-1",
          external_post_url: "https://example.invalid/x/post-1",
          provider_payload: {},
        },
      ];
      state.posts = [
        {
          id: "post-1",
          platform: "x",
          post_type: "text",
          external_post_id: "post-1",
          external_url: "https://example.invalid/x/post-1",
          status: "live",
          published_at: null,
        },
      ];
      await route.fulfill({ status: 202, body: JSON.stringify({ status: "accepted" }) });
      return;
    }

    if (path === "/publishing/queue" && method === "GET") {
      await route.fulfill({ status: 200, body: JSON.stringify(state.publishingJobs) });
      return;
    }

    if (path === "/publishing/posts" && method === "GET") {
      await route.fulfill({ status: 200, body: JSON.stringify(state.posts) });
      return;
    }

    if (path === "/publishing/publish-now" && method === "POST") {
      await route.fulfill({ status: 200, body: JSON.stringify(state.publishingJobs) });
      return;
    }

    if (path === "/settings/tenant" && method === "GET") {
      await route.fulfill({ status: 200, body: JSON.stringify({ id: "tenant-1", name: "Demo Tenant", slug: "demo", plan_tier: "starter", timezone: "UTC", status: "trial", settings: {} }) });
      return;
    }

    if (path === "/audit/logs" && method === "GET") {
      await route.fulfill({ status: 200, body: JSON.stringify([]) });
      return;
    }

    await route.fulfill({ status: 200, body: JSON.stringify([]) });
  });
}
