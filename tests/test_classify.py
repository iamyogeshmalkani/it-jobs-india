import pytest

from conftest import make_job
from jobbot import classify
from jobbot.models import MODE_HYBRID, MODE_ONSITE, MODE_REMOTE, TYPE_INTERNSHIP, TYPE_JOB


@pytest.mark.parametrize("title, expected", [
    ("Software Development Engineer Intern", ""),
    ("Data Analyst Internship", ""),
    ("SDE-1 (Backend, Java)", ""),
    ("Graduate Engineer Trainee - IT", ""),
    ("Associate Software Engineer", ""),
    ("Junior Frontend Developer", ""),
    ("Software Engineer I", ""),
    ("Software Engineer II", "not_entry_level"),
    ("Senior Software Engineer", "not_entry_level"),
    ("Staff Software Engineer I", "not_entry_level"),
    ("Software Engineer", "not_entry_level"),  # no level stated: not posted as a fresher job
    ("Business Development Internship", "not_it"),
    ("Data Entry Operator Intern", "not_it"),
    ("HR Intern", "not_it"),
    ("Product and Brand Designer Internship", "not_it"),
    ("Trust and Safety Intern", "not_it"),
    ("Sales Engineer Intern", "not_it"),
    ("Mechanical Design Engineer Trainee", "not_it"),
    ("Production Engineering Internship", "not_it"),
    ("Make It Happen Intern", "not_it"),
    ("IT Bidding Executive", "not_it"),
    ("Web Researcher", "not_it"),
    ("Product Testing & Customer Success Internship", "not_it"),
    ("AI Research Intern", ""),
    ("ML Research Intern", ""),
    ("Market Research Intern", "not_it"),
])
def test_titles(title, expected):
    assert classify.classify(make_job(title=title)) == expected


def test_source_entry_level_flag_admits_unlevelled_title():
    assert classify.classify(make_job(title="Python Developer", entry_level=True)) == ""
    assert classify.classify(make_job(title="Senior Python Developer", entry_level=True)) == "not_entry_level"


def test_it_category_rescues_vague_title_but_not_non_it_title():
    assert classify.is_it_role(make_job(title="Tech Associate", categories=["Software Development"]))
    assert not classify.is_it_role(make_job(title="Sales Associate", categories=["Software Development"]))
    # Only the main (first) category counts.
    assert not classify.is_it_role(make_job(title="Associate Internship",
                                            categories=["Investment Research", "Software Development"]))


@pytest.mark.parametrize("locations, in_india, expected", [
    (["Bengaluru"], None, True),
    (["Hybrid in Bangalore, India"], None, True),
    (["IN, KA, Bengaluru"], None, True),
    (["Remote in San Francisco Bay Area"], None, False),
    (["Remote"], None, False),
    (["Remote"], True, True),  # the source says so
    (["Pune"], False, False),
])
def test_india(locations, in_india, expected):
    assert classify.in_india(make_job(locations=locations, in_india=in_india)) is expected


def test_outside_india_is_skipped():
    assert classify.classify(make_job(locations=["Shanghai"])) == "not_india"


def test_unpaid_skipped_only_when_configured():
    job = make_job(unpaid=True)
    assert classify.classify(job, skip_unpaid=True) == "unpaid"
    assert classify.classify(job, skip_unpaid=False) == ""


@pytest.mark.parametrize("text", [
    "A refundable security deposit of Rs 2000 is required",
    "Registration fee: ₹499 after selection",
    "Earn Rs 5,000 per day from home",
    "100% placement guaranteed",
    "Contact us on WhatsApp only",
])
def test_scam_signals(text):
    assert classify.classify(make_job(description=text)).startswith("scam_signal:")


def test_normal_description_is_not_a_scam():
    text = "Registration deadline is 9 Nov. Stipend paid monthly. Interview in two rounds."
    assert classify.classify(make_job(description=text)) == ""


def test_insecure_link_rejected():
    assert classify.classify(make_job(url="http://example.com/job")) == "bad_link"


@pytest.mark.parametrize("job, mode", [
    (make_job(locations=["Remote in India"]), MODE_REMOTE),
    (make_job(locations=["Hybrid in Bangalore, India"]), MODE_HYBRID),
    (make_job(locations=["Onsite in Bangalore"]), MODE_ONSITE),
    (make_job(locations=["Bengaluru"]), None),  # unknown: left out, not guessed
    (make_job(locations=["Remote"], work_mode=MODE_HYBRID), MODE_HYBRID),
])
def test_work_mode(job, mode):
    assert classify.work_mode(job) == mode


def test_job_type_and_cities():
    assert classify.job_type(make_job(title="Backend Internship")) == TYPE_INTERNSHIP
    assert classify.job_type(make_job(title="SDE 1")) == TYPE_JOB
    assert classify.job_type(make_job(title="AI Developer Internship", job_type=TYPE_JOB)) == TYPE_INTERNSHIP
    job = make_job(locations=["Bangalore, India", "Gurgaon", "bengaluru"])
    assert classify.cities(job) == ["Bengaluru", "Gurugram"]
