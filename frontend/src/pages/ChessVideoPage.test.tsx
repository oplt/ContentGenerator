import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ChessVideoPage from "./ChessVideoPage";
import DashboardPage from "./DashboardPage";
import type { ChessVideoJob, ChessVideoValidation } from "../api/chessVideos";
import { useWorkspaceStore } from "../store/workspaceStore";

const validateChessGame = vi.fn<(...args: unknown[]) => Promise<ChessVideoValidation>>();
const createChessVideo = vi.fn<(...args: unknown[]) => Promise<ChessVideoJob>>();
const getChessVideoJobs = vi.fn<(...args: unknown[]) => Promise<ChessVideoJob[]>>();
const getChessVideoJob = vi.fn<(...args: unknown[]) => Promise<ChessVideoJob>>();
const retryChessVideoJob = vi.fn();
const deleteChessVideoJob = vi.fn<(...args: unknown[]) => Promise<void>>();

vi.mock("../api/chessVideos", async () => {
  const actual = await vi.importActual<typeof import("../api/chessVideos")>("../api/chessVideos");
  return {
    ...actual,
    validateChessGame: (...args: unknown[]) => validateChessGame(...args),
    createChessVideo: (...args: unknown[]) => createChessVideo(...args),
    getChessVideoJobs: (...args: unknown[]) => getChessVideoJobs(...args),
    getChessVideoJob: (...args: unknown[]) => getChessVideoJob(...args),
    retryChessVideoJob: (...args: unknown[]) => retryChessVideoJob(...args),
    deleteChessVideoJob: (...args: unknown[]) => deleteChessVideoJob(...args),
  };
});

vi.mock("../api/stories", () => ({
  getTrendDashboard: vi.fn(async () => ({ clusters: [] })),
  getStoryClusters: vi.fn(async () => []),
}));
vi.mock("../api/analytics", () => ({
  getAnalyticsOverview: vi.fn(async () => ({ summary: [] })),
}));
vi.mock("../api/health", () => ({
  getHealthReadiness: vi.fn(async () => ({
    status: "ready",
    worker_status: [],
    checks: { inference: "ok" },
  })),
}));
vi.mock("../api/sources", () => ({ getSources: vi.fn(async () => []) }));
vi.mock("../api/content", () => ({
  getContentPlans: vi.fn(async () => []),
  getContentJobs: vi.fn(async () => []),
}));
vi.mock("../api/approvals", () => ({ getApprovalRequests: vi.fn(async () => []) }));
vi.mock("../api/publishing", () => ({ getPublishedPosts: vi.fn(async () => []) }));

function job(overrides: Partial<ChessVideoJob> = {}): ChessVideoJob {
  return {
    id: "job-1",
    tenant_id: "tenant-1",
    status: "queued",
    stage: "queued",
    progress: 0,
    input_format: "san",
    move_count: 2,
    orientation: "white",
    render_preset: "economy_vertical",
    board_theme: "classic_wood",
    seconds_per_move: 1,
    include_coordinates: true,
    include_move_text: true,
    white_player: "Kasparov",
    black_player: "Karpov",
    created_at: "2026-09-15T10:00:00Z",
    updated_at: "2026-09-15T10:00:00Z",
    ...overrides,
  };
}

function renderChessPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/dashboard/chess-video"]}>
        <Routes>
          <Route path="/dashboard/chess-video" element={<ChessVideoPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useWorkspaceStore.setState({ tenantId: "tenant-1", tenantName: "Tenant" });
  validateChessGame.mockReset();
  createChessVideo.mockReset();
  getChessVideoJobs.mockReset().mockResolvedValue([]);
  getChessVideoJob.mockReset();
  retryChessVideoJob.mockReset();
  deleteChessVideoJob.mockReset().mockResolvedValue(undefined);
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

describe("DashboardPage chess CTA", () => {
  it("does not show Create Chess Video on overview", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <DashboardPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Pipeline")).toBeInTheDocument();
    expect(screen.queryByText("Create Chess Video")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /open creator/i })).not.toBeInTheDocument();
  });
});

describe("ChessVideoPage", () => {
  it("keeps Generate Video disabled until validation succeeds", async () => {
    const user = userEvent.setup();
    renderChessPage();
    const generate = await screen.findByRole("button", { name: /generate video/i });
    expect(generate).toBeDisabled();

    await user.type(screen.getByPlaceholderText(/paste pgn/i), "1. e4 e5");
    validateChessGame.mockResolvedValue({
      valid: true,
      input_format: "san",
      detected_format: "san",
      white_player: "Kasparov",
      black_player: "Karpov",
      event: "WC",
      result: "1-0",
      move_count: 2,
      errors: [],
    });
    await user.click(screen.getByRole("button", { name: /validate game/i }));
    await waitFor(() => expect(screen.getByText("Kasparov")).toBeInTheDocument());
    expect(screen.getByText("Karpov")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate video/i })).toBeEnabled();
  });

  it("lets the user pick a board theme before generate", async () => {
    const user = userEvent.setup();
    validateChessGame.mockResolvedValue({
      valid: true,
      input_format: "san",
      move_count: 2,
      errors: [],
    });
    createChessVideo.mockResolvedValue(job({ status: "queued", board_theme: "midnight_blue" }));
    getChessVideoJob.mockResolvedValue(job({ status: "queued", board_theme: "midnight_blue" }));

    renderChessPage();
    await user.type(screen.getByPlaceholderText(/paste pgn/i), "1. e4 e5");
    await user.click(screen.getByRole("button", { name: /validate game/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /generate video/i })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: /midnight blue/i }));
    await user.click(screen.getByRole("button", { name: /generate video/i }));
    await waitFor(() =>
      expect(createChessVideo).toHaveBeenCalledWith(
        expect.objectContaining({ board_theme: "midnight_blue" }),
      ),
    );
  });

  it("shows invalid validation errors", async () => {
    const user = userEvent.setup();
    renderChessPage();
    await user.type(screen.getByPlaceholderText(/paste pgn/i), "1. Qh8");
    validateChessGame.mockResolvedValue({
      valid: false,
      input_format: "san",
      move_count: 0,
      errors: ["Illegal move at ply 1: Qh8"],
    });
    await user.click(screen.getByRole("button", { name: /validate game/i }));
    expect(await screen.findByText(/Illegal move at ply 1/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate video/i })).toBeDisabled();
  });

  it("creates a job and shows completed video preview", async () => {
    const user = userEvent.setup();
    validateChessGame.mockResolvedValue({
      valid: true,
      input_format: "san",
      detected_format: "san",
      move_count: 2,
      errors: [],
    });
    createChessVideo.mockResolvedValue(job({ status: "queued", progress: 0 }));
    getChessVideoJob.mockResolvedValue(
      job({
        status: "completed",
        stage: "completed",
        progress: 1,
        video_public_url: "http://cdn/video.mp4",
        thumbnail_public_url: "http://cdn/thumb.png",
        duration_seconds: 3,
        width: 720,
        height: 1280,
        file_size_bytes: 2048,
      }),
    );

    renderChessPage();
    await user.type(screen.getByPlaceholderText(/paste pgn/i), "1. e4 e5");
    await user.click(screen.getByRole("button", { name: /validate game/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /generate video/i })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: /generate video/i }));

    expect(await screen.findByText(/Preview & Export/)).toBeInTheDocument();
    await waitFor(() => {
      const el = document.querySelector("video");
      expect(el).toBeTruthy();
      expect(el).toHaveAttribute("src", "http://cdn/video.mp4");
    });
  });

  it("supports PGN file upload into the paste buffer", async () => {
    const user = userEvent.setup();
    renderChessPage();
    await user.click(screen.getByRole("tab", { name: /upload pgn/i }));
    const contents = '[Event "Test"]\n\n1. e4 e5 *\n';
    const file = new File([contents], "game.pgn", { type: "text/plain" });
    Object.defineProperty(file, "text", {
      value: async () => contents,
    });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input).toBeTruthy();
    await user.upload(input, file);
    await waitFor(() => {
      expect(screen.getByDisplayValue(/1\. e4 e5/)).toBeInTheDocument();
    });
  });

  it("shows render progress while job is active", async () => {
    getChessVideoJobs.mockResolvedValue([
      job({ status: "rendering", stage: "rendering", progress: 0.72 }),
    ]);
    getChessVideoJob.mockResolvedValue(
      job({ status: "rendering", stage: "rendering", progress: 0.72 }),
    );
    renderChessPage();
    await userEvent.click(await screen.findByRole("tab", { name: /history/i }));
    await userEvent.click(await screen.findByRole("button", { name: /kasparov vs karpov/i }));
    expect(await screen.findByText("Generating video")).toBeInTheDocument();
    expect(screen.getByText("72%")).toBeInTheDocument();
  });

  it("shows failed state with retry", async () => {
    retryChessVideoJob.mockResolvedValue(job({ status: "queued", progress: 0 }));
    getChessVideoJobs.mockResolvedValue([
      job({
        status: "failed",
        stage: "failed",
        progress: 0.5,
        error_message: "FFmpeg encoding failed",
      }),
    ]);
    getChessVideoJob.mockResolvedValue(
      job({
        status: "failed",
        stage: "failed",
        progress: 0.5,
        error_message: "FFmpeg encoding failed",
      }),
    );
    renderChessPage();
    await userEvent.click(await screen.findByRole("tab", { name: /history/i }));
    await userEvent.click(await screen.findByRole("button", { name: /kasparov vs karpov/i }));
    expect(await screen.findByText(/FFmpeg encoding failed/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeEnabled();
  });

  it("deletes a recent job from the trash control", async () => {
    const user = userEvent.setup();
    getChessVideoJobs.mockResolvedValue([job()]);
    renderChessPage();
    await user.click(await screen.findByRole("tab", { name: /history/i }));
    await screen.findByRole("button", { name: /kasparov vs karpov/i });
    await user.click(screen.getByRole("button", { name: /delete chess video job/i }));
    await waitFor(() => expect(deleteChessVideoJob).toHaveBeenCalledWith("job-1"));
  });
});
