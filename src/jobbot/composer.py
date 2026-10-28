"""Telegram post text (HTML) for one job. Every line comes from source data; a field
the source doesn't give is left out rather than guessed."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from typing import List, Optional
from urllib.parse import quote

from jobbot import classify
from jobbot.india import format_deadline, format_inr, lakhs
from jobbot.models import (MODE_HYBRID, MODE_ONSITE, MODE_REMOTE, PAY_MONTH, PAY_YEAR,
                           TYPE_INTERNSHIP, RawJob)

APPLY_LABEL = "Apply now"
SHARE_LABEL = "📤 Share"
FOOTER = "🚫 Never pay anyone to get a job or internship."
MAX_CITIES = 3
MAX_SKILLS = 4

# (hashtag, pattern over title + skills). Order is the order tags appear in.
STACK_TAGS = [
    ("python", r"\bpython\b"), ("java", r"\bjava\b"), ("javascript", r"javascript|\bjs\b"),
    ("react", r"\breact"), ("nodejs", r"\bnode"), ("angular", r"angular"),
    ("dotnet", r"\.net\b|dotnet"), ("php", r"\bphp\b"), ("golang", r"golang|\bgo\b"),
    ("android", r"android"), ("ios", r"\bios\b"), ("flutter", r"flutter"),
    ("fullstack", r"full[- ]?stack"), ("frontend", r"front[- ]?end"), ("backend", r"back[- ]?end"),
    ("datascience", r"data scien"), ("dataanalyst", r"data analy"), ("ml", r"machine learning|\bml\b"),
    ("ai", r"\bai\b|artificial intelligence|\bllm|gen ?ai"), ("devops", r"devops|\bsre\b"),
    ("cloud", r"cloud|\baws\b|azure|gcp"), ("cybersecurity", r"cyber|security"),
    ("testing", r"\bqa\b|\btest|sdet"), ("uiux", r"ui ?/ ?ux|\bux\b"),
    ("sql", r"\bsql\b"),
]
MAX_STACK_TAGS = 3


@dataclass
class Composed:
    text: str
    closed_text: str
    keyboard: List[List[dict]]


def _pay_line(job: RawJob) -> Optional[str]:
    low, high = job.pay_min, job.pay_max
    if not (low or high) or job.pay_period not in (PAY_MONTH, PAY_YEAR):
        return None
    low, high = low or high, high or low
    label = "Stipend" if classify.job_type(job) == TYPE_INTERNSHIP else "Salary"
    if job.pay_period == PAY_YEAR:
        amount = f"₹{lakhs(low)} LPA" if low == high else f"₹{lakhs(low)}–{lakhs(high)} LPA"
    else:
        amount = format_inr(low) if low == high else f"{format_inr(low)}–{format_inr(high)}"
        amount += "/month"
    return f"💰 {label}: {amount}"


def location_line(job: RawJob) -> str:
    names = classify.cities(job)
    shown = ", ".join(names[:MAX_CITIES]) + (f" +{len(names) - MAX_CITIES} more" if len(names) > MAX_CITIES else "")
    mode = classify.work_mode(job)
    if mode == MODE_REMOTE:
        return f"📍 Remote (India){' · ' + shown if shown else ''}"
    place = shown or "India"
    if mode == MODE_HYBRID:
        return f"📍 {place} · Hybrid"
    if mode == MODE_ONSITE:
        return f"📍 {place} · On-site"
    return f"📍 {place}"


def hashtags(job: RawJob) -> str:
    tags = ["internship" if classify.job_type(job) == TYPE_INTERNSHIP else "fresherjobs"]
    mode = classify.work_mode(job)
    if mode:
        tags.append({MODE_REMOTE: "remote", MODE_HYBRID: "hybrid", MODE_ONSITE: "onsite"}[mode])
    tags += [re.sub(r"[^a-z]", "", c.lower()) for c in classify.cities(job)[:2]]
    haystack = " ".join([job.title, *job.skills, *job.categories])
    stack = [tag for tag, pattern in STACK_TAGS if re.search(pattern, haystack, re.I)]
    tags += stack[:MAX_STACK_TAGS]
    return " ".join(f"#{t}" for t in dict.fromkeys(tags))


def share_button(job: RawJob, channel_url: str) -> dict:
    """Opens Telegram's share sheet. It shares the channel link (so friends can join) with the
    job's title and apply link as the message; without a public channel link it shares the job."""
    text = f"{job.title.strip()} at {job.company.strip()}\n{job.url}"
    if channel_url:
        text += "\n\nMore free IT internships & fresher jobs in India 👇"
    target = channel_url or job.url
    return {"text": SHARE_LABEL,
            "url": f"https://t.me/share/url?url={quote(target, safe='')}&text={quote(text, safe='')}"}


def compose(job: RawJob, now: int, channel_url: str = "") -> Composed:
    is_intern = classify.job_type(job) == TYPE_INTERNSHIP
    header = "🎓 <b>INTERNSHIP</b>" if is_intern else "💼 <b>ENTRY-LEVEL JOB</b>"
    if job.part_time:
        header += " · Part-time"
    title, company = escape(job.title.strip(), quote=False), escape(job.company.strip(), quote=False)

    lines = [header, "", f"<b>{title}</b>", f"🏢 {company}", location_line(job)]
    pay = _pay_line(job)
    if pay:
        lines.append(pay)
    if job.deadline:
        lines.append(f"⏳ {format_deadline(job.deadline, now)}")
    skills = [s.strip() for s in job.skills if s.strip()][:MAX_SKILLS]
    if skills:
        lines.append("🛠 " + escape(", ".join(skills), quote=False))

    link = escape(job.url, quote=True)
    apply = f'👉 <a href="{link}">Apply here</a>'
    if job.via:
        apply += f" (via {job.via})"
    lines += ["", apply, "", hashtags(job), FOOTER]

    closed = "\n".join(["❌ <b>CLOSED</b>: no longer accepting applications.", "",
                        f"<s>{title}</s>", f"🏢 {company}", "", hashtags(job)])
    keyboard = [[{"text": APPLY_LABEL, "url": job.url}, share_button(job, channel_url)]]
    return Composed("\n".join(lines), closed, keyboard)
