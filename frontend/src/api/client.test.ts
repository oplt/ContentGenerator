import { refreshSession } from "./client";

describe("refreshSession", () => {
  it("shares one refresh request between concurrent callers", async () => {
    let resolveResponse: ((response: Response) => void) | undefined;
    const responsePromise = new Promise<Response>((resolve) => {
      resolveResponse = resolve;
    });
    const fetchMock = vi.fn(() => responsePromise);
    vi.stubGlobal("fetch", fetchMock);

    const first = refreshSession<{ user: { id: string } }>();
    const second = refreshSession<{ user: { id: string } }>();

    expect(first).toBe(second);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    resolveResponse?.(new Response(JSON.stringify({ user: { id: "user-1" } }), { status: 200 }));
    await expect(first).resolves.toEqual({ user: { id: "user-1" } });

    vi.unstubAllGlobals();
  });
});
