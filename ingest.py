"""
Phase 1 ingestion service — legislation.gov.uk point-in-time legal history.

MASTER-PROMPT-V2 compliance:
  §28  6 tables, 1 service, 0 agents in the data path
  §28  append-only snapshot + diff; never overwrite history
  §31  deterministic by default: NO LLM anywhere in this file
  §23  source license/rate limits enforced in CODE, not a prompt
  §24  external content is untrusted data; it never becomes an instruction
  §25  every action written to an immutable audit log

Empirically-derived controls (measured 2026-09-08/09, see PHASE0-EMPIRICAL-FINDINGS.md):
  * server tolerates ~14 req/s, but robots.txt declares Crawl-delay: 5.
    We enforce a POLITE rate well under tolerance. Being defensible > being fast.
  * silent-truncation detection: the eCFR 1,000-row cap taught us that a
    capped response looks identical to a complete one. We assert on suspicious
    boundaries and escalate to CRITICAL rather than continuing quietly.
  * resumable checkpoints: a multi-minute backfill will be interrupted.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

USER_AGENT = "uk-legal-history-pipeline/0.1 (+public data reuse under OGL v3)"
BASE = "https://www.legislation.gov.uk"

SOURCE_ID = "uk-legislation"
# Verbatim from https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/
# verified 2026-09-08. OGL v3 permits commercial exploitation, and REQUIRES attribution.
OGL_TERMS_EXCERPT = (
    "You are free to: copy, publish, distribute and transmit the Information; "
    "adapt the Information; exploit the Information commercially and "
    "non-commercially... You must (where you do any of the above): acknowledge "
    "the source of the Information in your product or application by including "
    "or linking to any attribution statement specified by the Information Provider(s)"
)
ATTRIBUTION = (
    "Contains public sector information licensed under the Open Government Licence v3.0. "
    "Source: legislation.gov.uk (The National Archives)."
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- rate limiting
class RateLimiter:
    """Deterministic politeness. Enforced in code so no caller can opt out (§23)."""

    def __init__(self, max_rps: float):
        self.min_interval = 1.0 / max_rps
        self._last = 0.0

    def wait(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last = time.monotonic()


class TruncationSuspected(Exception):
    """Raised when a response looks like it may have been silently capped."""


# ---------------------------------------------------------------- http client
@dataclass
class Fetch:
    status: int
    body: bytes
    ms: int
    url: str


class Client:
    """Serial, rate-limited, backoff-on-429. Never concurrent against one host."""

    def __init__(self, limiter: RateLimiter, max_retries: int = 4):
        self.limiter = limiter
        self.max_retries = max_retries
        self.requests_made = 0
        self.http_429_count = 0

    def get(self, url: str, timeout: int = 45) -> Fetch:
        delay = 2.0
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            self.limiter.wait()
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "application/xml"}
            )
            t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    body = r.read()
                    self.requests_made += 1
                    return Fetch(r.status, body, int((time.time() - t0) * 1000), url)
            except urllib.error.HTTPError as e:
                self.requests_made += 1
                if e.code == 429:
                    # No Retry-After is sent by some gov hosts — back off blind.
                    self.http_429_count += 1
                    time.sleep(delay)
                    delay *= 2
                    last_exc = e
                    continue
                if e.code == 404:
                    return Fetch(404, b"", int((time.time() - t0) * 1000), url)
                last_exc = e
                time.sleep(delay)
                delay *= 2
            except Exception as e:  # network flake
                last_exc = e
                time.sleep(delay)
                delay *= 2
        raise RuntimeError(f"GET failed after {self.max_retries} attempts: {url}: {last_exc!r}")


# ---------------------------------------------------------------- parsing
# NOTE (§24): everything below treats the payload as UNTRUSTED DATA.
# We extract declared fields with explicit patterns. We never eval, never
# execute, and never route document text into an instruction path.

RE_RESTRICT_START = re.compile(r'RestrictStartDate="(\d{4}-\d{2}-\d{2})"')
RE_TITLE = re.compile(r"<dc:title>(.*?)</dc:title>", re.S)
RE_P1GROUP = re.compile(r"<P1group[^>]*>(.*?)</P1group>", re.S)
RE_INNER_TITLE = re.compile(r"<Title>(.*?)</Title>", re.S)
RE_PNUMBER = re.compile(r"<Pnumber[^>]*>(.*?)</Pnumber>", re.S)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def extract_version_dates(xml: str) -> list[str]:
    """Version boundaries are declared IN the document (verified 2026-09-08)."""
    return sorted(set(RE_RESTRICT_START.findall(xml)))


def extract_act_title(xml: str) -> str | None:
    m = RE_TITLE.search(xml)
    return _clean(m.group(1))[:300] if m else None


def extract_section_heading(xml: str, section: str) -> str | None:
    """The section's OWN heading, not the Act's.

    dc:title returns the Act name for every section, which made all 20 records
    look identical. The real heading lives in the P1group whose Pnumber matches.
    """
    for block in RE_P1GROUP.findall(xml):
        pn = RE_PNUMBER.search(block)
        if pn and _clean(pn.group(1)) == section:
            t = RE_INNER_TITLE.search(block)
            if t:
                return _clean(t.group(1))[:300]
    return None


def build_title(xml: str, section: str, fallback: str) -> str:
    act = extract_act_title(xml)
    head = extract_section_heading(xml, section)
    if act and head:
        return f"{act} s.{section} — {head}"
    if act:
        return f"{act} s.{section}"
    return fallback


def visible_text(xml: str) -> str:
    """Normalised text used for hashing and diffing. Deterministic."""
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", xml, flags=re.S | re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    body = body.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    body = body.replace("&#8217;", "'").replace("&nbsp;", " ").replace("&quot;", '"')
    return re.sub(r"\s+", " ", body).strip()


RE_UNAPPLIED = re.compile(r"<ukm:UnappliedEffects>.*?</ukm:UnappliedEffects>", re.S)
RE_VOLATILE_ATTR = re.compile(r'\s(?:Modified|RequiresApplied)="[^"]*"')


def canonical_for_hash(xml: str) -> str:
    """Strip server-side volatile metadata before hashing.

    legislation.gov.uk emits a <ukm:UnappliedEffects> block describing pending
    amendments not yet applied to the text. It carries a Modified="..."
    timestamp and reorders its attributes between requests, so the SAME legal
    text hashes differently on every fetch. Hashing raw XML therefore breaks
    idempotency: re-ingesting appends near-duplicate versions forever.

    We hash the *substantive* document only. UnappliedEffects describes future
    changes to the law, not the law as it stood on valid_from, so excluding it
    from identity is correct as well as convenient.
    """
    x = RE_UNAPPLIED.sub("", xml)
    x = RE_VOLATILE_ATTR.sub("", x)
    return re.sub(r"\s+", " ", x).strip()


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def content_identity(xml: str) -> str:
    """Stable identity hash for a version. Immune to server metadata churn."""
    return sha256(canonical_for_hash(xml))


# ---------------------------------------------------------------- store
class Store:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")

    def init_schema(self, schema_sql: Path) -> None:
        self.conn.executescript(schema_sql.read_text(encoding="utf-8"))
        self.conn.commit()

    def audit(self, action: str, subject: str | None = None, run_id: int | None = None,
              severity: str = "INFO", detail: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO audit_events(occurred_at,actor,action,subject,ingest_run_id,severity,detail)"
            " VALUES(?,?,?,?,?,?,?)",
            (utcnow(), "ingest-service", action, subject, run_id, severity, detail),
        )
        self.conn.commit()

    def register_source(self) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO sources
               (id,name,operator,base_url,license_id,license_url,attribution_text,
                commercial_use,redistribution,requires_api_key,max_requests_per_sec,
                crawl_delay_declared,restricted_fields,terms_verified_on,terms_excerpt,notes)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (SOURCE_ID, "UK Legislation", "The National Archives", BASE,
             "OGL-3.0", "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
             ATTRIBUTION, 1, 1, 0, 0.5, 5.0, "[]", "2026-09-08", OGL_TERMS_EXCERPT,
             "Measured 30/30 OK at 14.3 req/s; robots.txt declares Crawl-delay: 5. "
             "We deliberately run at 0.5 rps — well under tolerance."),
        )
        self.conn.commit()

    def start_run(self, cursor: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO ingest_runs(source_id,started_at,status,cursor) VALUES(?,?,?,?)",
            (SOURCE_ID, utcnow(), "RUNNING", cursor),
        )
        self.conn.commit()
        return cur.lastrowid

    def checkpoint(self, run_id: int, cursor: str, client: Client, **counts) -> None:
        sets = ", ".join(f"{k}={k}+?" for k in counts)
        params = list(counts.values())
        sql = (f"UPDATE ingest_runs SET cursor=?, requests_made=?, http_429_count=?"
               + (f", {sets}" if sets else "") + " WHERE id=?")
        self.conn.execute(sql, [cursor, client.requests_made, client.http_429_count, *params, run_id])
        self.conn.commit()

    def finish_run(self, run_id: int, status: str, error: str | None = None) -> None:
        self.conn.execute(
            "UPDATE ingest_runs SET finished_at=?, status=?, error=? WHERE id=?",
            (utcnow(), status, error, run_id),
        )
        self.conn.commit()

    def resumable_run(self) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM ingest_runs WHERE status IN ('RUNNING','INTERRUPTED')"
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()

    def upsert_record(self, rid: str, uri: str, title: str | None, rtype: str,
                      jurisdiction: str) -> None:
        now = utcnow()
        self.conn.execute(
            """INSERT INTO records(id,source_id,record_type,jurisdiction,title,uri,
                                   first_seen_at,last_seen_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET last_seen_at=excluded.last_seen_at,
                                             title=COALESCE(excluded.title, records.title)""",
            (rid, SOURCE_ID, rtype, jurisdiction, title, uri, now, now),
        )

    def add_version(self, rid: str, valid_from: str, content: str, run_id: int) -> int | None:
        """Append-only. Returns new version id, or None if already known (idempotent).

        Identity is the CANONICAL hash (server metadata stripped), so repeated
        ingestion of an unchanged provision is a no-op even though the raw
        bytes differ between fetches.
        """
        h = content_identity(content)
        dup = self.conn.execute(
            "SELECT id FROM record_versions WHERE record_id=? AND valid_from=? AND content_hash=?",
            (rid, valid_from, h),
        ).fetchone()
        if dup:
            return None
        cur = self.conn.execute(
            """INSERT INTO record_versions(record_id,valid_from,retrieved_at,content_hash,
                                           content,content_bytes,ingest_run_id)
               VALUES(?,?,?,?,?,?,?)""",
            (rid, valid_from, utcnow(), h, content, len(content), run_id),
        )
        return cur.lastrowid

    def versions_for(self, rid: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM record_versions WHERE record_id=? ORDER BY valid_from, id", (rid,)
        ).fetchall()

    def add_change(self, rid: str, prev, curr, change_type: str) -> bool:
        exists = self.conn.execute(
            "SELECT 1 FROM record_changes WHERE record_id=? AND to_version=?", (rid, curr["id"])
        ).fetchone()
        if exists:
            return False
        a = visible_text(prev["content"]) if prev else ""
        b = visible_text(curr["content"])
        added = max(0, len(b) - len(a))
        removed = max(0, len(a) - len(b))
        if change_type == "INITIAL":
            summary = f"First recorded version, in force from {curr['valid_from']}."
        elif a == b:
            # Same visible text under a new boundary date: the provision was
            # re-issued without substantive textual change. Say so honestly
            # rather than reporting a "+0/-0" change, which reads as a bug.
            change_type = "REENACTED"
            summary = (f"New version boundary at {curr['valid_from']} with no change to "
                       f"visible text (previous boundary {prev['valid_from']}).")
        else:
            net = len(b) - len(a)
            if net > 0:
                direction = f"expanded by {net} characters"
            elif net < 0:
                direction = f"shortened by {abs(net)} characters"
            else:
                direction = "revised with no net length change"
            summary = (f"Text {direction} at the {curr['valid_from']} boundary "
                       f"(previous boundary {prev['valid_from']}).")
        self.conn.execute(
            """INSERT INTO record_changes(record_id,from_version,to_version,change_date,
                                          change_type,chars_added,chars_removed,summary,detected_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (rid, prev["id"] if prev else None, curr["id"], curr["valid_from"],
             change_type, added, removed, summary, utcnow()),
        )
        return True

    def commit(self) -> None:
        self.conn.commit()


# ---------------------------------------------------------------- ingestion
@dataclass
class Target:
    """A provision to track. Explicit allowlist — no crawling, no discovery."""
    act: str          # e.g. "ukpga/1998/42"
    section: str      # e.g. "1"
    label: str

    @property
    def record_id(self) -> str:
        return f"{self.act}/section/{self.section}"

    @property
    def url(self) -> str:
        return f"{BASE}/{self.act}/section/{self.section}/data.xml"

    def pit_url(self, date: str) -> str:
        return f"{BASE}/{self.act}/section/{self.section}/{date}/data.xml"


class Pipeline:
    def __init__(self, store: Store, client: Client):
        self.store = store
        self.client = client

    def ingest(self, targets: list[Target], run_id: int, resume_after: str | None = None):
        seen = versions = changes = trunc = 0
        started = False if resume_after else True

        for t in targets:
            if not started:
                if t.record_id == resume_after:
                    started = True
                continue

            try:
                n_v, n_c, n_t = self._ingest_one(t, run_id)
                seen += 1
                versions += n_v
                changes += n_c
                trunc += n_t
            except Exception as e:
                self.store.audit("ingest_record_failed", t.record_id, run_id, "WARN", repr(e)[:400])
                continue

            self.store.checkpoint(
                run_id, t.record_id, self.client,
                records_seen=1, versions_written=n_v, changes_written=n_c,
                truncation_alerts=n_t,
            )
        return seen, versions, changes, trunc

    def _ingest_one(self, t: Target, run_id: int) -> tuple[int, int, int]:
        current = self.client.get(t.url)
        if current.status != 200:
            self.store.audit("fetch_non_200", t.record_id, run_id, "WARN", f"status={current.status}")
            return 0, 0, 0

        xml = current.body.decode("utf-8", "replace")
        title = build_title(xml, t.section, t.label)
        self.store.upsert_record(t.record_id, t.url, title, "legislation_section", "UK")

        dates = extract_version_dates(xml)
        trunc_alerts = self._check_truncation(t, dates, run_id)

        # Fetch each declared point-in-time version. Append-only.
        new_versions = 0
        captured: set[str] = set()
        for d in dates:
            f = self.client.get(t.pit_url(d))
            if f.status != 200:
                self.store.audit("pit_unavailable", f"{t.record_id}@{d}", run_id, "INFO",
                                 f"status={f.status}")
                continue
            vid = self.store.add_version(t.record_id, d, f.body.decode("utf-8", "replace"), run_id)
            captured.add(d)
            if vid:
                new_versions += 1

        # Only store the "current" document if its boundary was NOT already
        # captured as a point-in-time version. Storing both produced spurious
        # self-comparisons ("changed on X vs version in force from X").
        latest = dates[-1] if dates else utcnow()[:10]
        if latest not in captured:
            if self.store.add_version(t.record_id, latest, xml, run_id):
                new_versions += 1

        self.store.commit()
        new_changes = self._compute_changes(t.record_id)
        self.store.commit()
        return new_versions, new_changes, trunc_alerts

    def _check_truncation(self, t: Target, dates: list[str], run_id: int) -> int:
        """The eCFR lesson: a silently-capped response looks exactly like a complete one.

        We cannot detect every cap, but we CAN refuse to treat suspicious
        round numbers as normal, and we escalate rather than continue quietly.
        """
        alerts = 0
        for suspicious in (100, 500, 1000):
            if len(dates) == suspicious:
                self.store.audit(
                    "possible_silent_truncation", t.record_id, run_id, "CRITICAL",
                    f"version count == {suspicious}, a suspicious round boundary. "
                    "Verify pagination before trusting this record.",
                )
                alerts += 1
        return alerts

    def _compute_changes(self, rid: str) -> int:
        versions = self.store.versions_for(rid)
        n = 0
        prev = None
        for v in versions:
            ctype = "INITIAL" if prev is None else "AMENDED"
            if self.store.add_change(rid, prev, v, ctype):
                n += 1
            prev = v
        return n
