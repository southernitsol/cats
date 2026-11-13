# ingram-mcp

Read-only MCP server for Ingram Micro (Xvantage Reseller API): product search, price/availability, deals and quotes, for bid preparation.

## Tools
| Tool | Endpoint |
|---|---|
| `search_products` | `GET /resellers/v6/catalog` |
| `get_product_details` | `GET /resellers/v6/catalog/details/{ingramPartNumber}` |
| `get_price_availability` | `POST /resellers/v6/catalog/priceandavailability` |
| `search_deals` | `GET /resellers/v6/deals[/{id}]` |
| `search_quotes` | `GET /resellers/v6/quotes[/{number}]` |

Paths are overridable via `IM_*_PATH` env vars. **Verify deals/quotes paths and versions against developer.ingrammicro.com**, as they were written without live API access. Make sure the portal app is subscribed to the matching API products.

## Setup
```bash
npm install && npm run build
```
Credentials come from environment variables only (see `.env.example`). Never commit them.

## Claude Desktop / Claude Code config
```json
{
  "mcpServers": {
    "ingram": {
      "command": "node",
      "args": ["/absolute/path/to/ingram-mcp/dist/index.js"],
      "env": {
        "IM_CLIENT_ID": "...",
        "IM_CLIENT_SECRET": "...",
        "IM_CUSTOMER_NUMBER": "70-211892",
        "IM_COUNTRY_CODE": "US"
      }
    }
  }
}
```

## Behavior
OAuth2 client-credentials token cached until ~1 min before expiry (single in-flight refresh), one refresh-and-retry on 401, exponential backoff on 429/5xx (honors `Retry-After`), unique `IM-CorrelationID` per request echoed in errors.
