import { queryKeyFactories } from "./queryKeys";

describe("queryKeyFactories", () => {
  it("exposes every required domain factory", () => {
    expect(Object.keys(queryKeyFactories).sort()).toEqual(
      [
        "analytics",
        "auth",
        "briefs",
        "content",
        "health",
        "publishing",
        "settings",
        "sources",
        "stories",
        "trending",
        "users",
      ].sort()
    );
  });

  it("returns stable keys for identical inputs", () => {
    expect(queryKeyFactories.sources.articlePage("tenant-a", 50, "cursor-1")).toEqual(
      queryKeyFactories.sources.articlePage("tenant-a", 50, "cursor-1")
    );
  });

  it("isolates tenant-scoped domains", () => {
    expect(queryKeyFactories.settings.tenant("tenant-a")).not.toEqual(
      queryKeyFactories.settings.tenant("tenant-b")
    );
    expect(queryKeyFactories.analytics.account("tenant-a", "account-1")).toEqual([
      "tenant",
      "tenant-a",
      "analytics",
      "account-1",
    ]);
  });

  it("keeps global domains outside tenant scope", () => {
    expect(queryKeyFactories.auth.root).toEqual(["auth"]);
    expect(queryKeyFactories.health.ready).toEqual(["health", "ready"]);
    expect(queryKeyFactories.users.profile).toEqual(["user-profile"]);
  });
});
