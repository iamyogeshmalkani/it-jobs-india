"""Public job-board APIs of applicant tracking systems: Greenhouse, Lever, Ashby, plus the
tools many smaller companies use: Workable, Recruitee and SmartRecruiters.

Each returns a company's whole board in unauthenticated GETs, so these collectors are
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

_WORKPLACE = {"onsite": MODE_ONSITE, "on-site": MODE_ONSITE, "on_site": MODE_ONSITE,
              "hybrid": MODE_HYBRID, "remote": MODE_REMOTE}


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


def _country_flags(codes: List[str]) -> Optional[bool]:
    """True if any listed country is India, False if countries are listed but none is, else None."""
    codes = [str(c).strip().upper() for c in codes if c]
    if not codes:
        return None
    return "IN" in codes or "INDIA" in codes


class WorkableCollector(_Board):
    """Workable's public careers widget feed: one GET returns a company's open jobs.
    The field names follow Workable's public widget response as documented by third parties."""

    kind = "workable"
    url_template = "https://apply.workable.com/api/v1/widget/accounts/{slug}"

    def parse(self, payload: Dict[str, Any]) -> List[RawJob]:
        jobs = []
        for item in payload.get("jobs") or []:
            title = (item.get("title") or "").strip()
            url = item.get("url") or item.get("shortlink") or ""
            job_id = item.get("shortcode") or item.get("id")
            if not title or not url or not job_id:
                continue
            places = list(item.get("locations") or [])
            if not places and (item.get("city") or item.get("country")):
                places = [item]
            locations, codes = [], []
            for place in places:
                country = str(place.get("country_name") or place.get("country") or "")
                name = ", ".join(str(b) for b in (place.get("city"), place.get("region"), country) if b)
                if name:
                    locations.append(name)
                codes.append(country)
            loc = item.get("location") if isinstance(item.get("location"), dict) else {}
            workplace = _workplace(loc.get("workplace_type") or item.get("workplace_type"))
            remote = item.get("telecommuting") or loc.get("telecommuting")
            employment = str(item.get("employment_type") or "")
            jobs.append(RawJob(
                source=self.name, source_job_id=str(job_id), company=self.company, title=title,
                url=url, locations=locations, in_india=_country_flags(codes),
                work_mode=workplace or (MODE_REMOTE if remote else None),
                job_type=TYPE_INTERNSHIP if re.search(r"\bintern", employment, re.I) else None,
                part_time=bool(re.search(r"part[- ]?time", employment, re.I)),
                posted_at=parse_iso(item.get("published_on") or item.get("created_at")),
            ))
        return jobs


class RecruiteeCollector(_Board):
    """Recruitee's careers-site API (`{slug}.recruitee.com/api/offers/`), no token needed."""

    kind = "recruitee"
    url_template = "https://{slug}.recruitee.com/api/offers/"

    @staticmethod
    def _time(value: Any) -> Optional[int]:
        """'2026-08-14 08:23:10 UTC' -> unix seconds."""
        text = str(value or "").strip()
        if text.endswith(" UTC"):
            text = text[:-4].replace(" ", "T") + "+00:00"
        return parse_iso(text)

    def parse(self, payload: Dict[str, Any]) -> List[RawJob]:
        jobs = []
        for item in payload.get("offers") or []:
            title, url = (item.get("title") or "").strip(), item.get("careers_url") or ""
            if not title or not url or item.get("id") is None:
                continue
            if item.get("status") not in (None, "published"):
                continue
            places = list(item.get("locations") or []) or [item]
            locations, codes = [], []
            for place in places:
                bits = [place.get("city"), place.get("country")]
                name = ", ".join(str(b) for b in bits if b) or str(place.get("location") or "")
                if name:
                    locations.append(name)
                codes.append(place.get("country_code"))
            code = str(item.get("employment_type_code") or "")
            mode = (MODE_REMOTE if item.get("remote") else MODE_HYBRID if item.get("hybrid")
                    else MODE_ONSITE if item.get("on_site") else None)
            jobs.append(RawJob(
                source=self.name, source_job_id=str(item["id"]), company=self.company, title=title,
                url=url, locations=locations, in_india=_country_flags(codes), work_mode=mode,
                job_type=TYPE_INTERNSHIP if re.search(r"intern|trainee", code, re.I) else None,
                part_time="part" in code.lower(),
                posted_at=self._time(item.get("published_at") or item.get("created_at")),
            ))
        return jobs


class SmartRecruitersCollector(_Board):
    """SmartRecruiters' public Posting API. It pages 100 at a time; a company with more than
    MAX_PAGES pages is only partly read, so `complete` is switched off for that fetch (a job
    missing from a partial list must not be treated as closed)."""

    kind = "smartrecruiters"
    url_template = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    PAGE = 100
    MAX_PAGES = 10

    def fetch(self) -> List[RawJob]:
        jobs: List[RawJob] = []
        offset, total = 0, 0
        for _ in range(self.MAX_PAGES):
            resp = self.client.get(self.url_template.format(slug=self.slug),
                                   params={"limit": self.PAGE, "offset": offset})
            resp.raise_for_status()
            payload = resp.json()
            jobs += self.parse(payload)
            total = int(payload.get("totalFound") or 0)
            offset += self.PAGE
            if offset >= total or not payload.get("content"):
                break
        self.complete = offset >= total
        return jobs

    def parse(self, payload: Dict[str, Any]) -> List[RawJob]:
        jobs = []
        for item in payload.get("content") or []:
            title, job_id = (item.get("name") or "").strip(), item.get("id")
            if not title or not job_id:
                continue
            place = item.get("location") or {}
            name = ", ".join(str(place[k]) for k in ("city", "region") if place.get(k))
            if place.get("country"):
                name = f"{name}, {place['country'].upper()}" if name else place["country"].upper()
            level = str((item.get("experienceLevel") or {}).get("id") or "")
            employment = " ".join(str((item.get("typeOfEmployment") or {}).get(k) or "")
                                  for k in ("id", "label"))
            is_intern = level == "internship" or bool(re.search(r"\bintern", employment, re.I))
            jobs.append(RawJob(
                source=self.name, source_job_id=str(job_id), company=self.company, title=title,
                url=f"https://jobs.smartrecruiters.com/{self.slug}/{job_id}",
                locations=[name] if name else [],
                in_india=_country_flags([place.get("country")]),
                work_mode=MODE_REMOTE if place.get("remote") else None,
                job_type=TYPE_INTERNSHIP if is_intern else None,
                entry_level=True if level in ("internship", "entry_level") else None,
                part_time=bool(re.search(r"part[- ]?time", employment, re.I)),
                posted_at=parse_iso(item.get("releasedDate")),
            ))
        return jobs


BOARDS = {c.kind: c for c in (GreenhouseCollector, LeverCollector, AshbyCollector,
                              WorkableCollector, RecruiteeCollector, SmartRecruitersCollector)}
