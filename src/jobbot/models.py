"""Core data types shared across collectors, classifier, composer, and publisher."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

TYPE_INTERNSHIP = "internship"
TYPE_JOB = "job"

MODE_ONSITE = "onsite"
MODE_HYBRID = "hybrid"
MODE_REMOTE = "remote"

PAY_MONTH = "month"
PAY_YEAR = "year"


@dataclass
class RawJob:
    """A job as reported by a source. Fields a source doesn't give stay None and are
    inferred (or left out of the post); nothing is ever guessed into a claim."""

    source: str  # collector name, e.g. "greenhouse:hackerrank", "unstop"
    source_job_id: str
    company: str
    title: str
    url: str
    locations: List[str] = field(default_factory=list)  # as given: "Bengaluru", "Remote - India"
    in_india: Optional[bool] = None  # source states the country; None = infer from locations
    work_mode: Optional[str] = None  # onsite | hybrid | remote; None = infer or leave out
    job_type: Optional[str] = None  # internship | job; None = infer from the title
    entry_level: Optional[bool] = None  # source says it is for students/freshers
    part_time: bool = False
    pay_min: Optional[int] = None  # whole rupees
    pay_max: Optional[int] = None
    pay_period: Optional[str] = None  # month | year
    unpaid: bool = False
    skills: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)  # source tags, e.g. Unstop work functions
    posted_at: Optional[int] = None  # unix seconds, when the source published it
    deadline: Optional[int] = None  # unix seconds, last day to apply
    description: str = ""  # plain text, used only for classification

    @property
    def via(self) -> str:
        """The platform behind the link, shown on aggregator posts ("" for company sites)."""
        return "Unstop" if self.source == "unstop" else ""


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def dedupe_key(job: RawJob) -> str:
    """Same company + same title = same opening, whichever source it came from."""
    company = re.sub(r"\b(private|pvt|limited|ltd|llp|inc|technologies|technology|careers)\b",
                     "", norm(job.company))
    return f"{' '.join(company.split())}|{norm(job.title)}"
