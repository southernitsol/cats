// Live smoke test: keyword search, then price/availability for the top hits.
// Usage: IM_CLIENT_ID=... IM_CLIENT_SECRET=... IM_CUSTOMER_NUMBER=... npm run smoke -- "cisco catalyst 9200"
import { IngramClient, IngramError } from "../src/client.js";
import { loadConfig } from "../src/config.js";

const keyword = process.argv.slice(2).join(" ") || "cisco switch";
const cfg = loadConfig();
const client = new IngramClient(cfg);

try {
  const search: any = await client.request("GET", cfg.catalogPath, { query: { keyword, pageNumber: 1, pageSize: 5 } });
  const hits: any[] = search.catalog ?? search.products ?? [];
  console.log(`search "${keyword}": ${hits.length} hit(s)`);
  for (const h of hits) console.log(`  ${h.ingramPartNumber}  ${h.vendorName ?? ""}  ${h.description ?? ""}`);
  if (!hits.length) process.exit(1);

  const pna: any = await client.request("POST", `${cfg.catalogPath}/priceandavailability`, {
    query: { includeAvailability: true, includePricing: true },
    body: { products: hits.map((h) => ({ ingramPartNumber: h.ingramPartNumber })) },
  });
  for (const p of Array.isArray(pna) ? pna : pna.products ?? []) {
    const qty = p.availability?.totalAvailability ?? "n/a";
    const price = p.pricing?.customerPrice ?? "n/a";
    console.log(`  ${p.ingramPartNumber}: stock=${qty} price=${price}`);
  }
  console.log("smoke test passed");
} catch (e) {
  console.error(e instanceof IngramError ? `${e.message} [correlationId=${e.correlationId}]` : e);
  process.exit(1);
}
