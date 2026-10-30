export interface Config {
  clientId: string;
  clientSecret: string;
  customerNumber: string;
  countryCode: string;
  baseUrl: string;
  tokenPath: string;
  catalogPath: string;
  dealsPath: string;
  quotesPath: string;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const missing = ["IM_CLIENT_ID", "IM_CLIENT_SECRET", "IM_CUSTOMER_NUMBER"].filter((k) => !env[k]);
  if (missing.length) {
    throw new Error(`Missing required environment variables: ${missing.join(", ")}`);
  }
  return {
    clientId: env.IM_CLIENT_ID!,
    clientSecret: env.IM_CLIENT_SECRET!,
    customerNumber: env.IM_CUSTOMER_NUMBER!,
    countryCode: env.IM_COUNTRY_CODE ?? "US",
    baseUrl: (env.IM_BASE_URL ?? "https://api.ingrammicro.com:443").replace(/\/+$/, ""),
    tokenPath: env.IM_TOKEN_PATH ?? "/oauth/oauth30/token",
    catalogPath: env.IM_CATALOG_PATH ?? "/resellers/v6/catalog",
    dealsPath: env.IM_DEALS_PATH ?? "/resellers/v6/deals",
    quotesPath: env.IM_QUOTES_PATH ?? "/resellers/v6/quotes",
  };
}
