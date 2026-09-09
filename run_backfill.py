"""
Phase 1 runner — backfills UK legislation point-in-time history.

Usage:
    python run_backfill.py            # resume if interrupted, else fresh
    python run_backfill.py --fresh    # ignore checkpoints

Deliberately picks provisions that are HIGH-TRAFFIC and KNOWN TO HAVE CHANGED,
because the falsification test in the Phase 0 gate needs provisions where a
"this changed on X" widget has something real to say.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from ingest import Client, Pipeline, RateLimiter, Store, Target, utcnow
from targets_500 import TARGETS as TARGETS_500

HERE = Path(__file__).parent
DB = HERE / "pipeline.db"
SCHEMA = HERE / "schema.sql"

# 20 provisions across 8 statutes. Explicit allowlist — no crawling (§8: no scraping).
TARGETS = [
    Target("ukpga/1998/42", "1",  "Human Rights Act 1998 s.1 — The Convention Rights"),
    Target("ukpga/1998/42", "2",  "Human Rights Act 1998 s.2 — Interpretation"),
    Target("ukpga/1998/42", "3",  "Human Rights Act 1998 s.3 — Legislation"),
    Target("ukpga/1998/42", "6",  "Human Rights Act 1998 s.6 — Public authorities"),

    Target("ukpga/2010/15", "4",  "Equality Act 2010 s.4 — Protected characteristics"),
    Target("ukpga/2010/15", "6",  "Equality Act 2010 s.6 — Disability"),
    Target("ukpga/2010/15", "13", "Equality Act 2010 s.13 — Direct discrimination"),
    Target("ukpga/2010/15", "19", "Equality Act 2010 s.19 — Indirect discrimination"),

    Target("ukpga/2006/46", "172", "Companies Act 2006 s.172 — Duty to promote success"),
    Target("ukpga/2006/46", "174", "Companies Act 2006 s.174 — Reasonable care and skill"),
    Target("ukpga/2006/46", "177", "Companies Act 2006 s.177 — Declaration of interest"),

    Target("ukpga/1996/18", "94",  "Employment Rights Act 1996 s.94 — Unfair dismissal"),
    Target("ukpga/1996/18", "98",  "Employment Rights Act 1996 s.98 — Fairness"),
    Target("ukpga/1996/18", "1",   "Employment Rights Act 1996 s.1 — Written particulars"),

    Target("ukpga/2018/12", "1",   "Data Protection Act 2018 s.1 — Overview"),
    Target("ukpga/2018/12", "3",   "Data Protection Act 2018 s.3 — Terms"),

    Target("ukpga/2015/15", "9",   "Consumer Rights Act 2015 s.9 — Satisfactory quality"),
    Target("ukpga/2015/15", "62",  "Consumer Rights Act 2015 s.62 — Fairness"),

    Target("ukpga/1974/37", "2",   "Health and Safety at Work Act 1974 s.2 — Duties"),
    Target("ukpga/2002/29", "327", "Proceeds of Crime Act 2002 s.327 — Concealing"),
]


def main() -> int:
    targets = TARGETS_500 if '--full' in sys.argv else TARGETS
    fresh = "--fresh" in sys.argv
    store = Store(DB)
    store.init_schema(SCHEMA)
    store.register_source()

    resume_after = None
    if not fresh:
        prior = store.resumable_run()
        if prior and prior["cursor"]:
            resume_after = prior["cursor"]
            store.finish_run(prior["id"], "INTERRUPTED")
            print(f"  resuming after checkpoint: {resume_after}")

    run_id = store.start_run(cursor=resume_after)
    store.audit("ingest_run_started", SOURCE := "uk-legislation", run_id, "INFO",
                f"targets={len(targets)} resume_after={resume_after}")

    # 0.5 rps — deliberately far under the measured ~14 rps tolerance (§23 politeness).
    client = Client(RateLimiter(max_rps=0.5))
    pipe = Pipeline(store, client)

    print(f"  run #{run_id} starting at {utcnow()} | {len(targets)} targets")
    t0 = time.time()
    try:
        seen, versions, changes, trunc = pipe.ingest(targets, run_id, resume_after)
        store.finish_run(run_id, "COMPLETED")
        store.audit("ingest_run_completed", "uk-legislation", run_id, "INFO",
                    f"records={seen} versions={versions} changes={changes}")
    except KeyboardInterrupt:
        store.finish_run(run_id, "INTERRUPTED")
        store.audit("ingest_run_interrupted", "uk-legislation", run_id, "WARN")
        print("  interrupted — checkpoint saved, rerun to resume")
        return 130
    except Exception as e:
        store.finish_run(run_id, "FAILED", repr(e)[:500])
        store.audit("ingest_run_failed", "uk-legislation", run_id, "CRITICAL", repr(e)[:400])
        raise

    el = time.time() - t0
    print(f"\n  records={seen} versions=+{versions} changes=+{changes} "
          f"truncation_alerts={trunc}")
    print(f"  requests={client.requests_made} http_429={client.http_429_count} "
          f"elapsed={el:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
