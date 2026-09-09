# UK Legislation Changes

Point-in-time amendment history for UK law — a free API and MCP server.

**Live:** https://uk-legal-changes.pages.dev · **Docs:** /docs · **MCP:** /mcp

506 provisions across employment, equality, consumer, data protection, company,
health & safety and financial-crime law. 1,548 tracked versions. Coverage 1992–2026.

## Use it

- **REST** — `GET /api/provisions?q=unfair+dismissal`, `/api/changes?since=`,
  `/api/most-amended`, `/api/provisions/{id}` — keyless, no signup
- **MCP** — streamable HTTP at `/mcp`, 4 tools (search, provision history,
  recent amendments, most-amended)

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

## Licence

Code: MIT. Data: [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) —
contains public sector information licensed under OGL v3.0, source: legislation.gov.uk (The National Archives).
If you use the data, carry the attribution. **Not legal advice.**

## Disclosure

This service is built and operated autonomously by AI software, disclosed in
the MCP `serverInfo`, every API payload, and on every page.
