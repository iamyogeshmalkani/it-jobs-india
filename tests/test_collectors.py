from datetime import datetime, timezone

import pytest

from conftest import fixture
from jobbot import classify
from jobbot.collectors.ats import (AshbyCollector, GreenhouseCollector, LeverCollector,
                                    RecruiteeCollector, SmartRecruitersCollector,
                                    WorkableCollector)
from jobbot.collectors.base import parse_iso
from jobbot.collectors.unstop import parse_listing, parse_unstop_date
from jobbot.collectors.workday import WorkdayCollector, looks_relevant
from jobbot.india import IST
from jobbot.models import (MODE_HYBRID, MODE_ONSITE, MODE_REMOTE, PAY_MONTH, PAY_YEAR,
                           TYPE_INTERNSHIP, TYPE_JOB)


def test_parse_iso_variants():
    assert parse_iso("2026-10-01T05:54:08-04:00") == int(datetime(2026, 10, 1, 9, 54, 8, tzinfo=timezone.utc).timestamp())
    assert parse_iso("2026-04-17T11:46:39.214+00:00") == int(datetime(2026, 4, 17, 11, 46, 39, tzinfo=timezone.utc).timestamp())
    assert parse_iso("2026-10-13") == int(datetime(2026, 10, 13, tzinfo=timezone.utc).timestamp())
    assert parse_iso("2026-10-13T00:00:00Z") == parse_iso("2026-10-13")
    assert parse_iso("not a date") is None and parse_iso(None) is None


def test_greenhouse():
    jobs = GreenhouseCollector("hackerrank", "HackerRank", client=None).parse(fixture("greenhouse.json"))
    intern, remote_us, senior = jobs
    assert intern.title == "Software Development Engineer Intern" and intern.company == "HackerRank"
    assert intern.source == "greenhouse:hackerrank" and intern.url.startswith("https://")
    assert classify.classify(intern) == ""
    assert classify.work_mode(intern) == MODE_ONSITE
    assert intern.posted_at == parse_iso("2026-10-01T05:54:08-04:00")
    assert classify.classify(remote_us) == "not_india"
    assert classify.classify(senior) in ("not_it", "not_entry_level")


def test_lever():
    jobs = LeverCollector("fampay", "FamPay", client=None).parse(fixture("lever.json"))
    by_title = {j.title: j for j in jobs}
    copy_intern = by_title["Copy Intern"]
    assert copy_intern.in_india is True and copy_intern.job_type == TYPE_INTERNSHIP
    assert copy_intern.work_mode == MODE_ONSITE and copy_intern.locations == ["Bengaluru"]
    assert 1_500_000_000 < copy_intern.posted_at < 2_000_000_000  # ms converted to s
    assert classify.classify(copy_intern) == "not_it"
    assert classify.classify(by_title["Security Engineer Intern"]) == ""


def test_ashby():
    jobs = AshbyCollector("sarvam", "Sarvam", client=None).parse(fixture("ashby.json"))
    assert all(j.in_india for j in jobs)
    assert all(j.work_mode == MODE_ONSITE for j in jobs)
    assert jobs[0].posted_at is not None
    assert [classify.classify(j) for j in jobs] == ["not_it", "not_it", "not_it"]


# The three fixtures below (workable, recruitee, smartrecruiters) are hand-written from the
# vendors' documented response shapes, not captured live. Check them against a real response
# (`python -m jobbot discover "Company"`) before relying on a field.

def test_workable():
    jobs = WorkableCollector("acme-labs", "Acme Labs", client=None).parse(fixture("workable.json"))
    intern, senior, graduate = jobs  # the job with an empty title is dropped
    assert intern.source == "workable:acme-labs" and intern.source_job_id == "A1B2C3D4E5"
    assert intern.in_india is True and intern.locations == ["Pune, Maharashtra, India"]
    assert intern.job_type == TYPE_INTERNSHIP and intern.work_mode == MODE_HYBRID
    assert intern.posted_at == parse_iso("2026-10-24") and classify.classify(intern) == ""
    assert senior.in_india is False and senior.work_mode == MODE_ONSITE
    assert classify.classify(senior) == "not_india"
    assert graduate.work_mode == MODE_REMOTE and classify.classify(graduate) == ""


def test_recruitee():
    jobs = RecruiteeCollector("acme", "Acme", client=None).parse(fixture("recruitee.json"))
    intern, qa, junior = jobs  # the unpublished draft is dropped
    assert intern.url == "https://acme.recruitee.com/o/frontend-developer-intern-react"
    assert intern.in_india is True and intern.work_mode == MODE_HYBRID and intern.job_type == TYPE_INTERNSHIP
    assert intern.posted_at == int(datetime(2026, 10, 22, 8, 23, 10, tzinfo=timezone.utc).timestamp())
    assert classify.classify(intern) == ""
    assert qa.in_india is False and classify.classify(qa) == "not_india"
    assert junior.in_india is True and junior.part_time and junior.work_mode == MODE_REMOTE
    assert junior.locations == ["Hyderabad, India", "Lisbon, Portugal"]
    assert classify.classify(junior) == ""


def test_smartrecruiters():
    jobs = SmartRecruitersCollector("acmelabs", "Acme Labs", client=None).parse(
        fixture("smartrecruiters.json"))
    intern, senior, associate = jobs
    assert intern.url == "https://jobs.smartrecruiters.com/acmelabs/744000100000001"
    assert intern.in_india is True and intern.job_type == TYPE_INTERNSHIP
    assert intern.posted_at == parse_iso("2026-10-23T10:15:30.000Z") and classify.classify(intern) == ""
    assert senior.in_india is False and classify.classify(senior) == "not_india"
    assert associate.entry_level and associate.part_time and associate.work_mode == MODE_REMOTE
    assert classify.classify(associate) == ""


class _Resp:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class _Pages:
    """Fake HTTP client serving SmartRecruiters pages of one posting each."""

    def __init__(self, total, served):
        self.total, self.served = total, served

    def get(self, url, params=None):
        offset = params["offset"]
        self.served.append(offset)
        item = {"id": str(offset + 1), "name": "Software Intern",
                "location": {"city": "Pune", "country": "in"}}
        return _Resp({"totalFound": self.total, "content": [item] if offset < self.total else []})


def test_smartrecruiters_paging_and_completeness():
    served = []
    sr = SmartRecruitersCollector("acmelabs", "Acme", client=_Pages(250, served))
    sr.PAGE = 100  # three pages cover 250 postings (each fake page holds one)
    assert len(sr.fetch()) == 3 and served == [0, 100, 200] and sr.complete is True
    sr = SmartRecruitersCollector("acmelabs", "Acme", client=_Pages(10_000, []))
    sr.MAX_PAGES = 2
    sr.fetch()
    assert sr.complete is False  # partly read: a missing job must not count as closed


def test_build_collectors_knows_the_new_boards(tmp_path):
    from jobbot.collectors import build_collectors
    from jobbot.config import Config
    path = tmp_path / "companies.json"
    path.write_text('[{"name": "A", "ats": "workable", "slug": "a"},'
                    ' {"name": "B", "ats": "recruitee", "slug": "b"},'
                    ' {"name": "C", "ats": "smartrecruiters", "slug": "c"}]')
    cfg = Config(companies_file=str(path), enable_unstop=False)
    assert [c.name for c in build_collectors(cfg, client=None)] == [
        "workable:a", "recruitee:b", "smartrecruiters:c"]


def test_unstop_internships():
    items = fixture("unstop_internships.json")["data"]["data"]
    jobs = {j.title: j for j in (parse_listing(i, TYPE_INTERNSHIP) for i in items) if j}
    data = jobs["Data Analyst Internship"]
    assert data.source == "unstop" and data.via == "Unstop"
    assert data.job_type == TYPE_INTERNSHIP and data.work_mode == MODE_REMOTE and data.in_india
    assert data.pay_period == PAY_MONTH and data.pay_min and not data.unpaid
    assert data.deadline and data.posted_at and data.deadline > data.posted_at
    assert data.skills and "Data Analysis" in data.categories
    assert classify.classify(data) == ""

    unpaid = jobs["Software Development Internship"]
    assert unpaid.unpaid and unpaid.pay_min is None
    assert classify.classify(unpaid) == "unpaid"
    assert classify.classify(jobs["Business Development Internship"]) == "not_it"


def test_unstop_jobs():
    items = fixture("unstop_jobs.json")["data"]["data"]
    jobs = {j.title.strip(): j for j in (parse_listing(i, TYPE_JOB) for i in items) if j}
    qa = jobs["QA & Glific Developer"]
    assert qa.work_mode == MODE_HYBRID and qa.locations == ["Pune"] and qa.in_india
    assert (qa.pay_min, qa.pay_max, qa.pay_period) == (400000, 700000, PAY_YEAR)
    assert qa.entry_level and classify.classify(qa) == ""
    assert classify.classify(jobs["Data Entry Operator"]) == "not_it"
    assert classify.classify(jobs["Campus Hiring - GT Sales | 2027"]) == "not_it"


def test_unstop_skips_closed_listing():
    item = dict(fixture("unstop_jobs.json")["data"]["data"][0], regn_open=0)
    assert parse_listing(item, TYPE_JOB) is None


def test_unstop_experience_over_two_years_is_not_entry_level():
    item = fixture("unstop_jobs.json")["data"]["data"][1]
    item["jobDetail"] = dict(item["jobDetail"], min_experience=3, max_experience=5)
    assert parse_listing(item, TYPE_JOB).entry_level is False


def test_unstop_date_format():
    expected = int(datetime(2026, 10, 25, 12, 56, 12, tzinfo=IST).timestamp())
    assert parse_unstop_date("2026-10-25 12:56:12 GMT+0530") == expected
    assert parse_unstop_date("2026-10-25T12:56:12+05:30") == expected


def test_workday_detail():
    wd = WorkdayCollector("philips.wd3.myworkdayjobs.com", "philips", "jobs-and-careers", "Philips",
                          client=None)
    payload = fixture("workday_detail.json")
    panama = wd.parse_detail(payload, "/job/x")
    assert panama.in_india is False and classify.classify(panama) == "not_india"
    assert panama.posted_at == parse_iso("2026-09-22") and panama.part_time
    assert panama.url.startswith("https://philips.wd3.myworkdayjobs.com/")

    info = dict(payload["jobPostingInfo"], location="Pune",
                jobRequisitionLocation={"country": {"alpha2Code": "IN"}})
    pune = wd.parse_detail({"jobPostingInfo": info}, "/job/x")
    assert pune.in_india is True and classify.classify(pune) == ""


@pytest.mark.parametrize("title, relevant", [
    ("IT Infrastructure Intern", True),
    ("AI Imaging Data Scientist Intern", True),
    ("Production Engineering Internship", False),
    ("Sales, Key Account Manager- Mobile Surgery Solutions", False),
    ("Senior Software Engineer", False),
    ("Software Engineer", False),
])
def test_workday_prefilter(title, relevant):
    assert looks_relevant(title) is relevant


def test_workday_list_titles_prefilter():
    titles = [p["title"] for p in fixture("workday_list.json")["jobPostings"]]
    assert [looks_relevant(t) for t in titles] == [True, True, False, False]
