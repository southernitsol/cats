import { randomUUID } from "node:crypto";
import type { Config } from "./config.js";

type Query = Record<string, string | number | boolean | undefined>;

export class IngramError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly correlationId: string,
  ) {
    super(message);
  }
}

const MAX_RETRIES = 3;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export class IngramClient {
  private token?: { value: string; expiresAt: number };
  private tokenInflight?: Promise<string>;

  constructor(
    private readonly cfg: Config,
    private readonly fetchImpl: typeof fetch = fetch,
  ) {}

  private async fetchToken(): Promise<string> {
    const res = await this.fetchImpl(this.cfg.baseUrl.replace(/\/sandbox$/, "") + this.cfg.tokenPath, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "client_credentials",
        client_id: this.cfg.clientId,
        client_secret: this.cfg.clientSecret,
      }),
    });
    if (!res.ok) {
      const detail = (await res.text()).slice(0, 300);
      throw new IngramError(`Token request failed (${res.status}): ${detail}. Check credentials and that the app is approved.`, res.status, "n/a");
    }
    const json = (await res.json()) as { access_token: string; expires_in?: string | number };
    const ttl = Number(json.expires_in ?? 3600);
    // Refresh a minute early so in-flight calls never carry an expired token.
    this.token = { value: json.access_token, expiresAt: Date.now() + Math.max(ttl - 60, 30) * 1000 };
    return json.access_token;
  }

  private async getToken(force = false): Promise<string> {
    if (!force && this.token && Date.now() < this.token.expiresAt) return this.token.value;
    // Share a single in-flight refresh across concurrent callers.
    this.tokenInflight ??= this.fetchToken().finally(() => (this.tokenInflight = undefined));
    return this.tokenInflight;
  }

  async request<T>(method: "GET" | "POST", path: string, opts: { query?: Query; body?: unknown } = {}): Promise<T> {
    const url = new URL(this.cfg.baseUrl + path);
    for (const [k, v] of Object.entries(opts.query ?? {})) {
      if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
    }
    let refreshed = false;
    for (let attempt = 0; ; attempt++) {
      const correlationId = randomUUID().replace(/-/g, "").slice(0, 32);
      const res = await this.fetchImpl(url, {
        method,
        headers: {
          Authorization: `Bearer ${await this.getToken()}`,
          "IM-CustomerNumber": this.cfg.customerNumber,
          "IM-CountryCode": this.cfg.countryCode,
          "IM-CorrelationID": correlationId,
          Accept: "application/json",
          ...(opts.body ? { "Content-Type": "application/json" } : {}),
        },
        body: opts.body ? JSON.stringify(opts.body) : undefined,
      });
      if (res.ok) return (await res.json()) as T;

      if (res.status === 401 && !refreshed) {
        refreshed = true;
        await this.getToken(true);
        continue;
      }
      if ((res.status === 429 || res.status >= 500) && attempt < MAX_RETRIES) {
        const retryAfter = Number(res.headers.get("retry-after"));
        await sleep(retryAfter > 0 ? retryAfter * 1000 : 500 * 2 ** attempt);
        continue;
      }
      const detail = (await res.text()).slice(0, 500);
      throw new IngramError(`Ingram API ${method} ${path} failed (${res.status}): ${detail}`, res.status, correlationId);
    }
  }
}
