import { describe, expect, it, vi } from "vitest";
import { IngramClient, IngramError } from "./client.js";
import type { Config } from "./config.js";

const cfg: Config = {
  clientId: "id", clientSecret: "secret", customerNumber: "70-211892", countryCode: "US",
  baseUrl: "https://api.test", tokenPath: "/oauth/token", catalogPath: "/cat", dealsPath: "/deals", quotesPath: "/quotes",
};
const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers });
const tokenRes = () => json({ access_token: "tok", expires_in: "3600" });

describe("IngramClient", () => {
  it("fetches a token once, caches it, and sends required headers", async () => {
    const f = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(tokenRes())
      .mockImplementation(async () => json({ ok: 1 }));
    const c = new IngramClient(cfg, f);
    await c.request("GET", "/cat", { query: { keyword: "switch", vendor: undefined } });
    await c.request("GET", "/cat");
    expect(f).toHaveBeenCalledTimes(3); // 1 token + 2 calls
    const [url, init] = f.mock.calls[1];
    expect(String(url)).toBe("https://api.test/cat?keyword=switch");
    const h = (init as RequestInit).headers as Record<string, string>;
    expect(h.Authorization).toBe("Bearer tok");
    expect(h["IM-CustomerNumber"]).toBe("70-211892");
    expect(h["IM-CountryCode"]).toBe("US");
    expect(h["IM-CorrelationID"]).toMatch(/^[0-9a-f]{32}$/);
  });

  it("shares one token request across concurrent calls", async () => {
    const f = vi.fn<typeof fetch>().mockImplementation(async (u) =>
      String(u).includes("/oauth/token") ? tokenRes() : json({ ok: 1 }));
    const c = new IngramClient(cfg, f);
    await Promise.all([c.request("GET", "/a"), c.request("GET", "/b"), c.request("GET", "/c")]);
    expect(f.mock.calls.filter(([u]) => String(u).includes("/oauth/token"))).toHaveLength(1);
  });

  it("refreshes the token once on 401 and retries", async () => {
    const f = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(tokenRes())
      .mockResolvedValueOnce(json({}, 401))
      .mockResolvedValueOnce(tokenRes())
      .mockResolvedValueOnce(json({ ok: 1 }));
    expect(await new IngramClient(cfg, f).request("GET", "/x")).toEqual({ ok: 1 });
  });

  it("retries 429 honoring Retry-After, then succeeds", async () => {
    const f = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(tokenRes())
      .mockResolvedValueOnce(json({}, 429, { "retry-after": "0.01" }))
      .mockResolvedValueOnce(json({ ok: 1 }));
    expect(await new IngramClient(cfg, f).request("GET", "/x")).toEqual({ ok: 1 });
  });

  it("throws IngramError with correlation id on non-retryable failure", async () => {
    const f = vi.fn<typeof fetch>().mockResolvedValueOnce(tokenRes()).mockResolvedValueOnce(json({ e: "nope" }, 403));
    await expect(new IngramClient(cfg, f).request("GET", "/x")).rejects.toMatchObject({
      status: 403,
      correlationId: expect.stringMatching(/^[0-9a-f]{32}$/),
    });
    expect(IngramError).toBeDefined();
  });
});
