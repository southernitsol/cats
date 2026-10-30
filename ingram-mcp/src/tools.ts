import { z } from "zod";
import type { Config } from "./config.js";
import type { IngramClient } from "./client.js";

export interface ToolDef {
  name: string;
  description: string;
  schema: z.ZodRawShape;
  run: (client: IngramClient, cfg: Config, args: any) => Promise<unknown>;
}

const page = {
  pageNumber: z.number().int().min(1).default(1).describe("1-based page number"),
  pageSize: z.number().int().min(1).max(100).default(25).describe("Results per page"),
};

export const tools: ToolDef[] = [
  {
    name: "search_products",
    description:
      "Keyword search of the Ingram Micro catalog. Returns part numbers and descriptions only; call get_price_availability for pricing and stock.",
    schema: {
      keyword: z.string().min(1).describe("Search keywords, e.g. 'Cisco Catalyst 9200 48 port'"),
      vendor: z.string().optional().describe("Filter by vendor name"),
      ...page,
    },
    run: (c, cfg, a) =>
      c.request("GET", cfg.catalogPath, {
        query: { keyword: a.keyword, vendor: a.vendor, pageNumber: a.pageNumber, pageSize: a.pageSize },
      }),
  },
  {
    name: "get_product_details",
    description: "Full product details and specifications for one Ingram part number.",
    schema: { ingramPartNumber: z.string().min(1) },
    run: (c, cfg, a) => c.request("GET", `${cfg.catalogPath}/details/${encodeURIComponent(a.ingramPartNumber)}`),
  },
  {
    name: "get_price_availability",
    description: "Your reseller price and warehouse availability for up to 50 Ingram part numbers.",
    schema: {
      ingramPartNumbers: z.array(z.string().min(1)).min(1).max(50),
      includeAvailability: z.boolean().default(true),
      includePricing: z.boolean().default(true),
    },
    run: (c, cfg, a) =>
      c.request("POST", `${cfg.catalogPath}/priceandavailability`, {
        query: { includeAvailability: a.includeAvailability, includePricing: a.includePricing, includeProductAttributes: true },
        body: { products: a.ingramPartNumbers.map((ingramPartNumber: string) => ({ ingramPartNumber })) },
      }),
  },
  {
    name: "search_deals",
    description: "Search special-pricing deals (read-only). Filter by vendor, status or deal number.",
    schema: {
      dealId: z.string().optional(),
      vendorName: z.string().optional(),
      status: z.string().optional().describe("e.g. ACTIVE, EXPIRED"),
      ...page,
    },
    run: (c, cfg, a) =>
      a.dealId
        ? c.request("GET", `${cfg.dealsPath}/${encodeURIComponent(a.dealId)}`)
        : c.request("GET", cfg.dealsPath, {
            query: { vendorName: a.vendorName, status: a.status, pageNumber: a.pageNumber, pageSize: a.pageSize },
          }),
  },
  {
    name: "search_quotes",
    description: "Search existing quotes (read-only), or fetch one by quote number.",
    schema: {
      quoteNumber: z.string().optional(),
      status: z.string().optional(),
      ...page,
    },
    run: (c, cfg, a) =>
      a.quoteNumber
        ? c.request("GET", `${cfg.quotesPath}/${encodeURIComponent(a.quoteNumber)}`)
        : c.request("GET", cfg.quotesPath, {
            query: { status: a.status, pageNumber: a.pageNumber, pageSize: a.pageSize },
          }),
  },
];
