import { afterEach, describe, expect, it, vi } from "vitest";
import axios, { type AxiosAdapter } from "axios";
import { apiClient } from "./client";

function tokenOf(headers: unknown): string | undefined {
  const auth = (headers as { Authorization?: unknown })?.Authorization;
  return typeof auth === "string" ? auth : undefined;
}

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("apiClient auto-refresh", () => {
  it("refreshes once on 401 and replays the original request with the new token", async () => {
    localStorage.setItem("access_token", "OLD");
    localStorage.setItem("refresh_token", "REFRESH");

    const seen: (string | undefined)[] = [];
    let calls = 0;
    const adapter: AxiosAdapter = (config) => {
      calls += 1;
      seen.push(tokenOf(config.headers));
      if (calls === 1) {
        return Promise.reject({
          isAxiosError: true,
          config,
          response: { status: 401, data: {}, statusText: "", headers: {}, config },
        });
      }
      return Promise.resolve({
        data: { ok: true },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      });
    };

    // Bare-axios refresh call → returns a rotated token pair.
    const postSpy = vi.spyOn(axios, "post").mockResolvedValue({
      data: { access_token: "NEW", refresh_token: "REFRESH2" },
    });

    const res = await apiClient.get("/apps", { adapter });

    expect(res.data).toEqual({ ok: true });
    expect(calls).toBe(2); // original + one retry
    expect(seen[0]).toBe("Bearer OLD"); // first attempt used the stale token
    expect(seen[1]).toBe("Bearer NEW"); // retry used the refreshed token
    expect(postSpy).toHaveBeenCalledTimes(1); // exactly one refresh
    expect(localStorage.getItem("access_token")).toBe("NEW");
    expect(localStorage.getItem("refresh_token")).toBe("REFRESH2");
  });

  it("issues a single refresh for concurrent 401s", async () => {
    localStorage.setItem("access_token", "OLD");
    localStorage.setItem("refresh_token", "REFRESH");

    let calls = 0;
    const adapter: AxiosAdapter = (config) => {
      calls += 1;
      const isRetry = tokenOf(config.headers) === "Bearer NEW";
      if (!isRetry) {
        return Promise.reject({
          isAxiosError: true,
          config,
          response: { status: 401, data: {}, statusText: "", headers: {}, config },
        });
      }
      return Promise.resolve({
        data: { ok: true },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      });
    };

    const postSpy = vi.spyOn(axios, "post").mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(
            () => resolve({ data: { access_token: "NEW", refresh_token: "REFRESH2" } }),
            10,
          ),
        ),
    );

    const results = await Promise.all([
      apiClient.get("/a", { adapter }),
      apiClient.get("/b", { adapter }),
      apiClient.get("/c", { adapter }),
    ]);

    expect(results.every((r) => r.status === 200)).toBe(true);
    expect(postSpy).toHaveBeenCalledTimes(1); // shared in-flight refresh
    expect(calls).toBe(6); // 3 initial 401s + 3 retries
  });

  it("does not attempt refresh for the login endpoint", async () => {
    localStorage.setItem("refresh_token", "REFRESH");
    const postSpy = vi.spyOn(axios, "post");
    const adapter: AxiosAdapter = (config) =>
      Promise.reject({
        isAxiosError: true,
        config,
        response: { status: 401, data: { detail: "Invalid credentials" }, statusText: "", headers: {}, config },
      });

    await expect(
      apiClient.post("/auth/login", { email: "a@b.c", password: "x" }, { adapter }),
    ).rejects.toBeTruthy();
    expect(postSpy).not.toHaveBeenCalled();
  });
});


describe("apiClient empty id guard", () => {
  it("rejects a request with an empty path segment without sending it", async () => {
    const adapter = vi.fn() as unknown as AxiosAdapter;
    await expect(apiClient.post("/apps//entities", {}, { adapter })).rejects.toMatchObject({
      code: "ERR_MISSING_ID",
    });
    expect(adapter).not.toHaveBeenCalled();
  });

  it("lets a normal URL through", async () => {
    const adapter: AxiosAdapter = (config) =>
      Promise.resolve({ data: {}, status: 200, statusText: "OK", headers: {}, config });
    await expect(apiClient.get("/apps/abc/entities", { adapter })).resolves.toMatchObject({ status: 200 });
  });
});
