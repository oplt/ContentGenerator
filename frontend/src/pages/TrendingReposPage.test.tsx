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
      product_ideas: [
        {
          title: "AgentOps Console",
          problem: "Teams cannot observe agent failures.",
          solution: "Hosted control plane for debugging and replay.",
          target_audience: "AI product teams",
          monetization: "$299/mo per workspace",
          wow_factor: "Replay any agent run in seconds.",
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

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Hide Ideas" })).toBeInTheDocument();
    });
  });
});
