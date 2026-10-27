"""Workday career sites (many large companies: NVIDIA, Intel, Mastercard, Citi, ...).

Uses the JSON endpoints the public career site itself calls. Search is keyword-based, so
this collector is not `complete`: a job missing from one search hasn't necessarily closed.
Only titles that look entry-level and IT are opened (one detail request each), which keeps
the request count small.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import httpx

from jobbot import classify
from jobbot.collectors.base import parse_iso, strip_html
from jobbot.models import RawJob

QUERIES = ("intern India", "graduate India", "trainee India", "fresher India",
           "associate engineer India", "entry level India")
PAGE_SIZE = 20


def looks_relevant(title: str) -> bool:
    probe = RawJob(source="", source_job_id="", company="", title=title, url="")
    return (classify.is_it_role(probe) and not classify.SENIOR_RE.search(title)
            and bool(classify.INTERN_RE.search(title) or classify.ENTRY_RE.search(title)))


class WorkdayCollector:
    complete = False
    every_minutes = 180

    def __init__(self, host: str, tenant: str, site: str, company: str, client: httpx.Client):
        self.host, self.tenant, self.site, self.company, self.client = host, tenant, site, company, client
        self.name = f"workday:{tenant}:{site}"
        self.base = f"https://{host}/wday/cxs/{tenant}/{site}"

    def fetch(self) -> List[RawJob]:
        paths: Dict[str, str] = {}
        for query in QUERIES:
            resp = self.client.post(f"{self.base}/jobs", json={
                "appliedFacets": {}, "limit": PAGE_SIZE, "offset": 0, "searchText": query})
            resp.raise_for_status()
            for post in resp.json().get("jobPostings") or []:
                if post.get("externalPath") and looks_relevant(post.get("title") or ""):
                    paths[post["externalPath"]] = post["title"]
        jobs = []
        for path in paths:
            resp = self.client.get(f"{self.base}{path}")
            if resp.status_code != 200:
                continue
            job = self.parse_detail(resp.json(), path)
            if job:
                jobs.append(job)
        return jobs

    def parse_detail(self, payload: Dict[str, Any], path: str) -> Optional[RawJob]:
        info = payload.get("jobPostingInfo") or {}
        title = (info.get("title") or "").strip()
        if not title or info.get("posted") is False or info.get("canApply") is False:
            return None
        locations = [info.get("location") or ""] + list(info.get("additionalLocations") or [])
        locations = [loc for loc in locations if loc]
        alpha2 = (((info.get("jobRequisitionLocation") or {}).get("country") or {})
                  .get("alpha2Code"))
        if alpha2 == "IN" or any(classify.INDIA_RE.search(loc) for loc in locations):
            india: Optional[bool] = True
        else:
            india = False if alpha2 else None
        url = info.get("externalUrl") or f"https://{self.host}/{self.site}{path}"
        return RawJob(
            source=self.name, source_job_id=str(info.get("jobReqId") or info.get("id") or path),
            company=self.company, title=title, url=url, locations=locations,
            in_india=india,
            part_time=bool(re.search(r"part", str(info.get("timeType") or ""), re.I)),
            posted_at=parse_iso(info.get("startDate")),
            description=strip_html(info.get("jobDescription"))[:4000],
        )
