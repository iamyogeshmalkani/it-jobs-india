from conftest import DAY, HOUR, NOW, edits, make_job, sent
from jobbot.db import (STATUS_CANDIDATE, STATUS_CLOSED, STATUS_EXPIRED, STATUS_POSTED,
                       STATUS_SKIPPED)
from jobbot.india import ist_day_start
from jobbot.models import TYPE_JOB
from jobbot.pipeline import Pipeline
from jobbot.telegram import TelegramError


class Source:
    def __init__(self, *jobs, name="test", complete=False, every_minutes=60):
        self.jobs, self.name, self.complete, self.every_minutes = list(jobs), name, complete, every_minutes
        self.calls = 0

    def fetch(self):
        self.calls += 1
        return self.jobs


class Broken:
    name, complete, every_minutes = "broken", True, 60

    def fetch(self):
        raise RuntimeError("boom")


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now


def job(i, **kw):
    kw.setdefault("company", f"Company {i}")
    return make_job(source_job_id=str(i), url=f"https://jobs.example.com/{i}", **kw)


def pipe(cfg, repo, tg, *sources, clock=None):
    return Pipeline(cfg, repo, tg, list(sources), clock=clock or Clock())


def test_posts_every_new_job_in_one_run(cfg, repo, tg):
    clock = Clock()
    p = pipe(cfg, repo, tg, Source(job(1), job(2), job(3)), clock=clock)
    assert p.run() == {"new": 3, "closed": 0, "posted": 3, "errors": 0}
    assert len(sent(tg)) == 3 and repo.counts() == {STATUS_POSTED: 3}
    post = sent(tg)[0]
    assert post["chat_id"] == "@itjobs_test" and "Apply here" in post["text"]
    assert post["reply_markup"]["inline_keyboard"][0][0]["url"].startswith("https://jobs.example.com/")
    clock.now += HOUR
    assert p.run()["posted"] == 0  # nothing new: nothing is re-posted
    assert len(sent(tg)) == 3


def test_at_most_five_posts_per_hour(cfg, repo, tg):
    clock = Clock()
    p = pipe(cfg, repo, tg, Source(*[job(i) for i in range(8)]), clock=clock)
    assert p.run()["posted"] == 5
    clock.now += 30 * 60
    assert p.run()["posted"] == 0  # still inside the same hour
    clock.now += 28 * 60  # 58 min later: inside the cron-drift slack, so the next batch goes out
    assert p.run()["posted"] == 3
    assert len(sent(tg)) == 8 and repo.counts() == {STATUS_POSTED: 8}


def test_hourly_cap_can_be_changed_or_turned_off(cfg, repo, tg):
    cfg.max_posts_per_hour = 2
    assert pipe(cfg, repo, tg, Source(*[job(i) for i in range(6)])).run()["posted"] == 2


def test_hourly_cap_off_posts_everything(cfg, repo, tg):
    cfg.max_posts_per_hour = 0
    assert pipe(cfg, repo, tg, Source(*[job(i) for i in range(8)])).run()["posted"] == 8


def test_posts_carry_apply_and_share_buttons(cfg, repo, tg):
    pipe(cfg, repo, tg, Source(job(1))).run()
    row = sent(tg)[0]["reply_markup"]["inline_keyboard"][0]
    assert [b["text"] for b in row] == ["Apply now", "📤 Share"]
    assert "t.me/share/url?url=https%3A%2F%2Ft.me%2Fitjobs_test" in row[1]["url"]


def test_later_run_posts_only_the_new_jobs(cfg, repo, tg):
    clock = Clock()
    src = Source(job(1), job(2))
    p = pipe(cfg, repo, tg, src, clock=clock)
    assert p.run()["posted"] == 2
    src.jobs.append(job(3))
    clock.now += HOUR  # next scheduled run (the source is due again); no waiting interval to clear
    assert p.run()["posted"] == 1 and "jobs.example.com/3" in sent(tg)[2]["text"]


def test_deadline_must_be_tomorrow_or_later(cfg, repo, tg):
    tomorrow = ist_day_start(NOW) + DAY
    jobs = [job(1, deadline=tomorrow - 60),         # today 23:59 IST
            job(2, deadline=NOW + 2 * HOUR),         # later today
            job(3, deadline=NOW - HOUR),             # already passed
            job(4, deadline=tomorrow),               # tomorrow 00:00 IST
            job(5, deadline=tomorrow + 20 * HOUR),   # tomorrow evening
            job(6, deadline=NOW + 9 * DAY),          # next week
            job(7)]                                  # no deadline listed
    p = pipe(cfg, repo, tg, Source(*jobs))
    assert p.run()["posted"] == 4
    assert dict(p.skipped) == {"deadline_too_close": 3}
    assert sorted(m["text"].count("jobs.example.com") for m in sent(tg)) == [1, 1, 1, 1]
    urls = " ".join(m["reply_markup"]["inline_keyboard"][0][0]["url"] for m in sent(tg))
    assert all(f"/{i}" in urls for i in (4, 5, 6, 7)) and not any(f"/{i}" in urls for i in (1, 2, 3))


def test_unposted_candidate_expires_once_its_deadline_is_today(cfg, repo, tg):
    clock = Clock()
    real_send = tg.send

    def fail(*a, **k):
        raise TelegramError("temporary outage")
    tg.send = fail
    p = pipe(cfg, repo, tg, Source(job(1, deadline=NOW + DAY)), clock=clock)  # tomorrow 14:00 IST
    p.run()
    assert repo.counts() == {STATUS_CANDIDATE: 1}
    tg.send = real_send
    clock.now = NOW + 11 * HOUR  # 01:00 IST the next day: that deadline is now "today"
    stats = p.run()
    assert stats["posted"] == 0 and repo.counts() == {STATUS_EXPIRED: 1}


def test_failing_telegram_stops_after_a_few_errors(cfg, repo, tg):
    def fail(*a, **k):
        raise TelegramError("chat not found")
    tg.send = fail
    p = pipe(cfg, repo, tg, Source(*[job(i) for i in range(10)]))
    assert p.run()["posted"] == 0
    assert len(p.errors) == 3 and repo.counts() == {STATUS_CANDIDATE: 10}


def test_newest_job_goes_first(cfg, repo, tg):
    old, new = job(1, posted_at=NOW - 3 * DAY), job(2, posted_at=NOW - HOUR)
    pipe(cfg, repo, tg, Source(old, new)).run()
    assert "jobs.example.com/2" in sent(tg)[0]["text"]


def test_posts_at_any_hour_by_default(cfg, repo, tg):
    night = NOW - 11 * HOUR  # 03:00 IST
    stats = pipe(cfg, repo, tg, Source(job(1, posted_at=night - HOUR)), clock=Clock(night)).run()
    assert stats["new"] == 1 and stats["posted"] == 1


def test_optional_quiet_hours_still_work(cfg, repo, tg):
    cfg.quiet_start_hour, cfg.quiet_end_hour = 0, 7
    night = NOW - 11 * HOUR  # 03:00 IST
    stats = pipe(cfg, repo, tg, Source(job(1, posted_at=night - HOUR)), clock=Clock(night)).run()
    assert stats["new"] == 1 and stats["posted"] == 0 and sent(tg) == []


def test_filtered_jobs_are_not_stored(cfg, repo, tg):
    jobs = [job(1, title="Senior Software Engineer"), job(2, title="Sales Intern"),
            job(3, locations=["Berlin"]), job(4, posted_at=NOW - 30 * DAY),
            job(5, source="unstop", deadline=NOW + 2 * HOUR)]
    p = pipe(cfg, repo, tg, Source(*jobs))
    assert p.run()["new"] == 0
    assert repo.counts() == {}
    assert dict(p.skipped) == {"not_entry_level": 1, "not_it": 1, "not_india": 1, "too_old": 1,
                               "deadline_too_close": 1}


def test_undated_jobs_on_a_new_source_are_backfill(cfg, repo, tg):
    clock = Clock()
    src = Source(job(1, posted_at=None))
    p = pipe(cfg, repo, tg, src, clock=clock)
    assert p.run()["posted"] == 0
    assert repo.skip_reasons() == {"backfill": 1}
    src.jobs.append(job(2, posted_at=None))  # appears after the first run: genuinely new
    clock.now += HOUR
    assert p.run()["posted"] == 1 and "jobs.example.com/2" in sent(tg)[0]["text"]


def test_complete_source_closes_removed_job(cfg, repo, tg):
    clock = Clock()
    src = Source(job(1), name="greenhouse:acme", complete=True)
    p = pipe(cfg, repo, tg, src, clock=clock)
    p.run()
    src.jobs = []
    clock.now += HOUR
    assert p.run()["closed"] == 0  # one missing fetch is not enough
    clock.now += 2 * HOUR
    assert p.run()["closed"] == 1
    edit = edits(tg)[0]
    assert edit["text"].startswith("❌ <b>CLOSED</b>") and edit["reply_markup"] == {"inline_keyboard": []}
    assert repo.counts() == {STATUS_CLOSED: 1}


def test_failed_fetch_never_closes_anything(cfg, repo, tg):
    clock = Clock()
    src = Source(job(1), name="greenhouse:acme", complete=True)
    p = pipe(cfg, repo, tg, src, clock=clock)
    p.run()

    def boom():
        raise RuntimeError("timeout")
    src.fetch = boom
    clock.now += 5 * HOUR
    stats = p.run()
    assert stats["closed"] == 0 and stats["errors"] == 1
    assert repo.counts() == {STATUS_POSTED: 1}


def test_incomplete_source_does_not_close_missing_job(cfg, repo, tg):
    clock = Clock()
    src = Source(job(1), name="unstop")
    p = pipe(cfg, repo, tg, src, clock=clock)
    p.run()
    src.jobs = []
    clock.now += 6 * HOUR
    assert p.run()["closed"] == 0 and repo.counts() == {STATUS_POSTED: 1}


def test_deadline_closes_post_and_expires_candidates(cfg, repo, tg):
    clock = Clock()
    p = pipe(cfg, repo, tg, Source(job(1, deadline=NOW + DAY), job(2, deadline=NOW + DAY)), clock=clock)
    p.run()
    clock.now += DAY
    assert p.run()["closed"] == 2
    assert repo.counts() == {STATUS_CLOSED: 2}


def test_candidate_that_ages_out_is_never_posted(cfg, repo, tg):
    clock = Clock()
    cfg.max_posts_per_day = 1  # leave one job unposted so it can age out
    p = pipe(cfg, repo, tg, Source(job(1), job(2)), clock=clock)
    p.run()
    clock.now += 11 * DAY
    p.run()
    assert len(sent(tg)) == 1 and repo.counts()[STATUS_EXPIRED] == 1


def test_same_job_from_two_sources_posts_once(cfg, repo, tg):
    clock = Clock()
    a = job(1, company="Acme Labs Pvt Ltd", title="SDE Intern")
    b = job(2, company="Acme Labs", title="SDE Intern", source="unstop")
    p = pipe(cfg, repo, tg, Source(a, name="greenhouse:acme"), Source(b, name="unstop"), clock=clock)
    p.run()
    clock.now += HOUR
    p.run()
    assert len(sent(tg)) == 1
    assert repo.skip_reasons() == {"duplicate": 1}


def test_same_company_posts_together_by_default(cfg, repo, tg):
    same = [job(1, company="Acme"), job(2, company="Acme", title="Data Analyst Intern")]
    p = pipe(cfg, repo, tg, Source(*same, job(3, company="Globex")))
    assert p.run()["posted"] == 3


def test_optional_company_cooldown_makes_a_company_wait(cfg, repo, tg):
    clock = Clock()
    cfg.company_cooldown_hours = 12
    same = [job(1, company="Acme"), job(2, company="Acme", title="Data Analyst Intern")]
    other = job(3, company="Globex", posted_at=NOW - 2 * DAY)
    p = pipe(cfg, repo, tg, Source(*same, other), clock=clock)
    p.run()
    clock.now += HOUR
    p.run()  # Acme still in cooldown and nothing else left
    texts = [m["text"] for m in sent(tg)]
    assert len(texts) == 2 and "Globex" in texts[1]
    assert repo.counts()[STATUS_CANDIDATE] == 1


def test_alternates_internships_and_jobs(cfg, repo, tg):
    interns = [job(i, title=f"Backend Intern {i}", posted_at=NOW - i * 60) for i in range(1, 4)]
    fresher = job(9, title="SDE 1", job_type=TYPE_JOB, posted_at=NOW - 20 * HOUR)
    p = pipe(cfg, repo, tg, Source(*interns, fresher))
    assert p.run()["posted"] == 4
    assert "ENTRY-LEVEL JOB" in sent(tg)[1]["text"]


def test_optional_daily_cap(cfg, repo, tg):
    cfg.max_posts_per_day = 2
    p = pipe(cfg, repo, tg, Source(*[job(i) for i in range(5)]))
    for _ in range(4):
        p.run()
    assert len(sent(tg)) == 2


def test_optional_post_interval(cfg, repo, tg):
    clock = Clock()
    cfg.post_interval_minutes = 60
    src = Source(job(1))
    p = pipe(cfg, repo, tg, src, clock=clock)
    assert p.run()["posted"] == 1
    src.jobs.append(job(2))
    clock.now += 30 * 60
    assert p.run()["posted"] == 0  # too soon
    clock.now += 28 * 60  # 58 min after the last post: inside the cron-drift slack
    assert p.run()["posted"] == 1


def test_source_cadence(cfg, repo, tg):
    clock = Clock()
    slow = Source(job(1), name="workday:x", every_minutes=180)
    p = pipe(cfg, repo, tg, slow, clock=clock)
    p.run()
    clock.now += HOUR
    p.run()
    assert slow.calls == 1
    clock.now += 2 * HOUR
    p.run()
    assert slow.calls == 2


def test_broken_source_does_not_stop_others(cfg, repo, tg):
    stats = pipe(cfg, repo, tg, Broken(), Source(job(1))).run()
    assert stats["posted"] == 1 and stats["errors"] == 1
    assert [s["key"] for s in repo.sources() if s["last_error"]] == ["broken"]


def test_telegram_failure_keeps_job_for_next_run(cfg, repo, tg):
    def fail(*a, **k):
        raise TelegramError("chat not found")
    tg.send = fail
    p = pipe(cfg, repo, tg, Source(job(1)))
    stats = p.run()
    assert stats["posted"] == 0 and any(e.startswith("telegram") for e in p.errors)
    assert repo.counts() == {STATUS_CANDIDATE: 1}


def test_already_stored_job_is_not_reinserted(cfg, repo, tg):
    clock = Clock()
    src = Source(job(1))
    p = pipe(cfg, repo, tg, src, clock=clock)
    p.run()
    clock.now += HOUR
    assert p.run()["new"] == 0
    row = repo.by_status(STATUS_POSTED)[0]
    assert row["last_seen"] == clock.now and row["first_seen"] == NOW
    assert STATUS_SKIPPED not in repo.counts()
