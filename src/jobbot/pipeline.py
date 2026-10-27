"""One bot cycle: collect -> store new candidates -> close ended jobs -> post one job.

Stateless between runs (state lives in the database) so it can be driven by an hourly
GitHub Actions cron. Fully automatic: there is no review step, so every filter that
protects the channel (India, IT, entry level, paid, scam signals, freshness) runs here.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from jobbot import classify
from jobbot.collectors.base import Collector
from jobbot.composer import compose
from jobbot.config import Config
from jobbot.db import (STATUS_CANDIDATE, STATUS_CLOSED, STATUS_EXPIRED, STATUS_POSTED,
                       STATUS_SKIPPED, Repo)
from jobbot.india import ist_day_start, is_quiet_hours
from jobbot.models import MODE_REMOTE, RawJob, dedupe_key, norm
from jobbot.telegram import Telegram, TelegramError

log = logging.getLogger("jobbot")

HOUR = 3600
# GitHub cron runs drift by minutes; allow this much early so a run that fires slightly
# before the interval has elapsed is not pushed back a whole cycle.
SLACK_SECONDS = 5 * 60
# A job must be missing from a complete source for this long before it counts as closed,
# so one flaky response never closes a live post.
CLOSE_AFTER_MISSING_SECONDS = 2 * HOUR
TOUCH_CHUNK = 500
FETCH_WORKERS = 8


def raw_from_json(text: str) -> RawJob:
    return RawJob(**json.loads(text))


class Pipeline:
    def __init__(self, cfg: Config, repo: Repo, tg: Telegram, collectors: Sequence[Collector],
                 clock: Callable[[], int] = lambda: int(time.time())):
        self.cfg, self.repo, self.tg, self.collectors, self.clock = cfg, repo, tg, collectors, clock
        self.skipped: Counter = Counter()  # this run's filter decisions, for logs and preview
        self.errors: List[str] = []
        self.closed_posts = 0  # posts edited to CLOSED this run

    def run(self, publish: bool = True) -> Dict[str, int]:
        stats = {"new": self.collect()}
        self.close_ended()
        stats["closed"] = self.closed_posts
        stats["posted"] = self.publish() if publish else 0
        stats["errors"] = len(self.errors)
        return stats

    # --- 1. collect ----------------------------------------------------------

    def _due(self, collector: Collector, now: int) -> bool:
        last = self.repo.source_last_ok(collector.name)
        return last is None or now - last >= collector.every_minutes * 60 - SLACK_SECONDS

    @staticmethod
    def _fetch(collector: Collector) -> Tuple[Optional[List[RawJob]], str]:
        try:
            return collector.fetch(), ""
        except Exception as exc:  # one broken source must not stop the run
            return None, f"{type(exc).__name__}: {exc}"

    def collect(self) -> int:
        """Fetch due sources in parallel (network-bound), then store results one by one."""
        now, new = self.clock(), 0
        due = [c for c in self.collectors if self._due(c, now)]
        first_runs = {c.name: self.repo.source_last_ok(c.name) is None for c in due}
        with ThreadPoolExecutor(FETCH_WORKERS) as pool:
            results = list(pool.map(self._fetch, due))
        for collector, (jobs, error) in zip(due, results):
            if jobs is None:
                log.warning("source %s failed: %s", collector.name, error)
                self.repo.record_source(collector.name, None, None, error)
                self.errors.append(collector.name)
                continue
            new += self.ingest(collector.name, jobs, now, first_runs[collector.name])
            self.repo.record_source(collector.name, now, len(jobs))
            if collector.complete:
                self.close_missing(collector.name, now)
        return new

    def ingest(self, source: str, jobs: Sequence[RawJob], now: int, first_run: bool) -> int:
        """Store jobs that pass the filters; refresh last_seen for ones already stored.
        Jobs that fail a filter aren't stored, so the table holds only real candidates."""
        known = {row["source_job_id"]: row for row in
                 self.repo.db.query("SELECT source_job_id, status FROM job_listings WHERE source = %s",
                                    (source,))}
        touch, new = [], 0
        for job in jobs:
            if job.source_job_id in known:
                touch.append(job.source_job_id)
                continue
            known[job.source_job_id] = {}
            reason = classify.classify(job, self.cfg.skip_unpaid) or self._freshness(job, now)
            if reason:
                self.skipped[reason.split(":")[0]] += 1
                continue
            status, reason = STATUS_CANDIDATE, ""
            if job.posted_at is None and first_run:
                status, reason = STATUS_SKIPPED, "backfill"  # undated job on a new source
            elif self._duplicate(job, now):
                status, reason = STATUS_SKIPPED, "duplicate"
            self.repo.insert_listing(
                source=source, source_job_id=job.source_job_id, dedupe_key=dedupe_key(job),
                company_key=norm(job.company), company=job.company, title=job.title, url=job.url,
                job_type=classify.job_type(job), status=status, reason=reason,
                score=self.static_score(job), published_at=job.posted_at, deadline=job.deadline,
                now=now, raw=json.dumps(dataclasses.asdict(job)))
            if status == STATUS_CANDIDATE:
                new += 1
            else:
                self.skipped[reason] += 1
        for i in range(0, len(touch), TOUCH_CHUNK):
            chunk = touch[i:i + TOUCH_CHUNK]
            marks = ", ".join(["%s"] * len(chunk))
            self.repo.db.query(
                f"UPDATE job_listings SET last_seen = %s WHERE source = %s AND source_job_id IN ({marks})",
                (now, source, *chunk))
        return new

    def _freshness(self, job: RawJob, now: int) -> str:
        if job.posted_at and now - job.posted_at > self.cfg.max_job_age_days * 24 * HOUR:
            return "too_old"
        if job.deadline and job.deadline - now < self.cfg.min_hours_before_deadline * HOUR:
            return "deadline_too_close"
        return ""

    def _duplicate(self, job: RawJob, now: int) -> bool:
        key = dedupe_key(job)
        if self.repo.was_posted("dedupe_key", key, now - self.cfg.repost_cooldown_days * 24 * HOUR):
            return True
        rows = self.repo.db.query(
            "SELECT 1 AS x FROM job_listings WHERE dedupe_key = %s AND status = %s LIMIT 1",
            (key, STATUS_CANDIDATE))
        return bool(rows)

    @staticmethod
    def static_score(job: RawJob) -> int:
        """The part of a job's priority that doesn't change with time."""
        score = 0 if job.via else 15  # straight from the employer's own careers site
        if job.pay_min or job.pay_max:
            score += 10
        if classify.work_mode(job) == MODE_REMOTE:
            score += 5
        return score

    # --- 2. close ended jobs ---------------------------------------------

    def close_missing(self, source: str, now: int) -> None:
        for row in self.repo.unseen_since(source, now - CLOSE_AFTER_MISSING_SECONDS,
                                          STATUS_CANDIDATE, STATUS_POSTED):
            self._close(row, now, "removed_from_source")

    def close_ended(self) -> None:
        """Close posts whose deadline passed; expire candidates that aged out unposted."""
        now = self.clock()
        max_age = self.cfg.max_job_age_days * 24 * HOUR
        for row in self.repo.by_status(STATUS_CANDIDATE, STATUS_POSTED):
            if row["deadline"] and int(row["deadline"]) <= now:
                self._close(row, now, "deadline_passed")
            elif row["status"] == STATUS_CANDIDATE:
                published = int(row["published_at"] or row["first_seen"])
                left = (int(row["deadline"]) - now) if row["deadline"] else None
                if now - published > max_age:
                    self._close(row, now, "too_old")
                elif left is not None and left < self.cfg.min_hours_before_deadline * HOUR:
                    self._close(row, now, "deadline_too_close")

    def _close(self, row: Dict, now: int, reason: str) -> None:
        if row["status"] == STATUS_CANDIDATE:
            self.repo.update(row["id"], status=STATUS_EXPIRED, reason=reason, closed_at=now)
            return
        try:
            self.tg.edit(self.cfg.channel_id, int(row["tg_message_id"]), row["closed_text"], [])
        except TelegramError as exc:
            log.warning("could not edit closed job %s: %s", row["id"], exc)
        self.repo.update(row["id"], status=STATUS_CLOSED, reason=reason, closed_at=now)
        self.closed_posts += 1

    # --- 3. post one job -------------------------------------------------

    def priority(self, row: Dict, now: int, last_type: Optional[str]) -> float:
        published = int(row["published_at"] or row["first_seen"])
        age_hours = max(0, now - published) / HOUR
        score = 100 + int(row["score"]) - min(age_hours, 7 * 24) / 2  # newest first
        if last_type and row["job_type"] != last_type:
            score += 12  # alternate internships and jobs
        return score

    def publish(self) -> int:
        now = self.clock()
        if is_quiet_hours(now, self.cfg.quiet_start_hour, self.cfg.quiet_end_hour):
            return 0
        if self.repo.sent_count_since(ist_day_start(now)) >= self.cfg.max_posts_per_day:
            return 0
        last = self.repo.last_sent()
        if last and now - int(last["sent_at"]) < self.cfg.post_interval_minutes * 60 - SLACK_SECONDS:
            return 0
        last_type = last["job_type"] if last else None
        rows = sorted(self.repo.by_status(STATUS_CANDIDATE),
                      key=lambda r: self.priority(r, now, last_type), reverse=True)
        company_since = now - self.cfg.company_cooldown_hours * HOUR
        for row in rows:
            if self.repo.was_posted("dedupe_key", row["dedupe_key"],
                                    now - self.cfg.repost_cooldown_days * 24 * HOUR):
                self.repo.update(row["id"], status=STATUS_SKIPPED, reason="duplicate")
                continue
            if self.repo.was_posted("company_key", row["company_key"], company_since):
                continue  # give other companies a turn; this one waits
            return self._send(row, now)
        return 0

    def _send(self, row: Dict, now: int) -> int:
        composed = compose(raw_from_json(row["raw"]), now)
        try:
            sent = self.tg.send(self.cfg.channel_id, composed.text, composed.keyboard)
        except TelegramError as exc:
            log.error("posting job %s failed: %s", row["id"], exc)
            self.errors.append(f"telegram: {exc}")
            return 0
        self.repo.update(row["id"], status=STATUS_POSTED, sent_at=now, tg_message_id=sent.message_id,
                         text=composed.text, closed_text=composed.closed_text,
                         keyboard=composed.keyboard)
        return 1
