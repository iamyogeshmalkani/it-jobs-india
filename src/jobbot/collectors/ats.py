"""Public job-board APIs of applicant tracking systems: Greenhouse, Lever, Ashby.

Each returns a company's whole board in one unauthenticated GET, so these collectors are
`complete`: a job missing from the response has been taken down.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import httpx

from jobbot.collectors.base import parse_iso, strip_html
from jobbot.models import MODE_HYBRID, MODE_ONSITE, MODE_REMOTE, TYPE_INTERNSHIP, RawJob

GREENHOUSE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
LEVER = "https://api.lever.co/v0/postings/{slug}?mode=json"
ASHBY = "https://api.ashbyhq.com/posting-api/job-board/{slug}"

_WORKPLACE = {"onsite": MODE_ONSITE, "on-site": MODE_ONSITE, "hybrid": MODE_HYBRID,
              "remote": MODE_REMOTE}


def _workplace(value: Any) -> Optional[str]:
    return _WORKPLACE.get(str(value or "").strip().lower())


class _Board:
    url_template = ""
    every_minutes = 60
    complete = True

    def __init__(self, slug: str, company: str, client: httpx.Client):
        self.slug, self.company, self.client = slug, company, client
        self.name = f"{self.kind}:{slug}"

    kind = ""

    def fetch(self) -> List[RawJob]:
        resp = self.client.get(self.url_template.format(slug=self.slug))
        resp.raise_for_status()
        return self.parse(resp.json())

    def parse(self, payload: Any) -> List[RawJob]:
        raise NotImplementedError


class GreenhouseCollector(_Board):
    kind = "greenhouse"
    url_template = GREENHOUSE

    def parse(self, payload: Dict[str, Any]) -> List[RawJob]:
        jobs = []
        for item in payload.get("jobs") or []:
            title, url = (item.get("title") or "").strip(), item.get("absolute_url") or ""
            if not title or not url or item.get("id") is None:
                continue
            location = ((item.get("location") or {}).get("name") or "").strip()
            jobs.append(RawJob(
                source=self.name, source_job_id=str(item["id"]), company=self.company,
                title=title, url=url, locations=[location] if location else [],
                posted_at=parse_iso(item.get("first_published") or item.get("updated_at")),
                deadline=parse_iso(item.get("application_deadline")),
            ))
        return jobs


class LeverCollector(_Board):
    kind = "lever"
    url_template = LEVER

    def parse(self, payload: List[Dict[str, Any]]) -> List[RawJob]:
        jobs = []
        for item in payload if isinstance(payload, list) else []:
            title, url = (item.get("text") or "").strip(), item.get("hostedUrl") or ""
            if not title or not url or not item.get("id"):
                continue
            cats = item.get("categories") or {}
            locations = cats.get("allLocations") or ([cats["location"]] if cats.get("location") else [])
            commitment = str(cats.get("commitment") or "")
            created = item.get("createdAt")
            jobs.append(RawJob(
                source=self.name, source_job_id=str(item["id"]), company=self.company,
                title=title, url=url, locations=list(locations),
                in_india=True if item.get("country") == "IN" else None,
                work_mode=_workplace(item.get("workplaceType")),
                job_type=TYPE_INTERNSHIP if re.search(r"\bintern", commitment, re.I) else None,
                part_time=bool(re.search(r"part[- ]?time", commitment, re.I)),
                posted_at=int(created) // 1000 if isinstance(created, (int, float)) else None,
                description=(item.get("descriptionPlain") or "")[:4000],
            ))
        return jobs


class AshbyCollector(_Board):
    kind = "ashby"
    url_template = ASHBY

    def parse(self, payload: Dict[str, Any]) -> List[RawJob]:
        jobs = []
        for item in payload.get("jobs") or []:
            title, url = (item.get("title") or "").strip(), item.get("jobUrl") or ""
            if not title or not url or not item.get("id") or item.get("isListed") is False:
                continue
            places = [item] + list(item.get("secondaryLocations") or [])
            locations = [p.get("location") for p in places if p.get("location")]
            countries = [((p.get("address") or {}).get("postalAddress") or {}).get("addressCountry")
                         for p in places]
            employment = str(item.get("employmentType") or "")
            mode = _workplace(item.get("workplaceType"))
            jobs.append(RawJob(
                source=self.name, source_job_id=str(item["id"]), company=self.company,
                title=title, url=url, locations=locations,
                in_india=True if "India" in countries else None,
                work_mode=mode or (MODE_REMOTE if item.get("isRemote") else None),
                job_type=TYPE_INTERNSHIP if employment == "Intern" else None,
                part_time=employment == "PartTime",
                posted_at=parse_iso(item.get("publishedAt")),
                description=strip_html(item.get("descriptionPlain"))[:4000],
            ))
        return jobs


BOARDS = {c.kind: c for c in (GreenhouseCollector, LeverCollector, AshbyCollector)}
