# UK Legislation Changes - deploy state 2026-10-21T23:51:42-07:00

## LIVE (verified 2026-10-21)
- Apex: https://uk-legal-changes.pages.dev  (serverInfo 0.1.1, 13/13 verify_live.py checks)
- MCP:  https://uk-legal-changes.pages.dev/mcp  (4 tools, streamable http, 2024-11-05)
- Card: https://uk-legal-changes.pages.dev/.well-known/mcp-server-card  (v0.1.1, application/json, CORS *)
- Also: /docs, /llms.txt, /api/provisions  -> all 200
- 528 provisions | 1,598 versions | 1,070 amendments | 1992-2026

## PAGES PROJECT
- project: uk-legal-changes   domain: uk-legal-changes.pages.dev   Git Provider: No
- PRODUCTION branch = main. Our git branch = master.
  => deploy.sh now passes `--branch ${DEPLOY_BRANCH:-main}` (was silently Preview-only)
- prod deployment id 65ae91e3-6bde-4dcb-9363-7b45bcf4b964 (build 098d5b0)

## GITHUB (needs Owner push consent)
- repo: https://github.com/busybusybussiness/uk-legislation-changes  (public, gh authed as busybusybussiness)
- 4 local commits not pushed: card endpoint + deploy fix + README refresh + install configs
- README.md rewritten: current numbers (528/1,598/1,070), one-click Cursor button,
  .cursor/mcp.json + .vscode/mcp.json added, 4 tools documented, API examples, products listed
- expired LAUNCH20 coupon removed from copy (it said "valid until 2026-10-20")
- duplicate extensionless README deleted (GitHub renders README.md, so the product links were invisible)
- glama.json enriched (version, description, websiteUrl, remotes)
