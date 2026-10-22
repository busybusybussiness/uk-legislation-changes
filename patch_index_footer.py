"""Inject the connect/monetisation footer into an already-built dist/index.html.

pipeline.db is gitignored (it is the source of truth for a full rebuild), so on
machines that do not have it we cannot re-run build_site.py. The committed
dist/index.html was built from the database when it was available, so we patch
that artifact instead of regenerating it. Idempotent: re-running replaces the
existing footer rather than adding a second one.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
DIST = HERE / "dist"
MARK = '<div class="connect">'


def main() -> int:
    html_path = DIST / "index.html"
    page = html_path.read_text(encoding="utf-8")
    css = (HERE / "site_footer.css").read_text(encoding="utf-8")
    footer = (HERE / "site_footer.html").read_text(encoding="utf-8")

    # 1. drop any previous footer
    page = re.sub(r'\n?' + MARK + r'.*?</div>\n(?=</div></body></html>)', '\n', page, flags=re.S)
    # 2. append the footer CSS to the style block
    page = page.replace("</style>", css + "\n</style>", 1) if "site_footer" not in page else page
    # 3. insert the footer before the closing wrap div
    page = page.replace("</div></body></html>", footer + "</div></body></html>", 1)
    html_path.write_text(page, encoding="utf-8")

    # 4. carry the headline totals so /llms.txt can quote the real numbers
    dj = DIST / "data.json"
    if dj.exists():
        d = json.loads(dj.read_text(encoding="utf-8"))
        if "stats" not in d:
            m = re.search(r'<b>([0-9,]+)</b><span>provisions</span>.*?<b>([0-9,]+)</b><span>versions tracked</span>.*?<b>([0-9,]+)</b><span>amendments</span>', page, re.S)
            if m:
                d["stats"] = {"provisions": int(m.group(1).replace(",", "")),
                              "versions": int(m.group(2).replace(",", "")),
                              "amendments": int(m.group(3).replace(",", "")),
                              "coverage": "1992-2026"}
                dj.write_text(json.dumps(d, indent=1), encoding="utf-8")
                print(f"  data.json stats -> {d['stats']}")
    print(f"  footer injected into dist/index.html ({len(page):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
