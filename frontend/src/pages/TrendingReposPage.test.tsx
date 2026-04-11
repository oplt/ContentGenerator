import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TrendingReposPage from "./TrendingReposPage";
import type { TrendingRepo, TrendingReposListResponse } from "../api/trending";

const getTrendingRepos = vi.fn<(...args: unknown[]) => Promise<TrendingReposListResponse>>();
const refreshTrendingRepos = vi.fn();
const generateProductIdeas = vi.fn<(...args: unknown[]) => Promise<TrendingRepo>>();

vi.mock("../api/trending", async () => {
  const actual = await vi.importActual<typeof import("../api/trending")>("../api/trending");
  return {
    ...actual,
    getTrendingRepos: (...args: unknown[]) => getTrendingRepos(...args),
    refreshTrendingRepos: (...args: unknown[]) => refreshTrendingRepos(...args),
    generateProductIdeas: (...args: unknown[]) => generateProductIdeas(...args),
  };
});

function buildRepo(overrides: Partial<TrendingRepo> = {}): TrendingRepo {
  return {
    id: "repo-1",
    period: "daily",
    snapshot_date: "2026-04-10",
    github_id: 1,
    name: "acme/rocket",
    full_name: "acme/rocket",
    description: "Realtime agent runtime",
    html_url: "https://github.com/acme/rocket",
    language: "TypeScript",
    topics: ["agents", "runtime"],
    stars_count: 1000,
    forks_count: 10,
    watchers_count: 10,
    open_issues_count: 1,
    stars_gained: 123,
    rank: 1,
    repo_assessment: null,
    product_ideas: [],
    ideas_generated_at: null,
    created_at: "2026-04-10T00:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <TrendingReposPage />
    </QueryClientProvider>
  );
}

describe("TrendingReposPage", () => {
  beforeEach(() => {
    getTrendingRepos.mockReset();
    refreshTrendingRepos.mockReset();
    generateProductIdeas.mockReset();
  });

  it("renders generated ideas immediately after the mutation succeeds", async () => {
    const repoWithoutIdeas = buildRepo();
    const repoWithIdeas = buildRepo({
      repo_assessment: {
        what_it_does: "Runtime for long-running AI agents.",
        evidence: ["README describes long-running agents"],
        strongest_assets: ["Agent orchestration primitives"],
        main_limitations: ["No hosted product layer"],
        best_commercial_angle: "Observability control plane for production agent teams",
        confidence: "medium",
      },
      product_ideas: [
        {
          rank: 1,
          title: "AgentOps Console",
          positioning: "Replay any agent run in seconds.",
          target_customer: "AI product teams",
          pain_point: "Teams cannot observe agent failures.",
          product_concept: "Hosted control plane for debugging and replay.",
          why_this_repo_fits: "The repo already orchestrates long-running agents.",
          required_extensions: ["Hosted auth and billing"],
          monetization: {
            model: "SaaS",
            pricing_logic: "$299/mo per workspace",
            estimated_willingness_to_pay: "High for production teams",
          },
          scores: {
            revenue_potential: 8,
            customer_urgency: 8,
            repo_leverage: 9,
            speed_to_mvp: 7,
            competitive_intensity: 6,
          },
          time_to_mvp: "6 weeks",
          key_risks: ["Crowded observability market"],
          why_now: "Agent teams are moving into production.",
          investor_angle: "Strong infra wedge with expansion revenue.",
          v1_scope: ["Replay", "logs", "alerts"],
          not_for_v1: ["Enterprise SSO"],
        },
      ],
      ideas_generated_at: "2026-04-10T10:00:00Z",
    });

    getTrendingRepos.mockResolvedValue({
      repos: [repoWithoutIdeas],
      period: "daily",
      snapshot_date: "2026-04-10",
      total: 1,
    });
    refreshTrendingRepos.mockResolvedValue(undefined);
    generateProductIdeas.mockResolvedValue(repoWithIdeas);

    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("acme/rocket")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Generate Ideas" }));

    expect(await screen.findByText("AI-Generated Product Ideas")).toBeInTheDocument();
    expect(screen.getByText("AgentOps Console")).toBeInTheDocument();
    expect(screen.getByText("Repo Assessment")).toBeInTheDocument();
    expect(
      screen.getByText(/Observability control plane for production agent teams/)
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Hide Ideas" })).toBeInTheDocument();
    });
  });

  it("shows the backend generation error instead of a generic fallback message", async () => {
    getTrendingRepos.mockResolvedValue({
      repos: [buildRepo()],
      period: "daily",
      snapshot_date: "2026-04-10",
      total: 1,
    });
    refreshTrendingRepos.mockResolvedValue(undefined);
    generateProductIdeas.mockRejectedValue(
      new Error("Idea generation returned unusable output. No ideas were saved.")
    );

    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("acme/rocket")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Generate Ideas" }));

    expect(
      await screen.findByText("Idea generation returned unusable output. No ideas were saved.")
    ).toBeInTheDocument();
  });
});
