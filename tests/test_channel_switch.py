from conftest import DAY, HOUR, NOW, make_job, sent
from jobbot.cli import CHANNEL_KEY, channel_changed, remember_channel
from jobbot.config import Config
from jobbot.db import STATUS_CANDIDATE, STATUS_CLOSED, STATUS_EXPIRED, STATUS_POSTED
from jobbot.pipeline import Pipeline
from jobbot.telegram import Telegram


class Source:
    name, complete, every_minutes = "test", False, 60

    def __init__(self, *jobs):
        self.jobs = list(jobs)

    def fetch(self):
        return self.jobs


def job(i, **kw):
    return make_job(source_job_id=str(i), url=f"https://jobs.example.com/{i}",
                    company=f"Company {i}", **kw)


def test_channel_guard(repo):
    cfg = Config(channel_id="@Old_Channel")
    assert not channel_changed(repo, cfg)  # nothing remembered yet
    remember_channel(repo, cfg)
    assert repo.get_kv(CHANNEL_KEY) == "@old_channel"
    assert not channel_changed(repo, Config(channel_id="@old_channel "))  # case/space ignored
    assert channel_changed(repo, Config(channel_id="@new_channel"))


def test_requeue_posted_jobs_for_a_new_channel(repo):
    old = Config(channel_id="@old_channel")
    old_tg = Telegram("", dry_run=True, min_interval=0)
    clock = [NOW]
    src = Source(job(1), job(2, deadline=NOW + 3 * DAY), job(3, deadline=NOW + 2 * DAY))
    old_pipe = Pipeline(old, repo, old_tg, [src], clock=lambda: clock[0])
    assert old_pipe.run()["posted"] == 3 and len(sent(old_tg)) == 3

    # Job 3's deadline passes on the old channel and its post is closed.
    clock[0] = NOW + 2 * DAY + HOUR
    old_pipe.run()
    assert repo.counts() == {STATUS_POSTED: 2, STATUS_CLOSED: 1}

    # Switch: re-queue the open posts and post them with no caps in the new channel.
    new = Config(channel_id="@new_channel", max_posts_per_hour=0)
    new_tg = Telegram("", dry_run=True, min_interval=0)
    assert repo.requeue_posted() == 2
    row = repo.by_status(STATUS_CANDIDATE)[0]
    assert row["sent_at"] is None and row["tg_message_id"] is None and row["text"] == ""
    new_pipe = Pipeline(new, repo, new_tg, [src], clock=lambda: clock[0])
    assert new_pipe.run()["posted"] == 2
    assert {m["chat_id"] for m in sent(new_tg)} == {"@new_channel"}
    assert len(sent(old_tg)) == 3  # nothing more went to the old channel
    assert repo.counts() == {STATUS_POSTED: 2, STATUS_CLOSED: 1}
    assert all(r["tg_message_id"] for r in repo.by_status(STATUS_POSTED))


def test_requeued_job_with_a_passed_deadline_is_not_reposted(repo):
    cfg = Config(channel_id="@old_channel")
    clock = [NOW]
    tg = Telegram("", dry_run=True, min_interval=0)
    p = Pipeline(cfg, repo, tg, [Source(job(1, deadline=NOW + DAY))], clock=lambda: clock[0])
    assert p.run()["posted"] == 1
    clock[0] = NOW + DAY + HOUR  # the deadline has passed but no run noticed yet
    repo.requeue_posted()
    new_tg = Telegram("", dry_run=True, min_interval=0)
    stats = Pipeline(Config(channel_id="@new_channel"), repo, new_tg, [Source()],
                     clock=lambda: clock[0]).run()
    assert stats["posted"] == 0 and repo.counts() == {STATUS_EXPIRED: 1}
