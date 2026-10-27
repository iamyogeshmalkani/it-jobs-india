"""Decide whether a job belongs in the channel: India, IT, entry level, not a scam.

Every rule here is a plain regex so a wrong decision is easy to trace and fix.
`classify` returns the reason a job was skipped ("" when it should be posted).
"""

from __future__ import annotations

import re
from typing import List, Optional

from jobbot.models import (MODE_HYBRID, MODE_ONSITE, MODE_REMOTE, TYPE_INTERNSHIP, TYPE_JOB,
                           RawJob)

CITIES = (
    "bengaluru|bangalore|mumbai|navi mumbai|thane|pune|hyderabad|secunderabad|chennai|kolkata|"
    "gurugram|gurgaon|noida|greater noida|new delhi|delhi|ncr|ahmedabad|gandhinagar|jaipur|"
    "kochi|cochin|thiruvananthapuram|trivandrum|coimbatore|indore|bhopal|chandigarh|mohali|"
    "lucknow|nagpur|vadodara|surat|visakhapatnam|vizag|bhubaneswar|mysuru|mysore|mangaluru|"
    "mangalore|nashik|goa|dehradun|patna|ranchi|guwahati|vijayawada|madurai|trichy|kanpur"
)
INDIA_RE = re.compile(rf"\b(india|{CITIES})\b", re.I)
_CITY_RE = re.compile(rf"\b({CITIES})\b", re.I)
CITY_CANONICAL = {"bangalore": "Bengaluru", "gurgaon": "Gurugram", "cochin": "Kochi",
                  "trivandrum": "Thiruvananthapuram", "mysore": "Mysuru", "vizag": "Visakhapatnam",
                  "mangalore": "Mangaluru", "new delhi": "Delhi", "secunderabad": "Hyderabad"}

INTERN_RE = re.compile(r"\bintern(ship)?s?\b|\btrainee\b|\bapprentice(ship)?\b", re.I)
ENTRY_RE = re.compile(
    r"\bfreshers?\b|\bgraduate\b|\bnew grad|\bentry[- ]level\b|\bjunior\b|\bjr\.?\s|\bcampus\b|"
    r"\buniversity hire|\bearly career|\b20\d\d (batch|passout|pass-out|graduates?)\b|"
    r"\bassociate (software|data|engineer|developer|consultant|analyst|qa|devops|cloud|ml)|"
    r"\b(sde|swe)[- ]?(1|i)\b|\b(engineer|developer|analyst)[- ](1|i)\b|"
    r"\b0\s*(-|to|–)\s*[12]\s*(yrs?|years?)\b", re.I)
SENIOR_RE = re.compile(
    r"\b(senior|sr\.?|lead|principal|staff|manager|director|head|architect|vp|vice president|"
    r"avp|chief|expert|specialist [2-9]|(engineer|developer|analyst|sde|swe)[- ]?(ii|iii|iv|[2-9]))\b",
    re.I)

IT_RE = re.compile(
    r"software|developer|\bdev\b|\bsde\b|\bswe\b|programmer|coder|full[- ]?stack|front[- ]?end|"
    r"back[- ]?end|\bweb\b|mobile app|android|\bios\b|flutter|react|angular|vue|node|python|"
    r"\bjava\b|golang|\bgo\b developer|\.net|dotnet|php|ruby|\brust\b|c\+\+|data scien|data analy|"
    r"data engineer|analytics engineer|machine learning|\bml\b|ai/ml|\bai (engineer|developer|"
    r"research)|artificial intelligence|deep learning|\bnlp\b|computer vision|\bllm|gen ?ai|"
    r"devops|\bsre\b|site reliability|cloud|\baws\b|azure|gcp|kubernetes|cyber|security engineer|"
    r"security analyst|information security|infosec|penetration|\bsoc\b|network engineer|"
    r"\bqa\b|quality assurance|test(ing)? engineer|\bsdet\b|automation test|tester|"
    r"it support|it infrastructure|system(s)? (engineer|administrator)|database|\bdba\b|\bsql\b|"
    r"ui ?/ ?ux|\bux\b|blockchain|web3|embedded software|firmware|"
    r"salesforce developer|sap (abap|developer)|erp developer|tech(nology)? intern|"
    r"computer science", re.I)
IT_UPPER_RE = re.compile(r"\bIT\b")  # case-sensitive: "IT Intern", not "make it happen"
NON_IT_RE = re.compile(
    r"\bsales\b|business development|\bbde\b|marketing|\bhr\b|human resource|people (ops|operations)|"
    r"recruit|talent acquisition|accountant|accounting|finance|financial|payroll|audit|\btax\b|"
    r"legal|counsel|telecall|tele-call|call(ing)? executive|customer (support|service|care|success)|"
    r"bidding|research(er)?\b(?! (engineer|scientist|intern))|"
    r"campus ambassador|content writ|copywrit|\bcopy\b|video edit|graphic design|\bbrand|social media|"
    r"data entry|operations executive|field|mechanical|civil|electrical|interior|teacher|tutor|"
    r"educator|faculty|procurement|supply chain|logistics|warehouse|nurse|pharma|medical|"
    r"chartered|\bca\b|\bmba\b|fashion|hospitality|chef|driver|receptionist|front office", re.I)
IT_CATEGORY_RE = re.compile(
    r"software|web development|full stack|front ?end|back ?end|mobile|app development|"
    r"data (science|analysis|analytics|engineering)|machine learning|artificial intelligence|"
    r"devops|cloud|cyber|security|qa engineering|testing|ui/ux", re.I)

SCAM_RE = re.compile(
    r"registration (fee|charge|amount)|security (deposit|amount|fee)|refundable (fee|deposit)|"
    r"training (fee|charge)s?|pay (a |the )?(fee|amount|deposit)|processing fee|"
    r"(whats ?app|telegram) (only|us at|me at|on \+?\d)|earn (rs\.?|₹|inr) ?[\d,]+ ?(per|/|a) ?(day|week)|"
    r"no interview|guaranteed (job|placement)|100% (job|placement)", re.I)

REMOTE_RE = re.compile(r"\bremote\b|work from home|\bwfh\b", re.I)
HYBRID_RE = re.compile(r"\bhybrid\b", re.I)
ONSITE_RE = re.compile(r"\bon-?site\b|\bin[- ]office\b", re.I)


def in_india(job: RawJob) -> bool:
    if job.in_india is not None:
        return job.in_india
    return any(INDIA_RE.search(loc) for loc in job.locations)


def job_type(job: RawJob) -> str:
    """An internship title wins over the source's section (Unstop lists some under jobs)."""
    if INTERN_RE.search(job.title):
        return TYPE_INTERNSHIP
    return job.job_type or TYPE_JOB


def work_mode(job: RawJob) -> Optional[str]:
    """onsite | hybrid | remote, or None when the source doesn't say."""
    if job.work_mode:
        return job.work_mode
    text = " ".join([job.title, *job.locations])
    if HYBRID_RE.search(text):
        return MODE_HYBRID
    if REMOTE_RE.search(text):
        return MODE_REMOTE
    if ONSITE_RE.search(text):
        return MODE_ONSITE
    return None


def cities(job: RawJob) -> List[str]:
    """Indian cities named in the locations, canonical spelling, in order, no repeats."""
    found: List[str] = []
    for loc in job.locations:
        for match in _CITY_RE.finditer(loc):
            raw = match.group(1).lower()
            name = CITY_CANONICAL.get(raw, raw.title())
            if name not in found:
                found.append(name)
    return found


def is_it_role(job: RawJob) -> bool:
    if NON_IT_RE.search(job.title):
        return False
    if IT_RE.search(job.title) or IT_UPPER_RE.search(job.title):
        return True
    # A vague title passes only if the source's main category (listed first) is IT.
    return bool(job.categories) and bool(IT_CATEGORY_RE.search(job.categories[0]))


def is_entry_level(job: RawJob, jtype: str) -> bool:
    if SENIOR_RE.search(job.title):
        return False
    if jtype == TYPE_INTERNSHIP or job.entry_level:
        return True
    return bool(ENTRY_RE.search(job.title))


def scam_reason(job: RawJob) -> str:
    match = SCAM_RE.search(f"{job.title}\n{job.description}")
    return f"scam_signal:{match.group(0).lower()}" if match else ""


def classify(job: RawJob, skip_unpaid: bool = True) -> str:
    """'' if the job belongs in the channel, otherwise the reason it doesn't."""
    if not job.url.startswith("https://"):
        return "bad_link"
    if not in_india(job):
        return "not_india"
    if not is_it_role(job):
        return "not_it"
    if not is_entry_level(job, job_type(job)):
        return "not_entry_level"
    if skip_unpaid and job.unpaid:
        return "unpaid"
    return scam_reason(job)
