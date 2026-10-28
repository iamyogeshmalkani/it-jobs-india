"""Runtime configuration, read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

DEFAULT_COMPANIES_FILE = str(Path(__file__).resolve().parents[2] / "data" / "companies.json")


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader. Existing environment variables win."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key, "").strip()
    return int(raw) if raw else default


def _bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key, "").strip().lower()
    return default if not raw else raw in ("1", "true", "yes")


@dataclass
class Config:
    database_url: str = ""
    bot_token: str = ""
    channel_id: str = ""

    companies_file: str = DEFAULT_COMPANIES_FILE
    enable_unstop: bool = True
    unstop_pages: int = 20  # max pages of 100 per type (internships, jobs); stops early at the end

    skip_unpaid: bool = True
    max_job_age_days: int = 10  # never post anything published longer ago than this
    # Jobs whose deadline is today (IST) or already passed are never posted; tomorrow or later is fine.
    company_cooldown_hours: int = 0  # 0 = no limit; N = at most one post per company per N hours
    repost_cooldown_days: int = 30  # same company + title is not posted again within this

    # Every run posts all new jobs. The limits below are off by default (0 = off).
    post_interval_minutes: int = 0  # minimum minutes between runs that post
    max_posts_per_day: int = 0  # cap per IST day
    quiet_start_hour: int = 0  # IST quiet window [start, end); equal values = no quiet hours
    quiet_end_hour: int = 0
    dry_run: bool = False

    @property
    def user_agent(self) -> str:
        contact = f" (+https://t.me/{self.channel_id[1:]})" if self.channel_id.startswith("@") else ""
        return f"it-jobs-india-bot/0.1{contact}"

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Config":
        env = os.environ if env is None else env
        return cls(
            database_url=env.get("DATABASE_URL", "").strip(),
            bot_token=env.get("TELEGRAM_BOT_TOKEN", "").strip(),
            channel_id=env.get("TELEGRAM_CHANNEL_ID", "").strip(),
            companies_file=env.get("COMPANIES_FILE", "").strip() or DEFAULT_COMPANIES_FILE,
            enable_unstop=_bool(env, "ENABLE_UNSTOP", True),
            unstop_pages=_int(env, "UNSTOP_PAGES", 20),
            skip_unpaid=_bool(env, "SKIP_UNPAID", True),
            max_job_age_days=_int(env, "MAX_JOB_AGE_DAYS", 10),
            company_cooldown_hours=_int(env, "COMPANY_COOLDOWN_HOURS", 0),
            repost_cooldown_days=_int(env, "REPOST_COOLDOWN_DAYS", 30),
            post_interval_minutes=_int(env, "POST_INTERVAL_MINUTES", 0),
            max_posts_per_day=_int(env, "MAX_POSTS_PER_DAY", 0),
            quiet_start_hour=_int(env, "QUIET_START_HOUR", 0),
            quiet_end_hour=_int(env, "QUIET_END_HOUR", 0),
            dry_run=_bool(env, "DRY_RUN", False),
        )
