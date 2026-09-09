"""Build the static site from the database. Deterministic, no LLM."""
import html
import json
import os
import sqlite3
from pathlib import Path

HERE = Path(__file__).parent
DB = HERE / "pipeline.db"
DIST = HERE / "dist"
MAX_CARDS = 120


def main() -> int:
    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    recs = []
    for r in conn.execute(
        """SELECT rec.id, rec.title, rec.uri FROM records rec
           JOIN record_versions v ON v.record_id = rec.id
           GROUP BY rec.id HAVING COUNT(v.id) >= 2"""
    ):
        changes = [dict(x) for x in conn.execute(
            """SELECT change_date, change_type, summary FROM record_changes
               WHERE record_id=? ORDER BY change_date""", (r["id"],))]
        versions = [x[0] for x in conn.execute(
            "SELECT valid_from FROM record_versions WHERE record_id=? ORDER BY valid_from",
            (r["id"],))]
        if changes:
            recs.append({"id": r["id"], "title": r["title"], "uri": r["uri"],
                         "changes": changes, "versions": versions})

    src = dict(conn.execute("SELECT attribution_text, license_url FROM sources").fetchone())
    tot_v = conn.execute("SELECT COUNT(*) FROM record_versions").fetchone()[0]
    tot_a = conn.execute(
        "SELECT COUNT(*) FROM record_changes WHERE change_type='AMENDED'").fetchone()[0]
    tot_r = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    rng = conn.execute(
        "SELECT MIN(valid_from) a, MAX(valid_from) b FROM record_versions").fetchone()
    conn.close()

    recs.sort(key=lambda x: x["changes"][-1]["change_date"], reverse=True)
    show = recs[:MAX_CARDS]

    cards = []
    for r in show:
        last = r["changes"][-1]
        dots = "".join(
            '<span class="dot%s" title="%s"></span>'
            % (" amd" if c["change_type"] == "AMENDED" else "", html.escape(c["summary"]))
            for c in r["changes"])
        cards.append(
            '<article class="card">'
            f'<div class="chead"><h3>{html.escape(r["title"])}</h3>'
            f'<span class="badge">{len(r["versions"])} versions</span></div>'
            f'<div class="track">{dots}</div>'
            f'<div class="range"><span>{r["versions"][0]}</span>'
            f'<span>{r["versions"][-1]}</span></div>'
            f'<p class="latest"><strong>Latest change {last["change_date"]}:</strong> '
            f'{html.escape(last["summary"])}</p>'
            f'<a class="src" href="{r["uri"].replace("/data.xml", "")}" target="_blank" '
            'rel="noopener">View on legislation.gov.uk &rarr;</a></article>')

    style = (HERE / "style.css").read_text(encoding="utf-8")
    page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>UK legislation — what changed, and when</title>
<meta name="description" content="Point-in-time amendment history for {tot_r} provisions of UK employment, equality, consumer, data protection and company law. Computed from the official record under OGL v3.">
<style>{style}</style></head><body><div class="wrap">
<h2>UK legislation — what changed, and when</h2>
<p class="sub">Point-in-time amendment history, computed from the official record.</p>
<div class="stats">
 <div class="stat"><b>{tot_r}</b><span>provisions</span></div>
 <div class="stat"><b>{tot_v:,}</b><span>versions tracked</span></div>
 <div class="stat"><b>{tot_a:,}</b><span>amendments</span></div>
 <div class="stat"><b>{rng['a'][:4]}&ndash;{rng['b'][:4]}</b><span>coverage</span></div>
</div>
<p class="showing">Showing the {len(show)} most recently amended provisions.</p>
{''.join(cards)}
<p class="attr">{html.escape(src['attribution_text'])}<br>
Licensed under the <a href="{src['license_url']}" target="_blank" rel="noopener">Open Government Licence v3.0</a>.
Amendment summaries are computed deterministically from published version boundaries; no generated prose.</p>
</div></body></html>"""

    DIST.mkdir(exist_ok=True)
    (DIST / "index.html").write_text(page, encoding="utf-8")
    json.dump({"records": recs, "attribution": src},
              open(DIST / "data.json", "w", encoding="utf-8"), indent=1)
    print(f"  built dist/index.html — {len(page):,} bytes, {len(show)} cards")
    print(f"  {tot_r} provisions | {tot_v:,} versions | {tot_a:,} amendments")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
