# Registry Submissions — ready to file

Everything below is prepared, schema-validated, and verified against each
venue's current published requirements (checked 2026-09-09).

**Live endpoints**
- Site: https://uk-legal-changes.pages.dev
- Docs: https://uk-legal-changes.pages.dev/docs
- MCP: https://uk-legal-changes.pages.dev/mcp
- API: https://uk-legal-changes.pages.dev/api

---

## Why registries, not social posts

The operator has no audience. Every human channel — content, community, social —
compounds on a following that does not exist. Directory and registry listings do
not: submitting is the expected behaviour of the venue, not an intrusion. And an
AI agent consuming an MCP server never checks a follower count.

This is §11 ("the fastest-growing buyer of an API is another agent") used as an
*acquisition* channel rather than a monetisation one.

---

## 1. Official MCP Registry — NEEDS YOUR GITHUB

`server.json` is written and **passes schema validation** against
`https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json`.

```json
{
  "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
  "name": "dev.uk-legal-changes/uk-legislation-changes",
  "title": "UK Legislation Changes",
  "description": "Point-in-time amendment history for 506 UK legislation provisions.",
  "version": "0.1.0",
  "websiteUrl": "https://uk-legal-changes.pages.dev",
  "remotes": [
    { "type": "streamable-http", "url": "https://uk-legal-changes.pages.dev/mcp" }
  ]
}
```

**Why this needs you:** publishing authenticates via `mcp-publisher login github`.
Account ownership is identity proofing — §5 human-only act #1. I will not
create or operate an account in your name.

**Steps (~5 min):**
```bash
# 1. install the publisher CLI (see registry docs for your platform)
# 2. from the registry/ directory:
mcp-publisher login github
mcp-publisher validate      # should pass; already schema-checked
mcp-publisher publish
```

Note: 19 of 20 servers sampled from the live registry are remote-only with zero
packages, so our architecture (no npm package, hosted endpoint) is normal and
supported.

---

## 2. `public-apis/public-apis` — 478k stars

Their CONTRIBUTING.md explicitly rejects marketing:

> *"Pull requests that are identified as marketing attempts will not be accepted.
> Please make sure the API you want to add has full, free access..."*

**We qualify legitimately:** keyless, no signup, no paid tier, no upsell.
This is the kind of entry the list exists for.

Entry for `README.md`, Government section, alphabetical:

```
| UK Legislation Changes | Point-in-time amendment history for UK law | No | Yes | Yes |
```

Link: `https://uk-legal-changes.pages.dev/docs`

---

## 3. `punkpeye/awesome-mcp-servers` — 94.7k stars

```markdown
- [UK Legislation Changes](https://uk-legal-changes.pages.dev/docs) - Point-in-time
  amendment history for UK employment, equality, consumer, data protection and
  company law. Keyless, OGL v3.0.
```

## 4. `wong2/awesome-mcp-servers` — 4.3k stars

Same entry format.

## 5. `modelcontextprotocol/servers` — 90.2k stars

Community servers section, same entry.

---

## Directories to submit via web form (no GitHub needed)

| Venue | Status |
|---|---|
| mcpservers.org | reachable, community list |
| Glama MCP directory | reachable |
| Smithery | reachable |
| PulseMCP | intermittent at check time |

---

## Compliance carried into every listing

- **AI disclosure** (§19) — in `serverInfo`, every API payload, and the docs page
- **OGL attribution** (§23) — in every response and on every surface
- **"No generated prose"** — stated explicitly; summaries are deterministic
- **Not legal advice** — stated on the docs page

---

## What this measures

The revised kill test: **≥3 registry listings AND ≥1 real agent call in 30 days.**

That tests whether machines discover and use it — the actual thesis — rather
than testing the operator's reach, which the original test would have done and
failed for the wrong reason.
