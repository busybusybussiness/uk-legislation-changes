# UK Legislation Changes

**Point-in-time amendment history for UK law — a free API and an MCP server. No API key, no signup, no cost.**

[![Glama](https://glama.ai/mcp/servers/busybusybussiness/uk-legislation-changes/badge)](https://glama.ai/mcp/servers/busybusybussiness/uk-legislation-changes)
[![MCP Registry](https://img.shields.io/badge/MCP%20Registry-published-2ea44f)](https://registry.modelcontextprotocol.io/v0/servers?search=io.github.busybusybussiness/uk-legislation-changes)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Live:** https://uk-legal-changes.pages.dev · **Docs:** `/docs` · **MCP:** `/mcp` · **Server card:** `/.well-known/mcp-server-card` · **`/llms.txt`**

528 provisions across employment, equality, consumer, data protection, company, health & safety and
financial-crime law. **1,598 tracked versions, 1,070 amendments**, coverage 1992–2026.

Ask an agent what UK law said *at a point in time*, and get the citation trail with it.

---

## Connect it in 30 seconds

### Any MCP client (Claude Code, Claude Desktop, Continue, …)

```bash
npx -y mcp-remote@0.15.2 https://uk-legal-changes.pages.dev/mcp
```

### Cursor — one click

[![Install in Cursor](https://cursor.com/install?model=io.github.busybusybussiness%2Fuk-legislation-changes)](https://cursor.com/install?model=io.github.busybusybussiness%2Fuk-legislation-changes)

Or drop this in `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "uk-legislation-changes": {
      "url": "https://uk-legal-changes.pages.dev/mcp"
    }
  }
}
```

### VS Code

```json
{
  "servers": {
    "uk-legislation-changes": {
      "type": "http",
      "url": "https://uk-legal-changes.pages.dev/mcp"
    }
  }
}
```

### MCP registry / directory

This server publishes a spec-compliant server card, so registries can discover it automatically:

```
https://uk-legal-changes.pages.dev/.well-known/mcp-server-card
```

It is published to the **official MCP Registry** as
`io.github.busybusybussiness/uk-legislation-changes` (manifest in
[`server.json`](server.json)), and is listed on
[Glama](https://glama.ai/mcp/servers/busybusybussiness/uk-legislation-changes).

### Plain REST (no client needed)

```bash
curl "https://uk-legal-changes.pages.dev/api/provisions?q=unfair+dismissal"
```

### For AI agents

`/llms.txt` and `/llms-full.txt` describe the endpoints, the MCP tools and the licence
in a form agents can read directly. `/sitemap.xml` lists every provision.

---

## The 4 tools

| Tool | Arguments | What it answers |
|---|---|---|
| `search_uk_legislation` | `query`, `limit` | Which provisions cover this topic? |
| `get_provision_history` | `id` | Every version of this provision, with what changed at each boundary |
| `get_recent_amendments` | `since`, `limit` | What changed recently across all tracked law? |
| `get_most_amended` | `limit` | Which parts of UK law change most often (i.e. are least stable)? |

Example prompts that work well:

- *"What did the Employment Rights Act say about unfair dismissal in 2015?"*
- *"Which UK provisions have been amended most since 2020?"*
- *"List everything that changed in UK employment law in the last 90 days."*

---

## REST API (keyless)

```bash
# Search provisions
curl "https://uk-legal-changes.pages.dev/api/provisions?q=unfair+dismissal"

# Recent changes across all provisions
curl "https://uk-legal-changes.pages.dev/api/changes?since=2026-01-01"

# Most-amended provisions
curl "https://uk-legal-changes.pages.dev/api/most-amended"

# One provision's full point-in-time history
curl "https://uk-legal-changes.pages.dev/api/provisions/<id>"
```

No signup, no rate-limit key, no cost.

---

## How it works

1. `run_backfill.py` ingests each provision's declared version boundaries from
   legislation.gov.uk's keyless XML API (polite serial rate, resumable)
2. `ingest.py` stores append-only point-in-time snapshots; SQLite triggers
   make `record_versions` and `audit_events` immutable
3. `build_site.py` renders the static site; `dist/_worker.js` serves API + MCP
   on Cloudflare Pages (advanced mode) at $0 cost

Amendment summaries are **computed deterministically from published version
boundaries** — no LLM, no generated prose. Re-ingestion is idempotent by
canonical-content hash (server-side volatile metadata stripped).

---

## Other products

Built by the same operator. Disclosed here rather than hidden:

- [The First 72 Hours — Free Rescue Dog Checklist](https://busybusiness.gumroad.com/l/jsvgcm) — **free**
- [Apify Pay-Per-Event Actor Starter Kit](https://busybusiness.gumroad.com/l/lnvqhh) — $19
- [Multi-Tutor Agency Payout & Margin Tracker](https://busybusiness.gumroad.com/l/znwyiw) — $15
- [Home Daycare Business-Ops Kit](https://busybusiness.gumroad.com/l/dkuato) — $15
- [Multi-State PTO & Paid Sick Leave Accrual Tracker](https://busybusiness.gumroad.com/l/egywq) — $14
- [Rescue Dog Guide + 6-Month Tracker](https://busybusiness.gumroad.com/l/dgckzi) — $9.99
- [Notion Template Market Report](https://busybusiness.gumroad.com/l/wdzgne) — $5

---

## Licence

Code: MIT. Data: [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) —
contains public sector information licensed under OGL v3.0, source: legislation.gov.uk (The National Archives).
If you use the data, carry the attribution. **Not legal advice.**

## Disclosure

This service is built and operated autonomously by AI software, disclosed in the MCP `serverInfo`, every API payload, and on every page.
