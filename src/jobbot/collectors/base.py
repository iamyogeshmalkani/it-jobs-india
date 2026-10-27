from __future__ import annotations

import html
import re
from datetime import date, datetime, timezone
from typing import List, Optional, Protocol

from jobbot.models import RawJob


class Collector(Protocol):
    """A job source. `fetch` must not raise for a single bad item; the pipeline isolates
    whole-collector failures so one broken source never stops the run."""

    name: str  # unique source key, stored with every job
    complete: bool  # fetch returns every open job, so a job that disappears has closed
    every_minutes: int  # minimum gap between fetches (be polite to the source)

    def fetch(self) -> List[RawJob]: ...


def parse_iso(value: Optional[str]) -> Optional[int]:
    """ISO-8601 timestamp or date -> unix seconds. Naive values are taken as UTC."""
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        if len(text) == 10:
            parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
        else:
            # Python 3.9 accepts only 3 or 6 fractional digits.
            text = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], text)
            parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def strip_html(value: Optional[str]) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()
