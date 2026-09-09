/**
 * UK Legislation Change API + MCP server.
 *
 * MASTER-PROMPT-V2 compliance:
 *   §11  machine customers: MCP server + agent-callable API from day 1
 *   §19  AI disclosure: every response and the MCP serverInfo declare AI operation
 *   §14  provenance: every record carries source URL, licence, retrieval date
 *   §23  licence terms enforced as data and surfaced in every payload
 *   §31  deterministic: no LLM in the serving path
 *
 * Distribution rationale: the operator has no audience. Human channels compound
 * on a following that does not exist; agent channels do not care. This is the
 * primary acquisition surface, not an add-on.
 */

const DISCLOSURE =
  "This service is operated autonomously by AI software. Data is derived from " +
  "legislation.gov.uk under the Open Government Licence v3.0. Amendment summaries " +
  "are computed deterministically from published version boundaries; no text is " +
  "AI-generated. Not legal advice.";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Mcp-Session-Id, Mcp-Protocol-Version",
  "Access-Control-Expose-Headers": "Mcp-Session-Id",
};

let DATA = null;
async function load(env) {
  if (DATA) return DATA;
  const res = await env.ASSETS.fetch(new Request("https://internal/data.json"));
  DATA = await res.json();
  return DATA;
}

const json = (body, status = 200, extra = {}) =>
  new Response(JSON.stringify(body, null, 2), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS, ...extra },
  });

// ----------------------------------------------------------------- helpers
function searchProvisions(data, query, limit = 20) {
  const q = (query || "").toLowerCase().trim();
  if (!q) return data.records.slice(0, limit);
  const terms = q.split(/\s+/);
  const scored = [];
  for (const r of data.records) {
    const hay = (r.title + " " + r.id).toLowerCase();
    let score = 0;
    for (const t of terms) if (hay.includes(t)) score += t.length;
    if (hay.includes(q)) score += 25;
    if (score > 0) scored.push([score, r]);
  }
  scored.sort((a, b) => b[0] - a[0]);
  return scored.slice(0, limit).map((x) => x[1]);
}

function slim(r) {
  return {
    id: r.id,
    title: r.title,
    section: r.section,
    version_count: r.versions.length,
    first_version: r.versions[0],
    latest_version: r.versions[r.versions.length - 1],
    amendment_count: r.changes.filter((c) => c.type === "AMENDED").length,
    latest_change: r.changes.length ? r.changes[r.changes.length - 1] : null,
    source_url: r.url,
  };
}

function recentChanges(data, since, limit = 50) {
  const out = [];
  for (const r of data.records)
    for (const c of r.changes)
      if (c.type === "AMENDED" && (!since || c.date >= since))
        out.push({ provision_id: r.id, title: r.title, source_url: r.url, ...c });
  out.sort((a, b) => (a.date < b.date ? 1 : -1));
  return out.slice(0, limit);
}

// ----------------------------------------------------------------- MCP
const TOOLS = [
  {
    name: "search_uk_legislation",
    description:
      "Search UK legislation provisions (employment, equality, consumer, data protection, " +
      "company, health & safety law) by keyword. Returns provisions with their amendment history.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Keywords, e.g. 'unfair dismissal' or 'disability'" },
        limit: { type: "number", description: "Max results (default 20)" },
      },
      required: ["query"],
    },
  },
  {
    name: "get_provision_history",
    description:
      "Get the full point-in-time amendment history for one provision: every version " +
      "boundary date and what changed at each.",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Provision id, e.g. 'ukpga/1996/18/section/94'" },
      },
      required: ["id"],
    },
  },
  {
    name: "get_recent_amendments",
    description:
      "List the most recent amendments across all tracked UK provisions. Useful for " +
      "answering 'what changed in UK employment law recently?'",
    inputSchema: {
      type: "object",
      properties: {
        since: { type: "string", description: "ISO date, e.g. '2026-01-01'" },
        limit: { type: "number", description: "Max results (default 50)" },
      },
    },
  },
  {
    name: "get_most_amended",
    description:
      "List the provisions that have changed most often — the least stable areas of UK law.",
    inputSchema: {
      type: "object",
      properties: { limit: { type: "number", description: "Max results (default 20)" } },
    },
  },
];

function callTool(data, name, args) {
  const a = args || {};
  if (name === "search_uk_legislation") {
    const hits = searchProvisions(data, a.query, a.limit || 20);
    return {
      query: a.query,
      result_count: hits.length,
      results: hits.map(slim),
      attribution: data.attribution.attribution_text,
      disclosure: DISCLOSURE,
    };
  }
  if (name === "get_provision_history") {
    const r = data.records.find((x) => x.id === a.id);
    if (!r) return { error: "not_found", id: a.id };
    return {
      ...slim(r),
      versions: r.versions,
      changes: r.changes,
      attribution: data.attribution.attribution_text,
      disclosure: DISCLOSURE,
    };
  }
  if (name === "get_recent_amendments") {
    const ch = recentChanges(data, a.since, a.limit || 50);
    return {
      since: a.since || "all time",
      result_count: ch.length,
      amendments: ch,
      attribution: data.attribution.attribution_text,
      disclosure: DISCLOSURE,
    };
  }
  if (name === "get_most_amended") {
    const rs = [...data.records]
      .sort((x, y) => y.versions.length - x.versions.length)
      .slice(0, a.limit || 20);
    return {
      result_count: rs.length,
      provisions: rs.map(slim),
      attribution: data.attribution.attribution_text,
      disclosure: DISCLOSURE,
    };
  }
  return { error: "unknown_tool", name };
}

async function handleMcp(request, env) {
  let msg;
  try {
    msg = await request.json();
  } catch {
    return json({ jsonrpc: "2.0", error: { code: -32700, message: "Parse error" }, id: null }, 400);
  }
  const data = await load(env);
  const { method, id } = msg;
  console.log(JSON.stringify({ evt: "mcp", method, tool: msg.params?.name || null,
                               ts: new Date().toISOString() }));
  const reply = (result) => json({ jsonrpc: "2.0", id, result });

  if (method === "initialize")
    return reply({
      protocolVersion: "2024-11-05",
      capabilities: { tools: {} },
      serverInfo: {
        name: "uk-legislation-changes",
        version: "0.1.0",
        description:
          "Point-in-time amendment history for UK legislation. " +
          "AI-operated service; data under OGL v3.0. " + DISCLOSURE,
      },
    });

  if (method === "notifications/initialized") return new Response(null, { status: 202, headers: CORS });
  if (method === "tools/list") return reply({ tools: TOOLS });
  if (method === "tools/call") {
    const out = callTool(data, msg.params?.name, msg.params?.arguments);
    return reply({ content: [{ type: "text", text: JSON.stringify(out, null, 2) }] });
  }
  if (method === "ping") return reply({});
  return json({ jsonrpc: "2.0", id, error: { code: -32601, message: "Method not found: " + method } }, 404);
}

// ----------------------------------------------------------------- router
/**
 * Minimal, privacy-preserving telemetry (§21: collect nothing you don't need).
 * Logs ONLY: path, whether it looked like an agent, and the MCP method.
 * No IP, no user identifier, no query contents, no cookies, no storage.
 * Visible via: wrangler pages deployment tail
 */
function classify(request) {
  const ua = (request.headers.get("user-agent") || "").toLowerCase();
  const agentish = /claude|gpt|openai|anthropic|mcp|langchain|llamaindex|cursor|cline|agent|bot|python-requests|httpx|node-fetch|curl/.test(ua);
  return agentish ? "machine" : "browser";
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    const client = classify(request);
    if (path === "/mcp" || path.startsWith("/api")) {
      console.log(JSON.stringify({ evt: "call", path, client, ts: new Date().toISOString() }));
    }

    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });

    if (path === "/mcp") {
      if (request.method === "POST") return handleMcp(request, env);
      return json({
        service: "uk-legislation-changes MCP server",
        transport: "streamable-http",
        usage: "POST JSON-RPC 2.0 to this endpoint",
        tools: TOOLS.map((t) => t.name),
        disclosure: DISCLOSURE,
      });
    }

    if (path === "/api" || path === "/api/") {
      const data = await load(env);
      return json({
        service: "UK Legislation Change API",
        description: "Point-in-time amendment history for UK legislation.",
        disclosure: DISCLOSURE,
        licence: data.attribution.license_id,
        licence_url: data.attribution.license_url,
        attribution_required: data.attribution.attribution_text,
        provisions: data.records.length,
        generated: data.generated,
        endpoints: {
          "GET /api/provisions?q=&limit=": "search provisions",
          "GET /api/provisions/{act}/section/{n}": "one provision with full history",
          "GET /api/changes?since=YYYY-MM-DD&limit=": "recent amendments",
          "GET /api/most-amended?limit=": "least stable provisions",
          "POST /mcp": "Model Context Protocol endpoint for AI agents",
        },
        mcp_endpoint: url.origin + "/mcp",
      });
    }

    if (path.startsWith("/api/provisions")) {
      const data = await load(env);
      const rest = path.slice("/api/provisions".length).replace(/^\//, "");
      if (rest) {
        const r = data.records.find((x) => x.id === rest);
        if (!r) return json({ error: "not_found", id: rest }, 404);
        return json({ ...slim(r), versions: r.versions, changes: r.changes,
                      attribution: data.attribution.attribution_text, disclosure: DISCLOSURE });
      }
      const q = url.searchParams.get("q") || "";
      const limit = Math.min(parseInt(url.searchParams.get("limit") || "20", 10), 200);
      const hits = searchProvisions(data, q, limit);
      return json({ query: q, result_count: hits.length, results: hits.map(slim),
                    attribution: data.attribution.attribution_text, disclosure: DISCLOSURE });
    }

    if (path === "/api/changes") {
      const data = await load(env);
      const since = url.searchParams.get("since");
      const limit = Math.min(parseInt(url.searchParams.get("limit") || "50", 10), 500);
      const ch = recentChanges(data, since, limit);
      return json({ since: since || "all time", result_count: ch.length, amendments: ch,
                    attribution: data.attribution.attribution_text, disclosure: DISCLOSURE });
    }

    if (path === "/api/most-amended") {
      const data = await load(env);
      const limit = Math.min(parseInt(url.searchParams.get("limit") || "20", 10), 200);
      const rs = [...data.records].sort((a, b) => b.versions.length - a.versions.length).slice(0, limit);
      return json({ result_count: rs.length, provisions: rs.map(slim),
                    attribution: data.attribution.attribution_text, disclosure: DISCLOSURE });
    }

    if (path === "/llms.txt") {
      const data = await load(env);
      return new Response(
        `# UK Legislation Change API\n\n` +
          `> Point-in-time amendment history for ${data.records.length} provisions of UK law.\n\n` +
          `${DISCLOSURE}\n\n` +
          `## API\n- GET /api — service description\n- GET /api/provisions?q= — search\n` +
          `- GET /api/changes?since= — recent amendments\n- POST /mcp — MCP endpoint for agents\n\n` +
          `## Licence\n${data.attribution.attribution_text}\n${data.attribution.license_url}\n`,
        { headers: { "Content-Type": "text/plain; charset=utf-8", ...CORS } }
      );
    }

    return env.ASSETS.fetch(request);
  },
};
