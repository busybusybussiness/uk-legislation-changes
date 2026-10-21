"""Post-deploy verification. Runs against the LIVE url over plain HTTP.

Replaces the browser screenshot step (the browser backend is unavailable).
Checks the things that actually matter legally and functionally:
OGL attribution is the licence condition for using this data commercially.
"""
import sys
import re
import time
import urllib.request
import urllib.error

UA = "uk-legal-history-pipeline/0.1 (post-deploy verification)"


def fetch(url, tries=6):
    """Pages deploys propagate in a few seconds; retry briefly."""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3)
    raise SystemExit(f"could not reach {url}: {last!r}")


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://uk-legal-changes.pages.dev"
    status, html = fetch(url)
    cards = html.count('class="card"')

    checks = {
        "reachable (HTTP 200)": status == 200,
        "OGL attribution present": "Open Government Licence" in html,
        "attribution links to the licence":
            "nationalarchives.gov.uk/doc/open-government-licence" in html,
        "source credited (legislation.gov.uk)": "legislation.gov.uk" in html,
        "'no generated prose' disclosure": "no generated prose" in html.lower(),
        "provision cards rendered (>=10)": cards >= 10,
        "no placeholder text": "lorem" not in html.lower(),
        "external links use noopener": html.count("noopener") >= 2,
    }

    # --- the MCP endpoint and the server card must both survive a deploy ---
    try:
        st, body = fetch(url.rstrip("/") + "/mcp")
        checks["MCP endpoint reachable"] = st == 200
        checks["MCP lists its 4 tools"] = all(
            t in body for t in (
                "search_uk_legislation", "get_provision_history",
                "get_recent_amendments", "get_most_amended"))
    except Exception as e:  # noqa: BLE001
        checks["MCP endpoint reachable"] = False
        print(f"  (MCP check errored: {e!r})")

    try:
        st, body = fetch(url.rstrip("/") + "/.well-known/mcp-server-card")
        checks["server card reachable"] = st == 200
        checks["server card is JSON"] = body.lstrip().startswith("{")
        checks["server card names the server"] = "uk-legislation-changes" in body
    except Exception as e:  # noqa: BLE001
        checks["server card reachable"] = False
        print(f"  (server card check errored: {e!r})")

    print(f"\n  {url}  ({len(html)} bytes, {cards} cards)\n")
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")

    failed = [k for k, v in checks.items() if not v]
    print()
    if failed:
        print(f"  {len(failed)} CHECK(S) FAILED — do not share the link yet.")
        return 1
    print(f"  {len(checks)}/{len(checks)} passed. Safe to share.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
