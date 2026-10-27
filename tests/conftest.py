from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from jobbot.config import Config
from jobbot.db import TABLES, Db, Repo
from jobbot.india import IST
from jobbot.models import RawJob
from jobbot.telegram import Telegram

# 2026-10-27 14:00 IST, a Tuesday afternoon (outside quiet hours).
NOW = int(datetime(2026, 10, 27, 14, 0, tzinfo=IST).timestamp())
HOUR = 3600
DAY = 86400
FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str):
    """Trimmed real responses saved from each source on 2026-10-27."""
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def cfg() -> Config:
    return Config(channel_id="@itjobs_test", dry_run=True)


@pytest.fixture
def repo() -> Repo:
    """In-memory SQLite by default; set TEST_DATABASE_URL to run the suite on Postgres."""
    url = os.environ.get("TEST_DATABASE_URL", ":memory:")
    db = Db(url)
    if db.is_postgres:
        db.query(f"DROP TABLE IF EXISTS {', '.join(TABLES)} CASCADE")
    r = Repo(db)
    r.init()
    yield r
    db.close()


@pytest.fixture
def tg() -> Telegram:
    return Telegram("", dry_run=True, min_interval=0)


def make_job(**overrides) -> RawJob:
    base = dict(source="test", source_job_id="1", company="Acme Labs",
                title="Software Engineer Intern", url="https://jobs.example.com/1",
                locations=["Bengaluru, India"], posted_at=NOW - 2 * HOUR)
    base.update(overrides)
    return RawJob(**base)


def sent(tg: Telegram):
    return [m for m in tg.outbox if m["method"] == "sendMessage"]


def edits(tg: Telegram):
    return [m for m in tg.outbox if m["method"] == "editMessageText"]
