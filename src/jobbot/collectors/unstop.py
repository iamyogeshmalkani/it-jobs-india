"""Unstop (unstop.com): India's largest student opportunity platform.

Reads the newest open internships and jobs from the public listing endpoint that
unstop.com's own pages use (robots.txt allows `/api/public/`). Unstop states a work
mode, stipend/salary and an application deadline for each listing, so posts from here
carry the most detail. It is not `complete` (only the newest pages are read); listings
are closed by their deadline instead.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from jobbot.collectors.base import parse_iso, strip_html
from jobbot.models import (MODE_HYBRID, MODE_ONSITE, MODE_REMOTE, PAY_MONTH, PAY_YEAR,
                           TYPE_INTERNSHIP, TYPE_JOB, RawJob)

SEARCH = "https://unstop.com/api/public/opportunity/search-result"
KINDS = (("internships", TYPE_INTERNSHIP), ("jobs", TYPE_JOB))
PER_PAGE = 100
_MODES = {"wfh": MODE_REMOTE, "remote": MODE_REMOTE, "hybrid": MODE_HYBRID,
          "in_office": MODE_ONSITE, "on_field": MODE_ONSITE}
MAX_ENTRY_EXPERIENCE = 2  # years


def parse_unstop_date(value: Optional[str]) -> Optional[int]:
    """Handles ISO strings and Unstop's '2026-10-25 12:56:12 GMT+0530' format."""
    if not value:
        return None
    match = re.match(r"(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d) GMT([+-]\d{4})$", value.strip())
    if match:
        return int(datetime.strptime(" ".join(match.groups()), "%Y-%m-%d %H:%M:%S %z").timestamp())
    return parse_iso(value)


def _int(value: Any) -> Optional[int]:
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def parse_listing(item: Dict[str, Any], job_type: str) -> Optional[RawJob]:
    title = (item.get("title") or "").strip()
    url = item.get("seo_url") or item.get("public_url") or ""
    if not title or not url.startswith("https://") or item.get("id") is None:
        return None
    if item.get("regn_open") in (0, False) or str(item.get("status") or "LIVE").upper() != "LIVE":
        return None
    detail = item.get("jobDetail") or {}
    places = item.get("locations") or []
    cities = [p.get("city") for p in places if isinstance(p, dict) and p.get("city")]
    countries = {p.get("country") for p in places if isinstance(p, dict) and p.get("country")}
    mode = _MODES.get(str(detail.get("type") or ""))
    # Unstop is an Indian platform; a listing with no address (most remote ones) is Indian.
    india = "India" in countries if countries else True

    unpaid = detail.get("paid_unpaid") == "unpaid"
    show_pay = (not unpaid and detail.get("show_salary") in (1, True)
                and not detail.get("not_disclosed"))
    period = {"monthly": PAY_MONTH, "annually": PAY_YEAR}.get(str(detail.get("pay_in") or ""))
    max_exp = _int(detail.get("max_experience")) or _int(detail.get("min_experience"))

    return RawJob(
        source="unstop", source_job_id=str(item["id"]),
        company=((item.get("organisation") or {}).get("name") or "").strip() or "Unknown",
        title=title, url=url, locations=cities, in_india=india, work_mode=mode,
        job_type=job_type,
        entry_level=max_exp is None or max_exp <= MAX_ENTRY_EXPERIENCE,
        part_time=detail.get("timing") == "part_time",
        pay_min=_int(detail.get("min_salary")) if show_pay else None,
        pay_max=_int(detail.get("max_salary")) if show_pay else None,
        pay_period=period if show_pay else None,
        unpaid=unpaid,
        skills=[s.get("skill_name") or s.get("skill") for s in item.get("required_skills") or []
                if isinstance(s, dict) and (s.get("skill_name") or s.get("skill"))],
        categories=[w.get("name") for w in item.get("workfunction") or []
                    if isinstance(w, dict) and w.get("name")],
        posted_at=parse_unstop_date(item.get("approved_date")) or parse_iso(item.get("updated_at")),
        deadline=parse_iso(item.get("end_date")),
        description=strip_html(item.get("details"))[:4000],
    )


class UnstopCollector:
    name = "unstop"
    complete = False
    every_minutes = 60

    def __init__(self, client: httpx.Client, pages: int = 2):
        self.client, self.pages = client, pages

    def fetch(self) -> List[RawJob]:
        jobs: List[RawJob] = []
        for kind, job_type in KINDS:
            for page in range(1, self.pages + 1):
                resp = self.client.get(SEARCH, params={
                    "opportunity": kind, "page": page, "per_page": PER_PAGE, "oppstatus": "open"})
                resp.raise_for_status()
                data = (resp.json().get("data") or {})
                items = data.get("data") or []
                jobs += [j for j in (parse_listing(i, job_type) for i in items) if j]
                if len(items) < PER_PAGE // 2 or page >= int(data.get("last_page") or page):
                    break
        return jobs
