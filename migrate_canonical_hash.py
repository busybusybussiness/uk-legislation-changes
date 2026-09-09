"""One-off migration: rewrite content_hash to canonical identity.

WHY: legislation.gov.uk emits <ukm:UnappliedEffects> containing a
Modified="<timestamp>" attribute whose attribute ORDER also varies between
requests. Hashing raw XML therefore produced a different hash for identical
legal text on every fetch, so re-ingestion appended near-duplicate versions
forever and idempotency silently failed.

This migration:
  1. drops the append-only triggers (explicitly, with an audit record),
  2. rewrites every content_hash to canonical form,
  3. collapses rows that are now provably identical,
  4. restores the triggers.

Run once:  python migrate_canonical_hash.py
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ingest import content_identity, utcnow  # noqa: E402

DB = Path(__file__).parent / "pipeline.db"


def main() -> int:
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("DROP TRIGGER IF EXISTS no_update_versions")
        conn.execute("DROP TRIGGER IF EXISTS no_delete_versions")

        # PASS 1 — collapse rows that are identical under CANONICAL identity.
        # Must happen BEFORE rehashing: once two rows share a canonical hash the
        # UNIQUE(record_id, valid_from, content_hash) index would reject the update.
        rows = conn.execute(
            "SELECT id, record_id, valid_from, content FROM record_versions ORDER BY id"
        ).fetchall()
        best: dict[tuple[str, str, str], int] = {}
        victims: list[int] = []
        canon: dict[int, str] = {}
        for r in rows:
            h = content_identity(r["content"])
            canon[r["id"]] = h
            key = (r["record_id"], r["valid_from"], h)
            if key in best:
                victims.append(r["id"])
            else:
                best[key] = r["id"]

        removed = 0
        if victims:
            ids = ",".join(map(str, victims))
            conn.execute(
                f"DELETE FROM record_changes WHERE to_version IN ({ids}) OR from_version IN ({ids})"
            )
            conn.execute(f"DELETE FROM record_versions WHERE id IN ({ids})")
            removed = len(victims)
        print(f"  collapsed {removed} duplicate rows (canonical identity)")

        # PASS 2 — now every surviving row has a unique canonical key; safe to rewrite.
        changed = 0
        for vid, h in canon.items():
            if vid in set(victims):
                continue
            cur = conn.execute(
                "SELECT content_hash FROM record_versions WHERE id=?", (vid,)
            ).fetchone()
            if cur and cur[0] != h:
                conn.execute("UPDATE record_versions SET content_hash=? WHERE id=?", (h, vid))
                changed += 1
        print(f"  rehashed {changed} of {len(rows) - removed} surviving rows")

        conn.execute(
            """CREATE TRIGGER no_update_versions BEFORE UPDATE ON record_versions
               BEGIN SELECT RAISE(ABORT,'record_versions is append-only'); END"""
        )
        conn.execute(
            """CREATE TRIGGER no_delete_versions BEFORE DELETE ON record_versions
               BEGIN SELECT RAISE(ABORT,'record_versions is append-only'); END"""
        )
        conn.execute(
            """INSERT INTO audit_events(occurred_at,actor,action,subject,severity,detail)
               VALUES(?,?,?,?,?,?)""",
            (utcnow(), "maintenance-migration", "rehash_canonical_identity",
             "record_versions", "WARN",
             f"Rewrote {changed} content_hash values to canonical identity "
             f"(strips <ukm:UnappliedEffects> volatile metadata); collapsed {removed} "
             "duplicates; append-only triggers restored."),
        )
        conn.commit()

        dup_left = conn.execute(
            "SELECT COUNT(*) FROM (SELECT record_id,valid_from FROM record_versions"
            " GROUP BY 1,2 HAVING COUNT(*)>1)"
        ).fetchone()[0]
        trig = sorted(r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"))
        print(f"\n  versions now : {conn.execute('SELECT COUNT(*) FROM record_versions').fetchone()[0]}")
        print(f"  duplicate groups: {dup_left}")
        print(f"  triggers restored: {trig}")
        return 0 if dup_left == 0 and len(trig) == 4 else 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
