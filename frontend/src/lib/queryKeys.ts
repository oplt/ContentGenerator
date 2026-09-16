export const TENANT_KEY_ROOT = "tenant" as const;

export type TenantQueryKey = readonly [typeof TENANT_KEY_ROOT, string, ...Array<string | number>];

export function tenantQueryKey(tenantId: string, ...parts: Array<string | number>): TenantQueryKey {
  return [TENANT_KEY_ROOT, tenantId, ...parts] as const;
}

export function isTenantQueryKey(queryKey: readonly unknown[]): queryKey is TenantQueryKey {
  return queryKey[0] === TENANT_KEY_ROOT && typeof queryKey[1] === "string";
}

export function isTenantQueryFor(tenantId: string, queryKey: readonly unknown[]): boolean {
  return isTenantQueryKey(queryKey) && queryKey[1] === tenantId;
}

/** Global (non-tenant) keys — never cleared on tenant switch. */
export const globalQueryKeys = {
  appConfig: ["app-config"] as const,
  healthReady: ["health", "ready"] as const,
  auth: ["auth"] as const,
  userProfile: ["user-profile"] as const,
  userSessions: ["user-sessions"] as const,
} as const;

export const queryKeyFactories = {
  auth: {
    root: globalQueryKeys.auth,
  },
  settings: {
    app: globalQueryKeys.appConfig,
    tenant: (tenantId: string) => tenantQueryKey(tenantId, "tenant-settings"),
    brand: (tenantId: string) => tenantQueryKey(tenantId, "brand-profile"),
    whatsapp: (tenantId: string) => tenantQueryKey(tenantId, "settings", "whatsapp"),
    telegram: (tenantId: string) => tenantQueryKey(tenantId, "settings", "telegram"),
  },
  sources: {
    all: (tenantId: string) => tenantQueryKey(tenantId, "sources"),
    health: (tenantId: string) => tenantQueryKey(tenantId, "sources", "health"),
    articles: (tenantId: string) => tenantQueryKey(tenantId, "sources", "articles"),
    articlePage: (tenantId: string, limit: number, cursor?: string) =>
      tenantQueryKey(tenantId, "sources", "articles", limit, cursor ?? "first"),
    catalog: (tenantId: string, category: string) =>
      tenantQueryKey(tenantId, "sources", "catalog", category),
    fetchRuns: (tenantId: string) => tenantQueryKey(tenantId, "sources", "fetch-runs"),
  },
  stories: {
    all: (tenantId: string) => tenantQueryKey(tenantId, "stories"),
    detail: (tenantId: string, id: string) => tenantQueryKey(tenantId, "stories", id),
    candidate: (tenantId: string, id: string) =>
      tenantQueryKey(tenantId, "trend-candidates", id),
  },
  briefs: {
    all: (tenantId: string, status?: string) =>
      status === undefined
        ? tenantQueryKey(tenantId, "briefs")
        : tenantQueryKey(tenantId, "briefs", status),
  },
  content: {
    all: (tenantId: string) => tenantQueryKey(tenantId, "content"),
    plans: (tenantId: string) => tenantQueryKey(tenantId, "content", "plans"),
    jobs: (tenantId: string) => tenantQueryKey(tenantId, "content", "jobs"),
    job: (tenantId: string, id: string) => tenantQueryKey(tenantId, "content", "job", id),
  },
  publishing: {
    jobs: (tenantId: string) => tenantQueryKey(tenantId, "publishing", "jobs"),
    posts: (tenantId: string) => tenantQueryKey(tenantId, "publishing", "posts"),
    connectedAccounts: (tenantId: string) =>
      tenantQueryKey(tenantId, "publishing", "connected-accounts"),
    socialAccounts: (tenantId: string) =>
      tenantQueryKey(tenantId, "publishing", "social-accounts"),
  },
  analytics: {
    all: (tenantId: string) => tenantQueryKey(tenantId, "analytics"),
    account: (tenantId: string, accountId?: string) =>
      tenantQueryKey(tenantId, "analytics", accountId || "all"),
  },
  users: {
    profile: globalQueryKeys.userProfile,
    sessions: globalQueryKeys.userSessions,
  },
  trending: {
    candidates: (tenantId: string) => tenantQueryKey(tenantId, "trend-candidates"),
    repos: (tenantId: string, period?: string) =>
      period === undefined
        ? tenantQueryKey(tenantId, "trending-repos")
        : tenantQueryKey(tenantId, "trending-repos", period),
  },
  chessVideos: {
    all: (tenantId: string) => tenantQueryKey(tenantId, "chess-videos"),
    job: (tenantId: string, jobId: string) =>
      tenantQueryKey(tenantId, "chess-videos", "job", jobId),
  },
  workflows: {
    definitions: (tenantId: string) => tenantQueryKey(tenantId, "workflows", "definitions"),
    definition: (tenantId: string, definitionId: string) =>
      tenantQueryKey(tenantId, "workflows", "definitions", definitionId),
    versions: (tenantId: string, definitionId: string) =>
      tenantQueryKey(tenantId, "workflows", "versions", definitionId),
    nodes: (tenantId: string) => tenantQueryKey(tenantId, "workflows", "nodes"),
    runs: (tenantId: string, status?: string) =>
      status
        ? tenantQueryKey(tenantId, "workflows", "runs", status)
        : tenantQueryKey(tenantId, "workflows", "runs"),
    run: (tenantId: string, runId: string) =>
      tenantQueryKey(tenantId, "workflows", "runs", "detail", runId),
    automations: (tenantId: string) => tenantQueryKey(tenantId, "workflows", "automations"),
    brands: (tenantId: string) => tenantQueryKey(tenantId, "workflows", "brands"),
  },
  health: {
    ready: globalQueryKeys.healthReady,
  },
} as const;

/** Compatibility aliases for existing consumers. New keys belong in a domain factory above. */
export const queryKeys = {
  ...globalQueryKeys,
  sources: queryKeyFactories.sources.all,
  sourceHealth: queryKeyFactories.sources.health,
  sourceArticles: queryKeyFactories.sources.articles,
  sourceCatalog: queryKeyFactories.sources.catalog,
  sourceFetchRuns: queryKeyFactories.sources.fetchRuns,
  stories: queryKeyFactories.stories.all,
  story: queryKeyFactories.stories.detail,
  trendCandidates: queryKeyFactories.trending.candidates,
  content: queryKeyFactories.content.all,
  contentPlans: queryKeyFactories.content.plans,
  contentJobs: queryKeyFactories.content.jobs,
  contentJob: queryKeyFactories.content.job,
  approvals: (tenantId: string) => tenantQueryKey(tenantId, "approvals"),
  publishingJobs: queryKeyFactories.publishing.jobs,
  publishingPosts: queryKeyFactories.publishing.posts,
  connectedAccounts: queryKeyFactories.publishing.connectedAccounts,
  socialAccounts: queryKeyFactories.publishing.socialAccounts,
  analytics: queryKeyFactories.analytics.all,
  brandProfile: queryKeyFactories.settings.brand,
  tenantSettings: queryKeyFactories.settings.tenant,
  whatsappSettings: queryKeyFactories.settings.whatsapp,
  telegramSettings: queryKeyFactories.settings.telegram,
  auditLogs: (tenantId: string) => tenantQueryKey(tenantId, "audit", "logs"),
  briefs: queryKeyFactories.briefs.all,
  dashboardTrends: (tenantId: string) => tenantQueryKey(tenantId, "dashboard", "trends"),
  dashboardAnalytics: (tenantId: string) => tenantQueryKey(tenantId, "dashboard", "analytics"),
  trendingRepos: queryKeyFactories.trending.repos,
  chessVideos: queryKeyFactories.chessVideos.all,
  chessVideoJob: queryKeyFactories.chessVideos.job,
  workflowDefinitions: queryKeyFactories.workflows.definitions,
  workflowDefinition: queryKeyFactories.workflows.definition,
  workflowVersions: queryKeyFactories.workflows.versions,
  workflowNodes: queryKeyFactories.workflows.nodes,
  workflowRuns: queryKeyFactories.workflows.runs,
  workflowRun: queryKeyFactories.workflows.run,
  workflowAutomations: queryKeyFactories.workflows.automations,
  workflowBrands: queryKeyFactories.workflows.brands,
} as const;
