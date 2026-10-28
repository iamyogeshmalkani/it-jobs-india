from urllib.parse import parse_qs, urlparse

from conftest import DAY, HOUR, NOW, make_job
from jobbot.composer import FOOTER, compose, hashtags, location_line
from jobbot.india import format_deadline, format_inr, lakhs
from jobbot.models import MODE_HYBRID, MODE_REMOTE, PAY_MONTH, PAY_YEAR, TYPE_JOB


def test_internship_post_has_only_given_fields():
    job = make_job(title="Backend Intern <Go>", company="R&D Labs", locations=["Pune"])
    post = compose(job, NOW)
    assert post.text.startswith("🎓 <b>INTERNSHIP</b>")
    assert "<b>Backend Intern &lt;Go&gt;</b>" in post.text and "🏢 R&amp;D Labs" in post.text
    assert "📍 Pune" in post.text
    for absent in ("💰", "⏳", "🛠", "via"):
        assert absent not in post.text
    assert post.text.endswith(FOOTER)
    apply, share = post.keyboard[0]
    assert len(post.keyboard) == 1 and apply == {"text": "Apply now", "url": "https://jobs.example.com/1"}
    assert share["text"] == "📤 Share"


def test_share_button_shares_channel_with_job_details():
    post = compose(make_job(title="Backend Intern", company="Acme Labs"), NOW, "https://t.me/itjobs_test")
    url = post.keyboard[0][1]["url"]
    parts = urlparse(url)
    assert parts.netloc == "t.me" and parts.path == "/share/url"
    query = parse_qs(parts.query)
    assert query["url"] == ["https://t.me/itjobs_test"]
    assert "Backend Intern at Acme Labs" in query["text"][0]
    assert "https://jobs.example.com/1" in query["text"][0]


def test_share_button_without_public_channel_shares_the_job():
    url = compose(make_job(), NOW, "").keyboard[0][1]["url"]
    assert parse_qs(urlparse(url).query)["url"] == ["https://jobs.example.com/1"]


def test_unstop_style_post():
    job = make_job(source="unstop", title="Data Science Internship", locations=[],
                   work_mode=MODE_REMOTE, in_india=True, pay_min=7000, pay_max=12000,
                   pay_period=PAY_MONTH, deadline=NOW + 13 * DAY, skills=["Python", "SQL"],
                   part_time=True)
    text = compose(job, NOW).text
    assert "🎓 <b>INTERNSHIP</b> · Part-time" in text
    assert "📍 Remote (India)" in text
    assert "💰 Stipend: ₹7,000–₹12,000/month" in text
    assert "⏳ Apply by 9 Nov" in text and "closes in" not in text
    assert "🛠 Python, SQL" in text
    assert "(via Unstop)" in text


def test_job_salary_in_lpa_and_countdown():
    job = make_job(title="QA Engineer", job_type=TYPE_JOB, pay_min=400000, pay_max=700000,
                   pay_period=PAY_YEAR, deadline=NOW + 20 * HOUR, work_mode=MODE_HYBRID)
    text = compose(job, NOW).text
    assert text.startswith("💼 <b>ENTRY-LEVEL JOB</b>")
    assert "💰 Salary: ₹4–7 LPA" in text
    assert "📍 Bengaluru · Hybrid" in text
    assert "(closes in 20 h)" in text


def test_single_salary_value():
    job = make_job(title="SDE 1", job_type=TYPE_JOB, pay_min=600000, pay_max=600000,
                   pay_period=PAY_YEAR)
    assert "💰 Salary: ₹6 LPA" in compose(job, NOW).text


def test_location_lines():
    assert location_line(make_job(locations=[])) == "📍 India"
    many = make_job(locations=["Pune", "Mumbai", "Chennai", "Hyderabad", "Noida"])
    assert location_line(many) == "📍 Pune, Mumbai, Chennai +2 more"
    assert location_line(make_job(locations=["Delhi"], work_mode=MODE_REMOTE)) == "📍 Remote (India) · Delhi"


def test_hashtags():
    job = make_job(title="Full Stack Developer Intern (React, Node)", locations=["Bangalore"],
                   work_mode=MODE_REMOTE)
    assert hashtags(job) == "#internship #remote #bengaluru #react #nodejs #fullstack"
    assert hashtags(make_job(title="SDE 1", job_type=TYPE_JOB)).startswith("#fresherjobs")


def test_closed_text_strikes_title_and_drops_link():
    post = compose(make_job(), NOW)
    assert post.closed_text.startswith("❌ <b>CLOSED</b>")
    assert "<s>Software Engineer Intern</s>" in post.closed_text
    assert "href" not in post.closed_text


def test_india_formatting():
    assert format_inr(149999) == "₹1,49,999" and format_inr(15000) == "₹15,000"
    assert lakhs(450000) == "4.5" and lakhs(1200000) == "12"
    assert format_deadline(NOW + 3 * DAY, NOW) == "Apply by 30 Oct"
    assert format_deadline(NOW + 5 * HOUR, NOW) == "Apply by 27 Oct (closes in 5 h)"
