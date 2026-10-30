#!/usr/bin/env node
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { IngramClient, IngramError } from "./client.js";
import { loadConfig } from "./config.js";
import { tools } from "./tools.js";

const cfg = loadConfig();
const client = new IngramClient(cfg);
const server = new McpServer({ name: "ingram-mcp", version: "0.1.0" });

for (const t of tools) {
  server.tool(t.name, t.description, t.schema, { readOnlyHint: true, openWorldHint: true }, async (args) => {
    try {
      const data = await t.run(client, cfg, z.object(t.schema).parse(args));
      return { content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }] };
    } catch (e) {
      const msg = e instanceof IngramError ? `${e.message} [correlationId=${e.correlationId}]` : String(e);
      return { isError: true, content: [{ type: "text" as const, text: msg }] };
    }
  });
}

// stdout is the MCP channel; log to stderr only.
await server.connect(new StdioServerTransport());
console.error("ingram-mcp ready");
