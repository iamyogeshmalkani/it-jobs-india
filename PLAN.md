# IT Jobs & Internships Telegram Channel: Development Plan

Goal: an automated Telegram channel that posts **fresh, genuine IT jobs and internships in India (plus India-eligible remote roles)** every hour, for students, freshers, and experienced professionals. It reuses the `dealbot` architecture from `crazy-deals-india` (GitHub Actions cron, Postgres, collectors, scorer, composer, review queue, auto-expire) at ₹0 infrastructure cost.

---

## 1. Principles

1. **Trust first.** Job scams are common in India: fake "work from home" jobs, registration fees, and Telegram "task" jobs. A single scam post can ruin the channel's reputation. Every post must link to a company careers page, an ATS (Greenhouse, Lever, etc.), or a reputable job board. We never post jobs that ask for a fee, or jobs whose only contact is a WhatsApp or Telegram number.
2. **Fresh only.** A job counts as "new" the first time we see it, and we post only jobs seen within the last 72 hours. When the source shows a job is closed, the post is edited to "❌ Closed" (same idea as "DEAL KHATAM").
3. **Use sources the way they allow.** Prefer official or public APIs. Scrape only where robots.txt **and** the terms of service allow it. Give attribution and links wherever the source requires them.
4. **Quality over volume.** Post once an hour during the day. Better 5 good jobs than 50 stale ones.

---

## 2. Where jobs come from

I tested every source marked ✅ below on 2026-10-27, and each returned live data. Sources marked ⚠️ need a check before you build on them.

### Tier 1: Public ATS APIs (no key, best quality, direct apply links)

Most tech companies publish their open roles through an applicant tracking system (ATS) that has a public JSON endpoint. This should be the **main source**. We keep a curated list of companies that hire in India and poll their boards.

| ATS | Endpoint | Verified examples (total jobs / India jobs) |
|---|---|---|
| Greenhouse ✅ | `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs` | Razorpay 27/22, Groww 10/10, Druva 31/12, Databricks 894/84, MongoDB 364/82, Stripe 711/46, GitLab 237/28 |
| Lever ✅ | `https://api.lever.co/v0/postings/{slug}?mode=json` | CRED 10, Meesho 54 |
| Ashby ✅ | `https://api.ashbyhq.com/posting-api/job-board/{slug}` | Sarvam 45, Atlan 7 |
| SmartRecruiters ✅ | `https://api.smartrecruiters.com/v1/companies/{id}/postings?country=in` | Bosch 624 in India |
| Amazon Jobs ✅ (undocumented) | `https://www.amazon.jobs/en/search.json?country=IND` | 2,227 India jobs |
| Workday / other career sites ⚠️ | Undocumented JSON per company | Many MNCs (banks, product companies). Treat as scraping (Tier 4) |

Why this tier wins:
- Each job has a stable ID and a direct apply URL, and when a job closes it disappears from the board. That makes the auto-"Closed" edit reliable.
- Job data comes straight from the employer, so the scam risk is near zero.
- Hourly polling of about 300 boards is about 300 light GET requests, which is polite and fits easily inside a GitHub Actions run.

**Company list (`data/companies.yaml`):** Start with 150-300 companies: Indian startups (fintech, SaaS, quick commerce, AI) and MNCs with Indian offices. Add a small `discover` script that tries each company name against the Greenhouse, Lever, Ashby, and SmartRecruiters slugs and saves the ones that return jobs. Many slugs are not the plain company name. For example, Razorpay's Greenhouse slug is `razorpaysoftwareprivatelimited`, and `phonepe` and `postman` on Greenhouse returned 0 jobs, so they likely use another ATS.

### Tier 2: Aggregator APIs (key required, wider coverage including non-startup roles)

| Source | Notes |
|---|---|
| Adzuna ⚠️ | Free developer key (`app_id` + `app_key`). URLs are `/v1/api/jobs/{country}/search/{page}`. The official overview page shows only `gb`, so confirm that `in` works with your key. One third-party SDK reports a limit of 25 calls/min and 250/day. Confirm in the [developer docs](https://developer.adzuna.com/overview) and terms. |
| Jooble ⚠️ | Free partner key from jooble.org/api/about. POST with keywords and location ([docs](https://jooblehelpcenter.freshdesk.com/en/support/solutions/articles/60001448238-rest-api-documentation)). Confirm India coverage. |
| JSearch on RapidAPI ⚠️ | Pulls from Google for Jobs, so its India coverage is strong. The free tier is small and paid plans cost money. Use only if Tier 1 and Tier 2 aren't enough. |

Aggregator links often point to another job board rather than the employer. Score these lower than Tier 1 and apply the anti-scam filters (§5).

### Tier 3: Remote-job APIs (global roles that hire from India)

| Source | Terms (from the API response or docs) |
|---|---|
| Remotive ✅ `remotive.com/api/remote-jobs` | **Poll at most 4 times a day.** Jobs arrive 24 h late. You must link back to Remotive and name it as the source. |
| Remote OK ✅ `remoteok.com/api` | Link back to Remote OK and name it as the source. Do not use their logo. |
| Himalayas ✅ `himalayas.app/jobs/api` | Read their API terms before launch. |
| Jobicy ✅ `jobicy.com/api/v2/remote-jobs` | Read their API terms before launch. |
| HN "Who is hiring" ✅ via the `hn.algolia.com` API | Monthly thread. Filter comments mentioning India, Bengaluru, or "REMOTE (Worldwide)". |
| Arbeitnow ✅ | Mostly European jobs, so low value here. Skip at launch. |

Filter strictly: a remote job is posted only if it says Worldwide, APAC, or India, never US-only.

### Tier 4: Careful scraping (only where robots.txt and the terms allow it)

| Source | Status |
|---|---|
| Unstop ⚠️ | Its robots.txt allows `/internship/` and `/job/` but disallows `/api/*`. Read the terms of service before scraping, or better, email them about a partnership. Strong for student internships and hackathons. |
| Company career pages (Workday etc.) ⚠️ | Fetch politely (1 request every few seconds, a clear User-Agent) and check each site's robots.txt. |
| Government ⚠️ | National Career Service (ncs.gov.in), PM Internship Scheme, Apprenticeship India. Check for RSS feeds or open data first. |

### Do NOT scrape

| Source | Why |
|---|---|
| **LinkedIn** | Its robots.txt says automated access without express permission is "strictly prohibited". The legal risk is high and they actively block bots. |
| **Internshala** | Its terms prohibit "automated systems, software, bots, spiders, scripts", "data mining", and "retransmitting" content. Instead, ask them about an affiliate or partner program, or post manually with links. |
| **Naukri, Indeed, Foundit, Instahyre, Wellfound** | No public API, and they use anti-bot measures. Read each site's terms before even considering it. Use only manual curation with a link back. |
| **Other Telegram channels** | Copying or forwarding their posts takes their content and reposts unverified jobs. |

### Tier 5: Manual and community intake (reuses `intake.py`)

- Send a careers link to the bot privately, and it creates a review card (same flow as Amazon deals today).
- Later, add a `/submit` form for recruiters and referrals. These always go through review, never auto-post.

---

## 3. Hourly flow

```
GitHub Actions cron "7 * * * *"  (hourly; :07 avoids GitHub's top-of-hour congestion)
        │
        ├─ 1. review taps     (Approve/Reject from the review chat; same as dealbot)
        ├─ 2. collect         each source has its own cadence stored in kv:
        │                       ATS boards: every run · Adzuna/Jooble: every run within quota
        │                       Remotive: every 6 h · HN: daily
        ├─ 3. normalize       → jobs table; first_seen_at = now if new
        ├─ 4. filter + score  IT role? India/remote-eligible? fresh? scam flags? duplicate?
        ├─ 5. queue           review chat (Phase 1) / auto-approve high scores (Phase 2)
        ├─ 6. publish         1 post per hour (07:00-00:00 IST) = ~17 posts/day
        └─ 7. expire          jobs gone from their ATS board → edit post "❌ Closed"
```

**What one hourly post contains:** Recommended format is a **digest of the top 3-5 new jobs**, mixed so each post has something for students and something for experienced people. Single-job posts are easier to share, but at only one post per hour they would show just 17 jobs a day. You could also alternate: digests during the day plus one "🔥 Featured" single post at 10:00 and 19:00.

**Seed the database before going live.** The first run must load every current job **without posting** (a backfill). Otherwise the first post would treat hundreds of old jobs as "new".

**Cron reliability:** GitHub cron can start several minutes late and pauses scheduled workflows in inactive repos, the same caveat as the deals bot. Hourly posting tolerates a few minutes of drift fine.

---

## 4. Reusing `dealbot` (what changes)

| dealbot file | jobbot equivalent |
|---|---|
| `collectors/base.py` | Same `Collector` protocol, now returning `RawJob`. New collectors: `greenhouse.py`, `lever.py`, `ashby.py`, `smartrecruiters.py`, `amazon_jobs.py`, `adzuna.py`, `jooble.py`, `remotive.py`, `remoteok.py`, `hn.py` |
| `collectors/rss.py`, `manual.py` | Kept as they are (manual JSON + any job RSS feeds) |
| `models.py` | `RawDeal` → `RawJob` (below) |
| `scorer.py` | Filters, scoring, and anti-scam checks (§5) instead of price history |
| `composer.py` | Job card / digest templates (§6) |
| `links.py` | Instead of affiliate tagging: a **domain allowlist** (ATS + known boards + verified company domains), so the publisher refuses any other link, plus `utm_source=<channel>`. Same "never post a link that is not ours" rule, adapted. |
| `pipeline.py` | Same 5 stages. `expire_posted` checks whether the job still exists at its source |
| `intake.py` | Accepts careers or job URLs instead of Amazon links |
| `india.py`, `telegram.py`, `db.py`, `config.py`, `cli.py` | Reused almost unchanged (IST, quiet hours, Bot API, repo, env config, `demo`/`check`/`run`) |
| `.github/workflows/dealbot.yml` | `jobbot.yml` with cron `7 * * * *` and the new secrets |

### Data model

```python
@dataclass
class RawJob:
    source: str            # greenhouse | lever | adzuna | remotive | manual ...
    source_job_id: str     # stable id from the source
    company: str
    title: str
    apply_url: str
    locations: list[str]   # ["Bengaluru", "Remote - India"]
    remote: str | None     # onsite | hybrid | remote_india | remote_global
    job_type: str | None   # internship | fulltime | contract
    exp_min: int | None    # years, parsed from title/description
    exp_max: int | None
    salary_text: str | None   # only if the source gives it, never estimated
    stipend_text: str | None
    skills: list[str]      # extracted keywords: python, react, java, devops ...
    posted_at: int | None  # from the source if given
    description: str | None
```

Tables: `companies(slug, ats, name, active, last_ok_at)`, `jobs(id, source, source_job_id, company, title, url, …, first_seen_at, last_seen_at, closed_at, dedupe_key)`, `posts(id, tg_message_id, job_ids[], sent_at)`, `kv` (cron state, per-source last-run).

---

## 5. Filtering, scoring, and anti-scam rules

**Gates (all must pass):**
1. **IT role:** the title matches an allowlist (software/SDE, frontend/backend/full-stack, mobile, data/ML/AI, DevOps/SRE/cloud, QA/SDET, security, product/design for tech, IT support) and none of the blocklist (sales, BPO/voice, "data entry", "typing").
2. **Location:** an Indian city, "India", or remote eligible from India.
3. **Fresh:** first seen ≤72 h ago (or source `posted_at` ≤7 days).
4. **Not a duplicate:** `dedupe_key = norm(company) + norm(title) + city`. If the same job appears in several sources, keep the direct ATS link.
5. **Not posted before:** never repost the same `dedupe_key` within 30 days.

**Anti-scam (any one sends the job to manual review, never auto-post):**
- The text mentions a fee, deposit, "registration charges", or "security amount".
- The only contact is WhatsApp or Telegram, or a personal email (gmail/yahoo) for a "company" job.
- Unrealistic pay ("earn ₹50,000/week from home"), "no interview", or "100% placement guaranteed".
- The link domain is not on the allowlist (Tier 2/4 sources).

**Score (orders the queue):** source trust (ATS > aggregator > scraped) + freshness + known company + experience bucket the channel needs right now (keeps a student/pro balance) + stated salary/stipend + remote-friendliness.

**Experience buckets** (parsed from the title and description: "intern", "fresher", "0-2 years", "SDE-1", "Senior", "Staff"):
`#internship` · `#fresher` (0-1 y) · `#junior` (1-3 y) · `#mid` (3-6 y) · `#senior` (6 y+)

---

## 6. Post format

Recommended language is **English** (IT audience), with optional short Hinglish hooks. That is an open decision; the deals bot defaults to Hinglish.

**Hourly digest**
```
🧑‍💻 New IT jobs · 3 PM IST

1️⃣ Software Engineer Intern — Razorpay
📍 Bengaluru · 🎓 Internship · #internship #backend
👉 Apply: <link>

2️⃣ SDE-1 (Backend, Java) — Meesho
📍 Bengaluru · 🧭 0-2 yrs · #fresher #java
👉 Apply: <link>

3️⃣ Senior DevOps Engineer — MongoDB
📍 Gurugram / Hybrid · 🧭 6+ yrs · #senior #devops
👉 Apply: <link>

🔔 Never pay for a job. We never charge to apply.
```

Rules:
- Only show salary or stipend if the source states it. Never estimate it.
- Hashtags for type, experience, city, and stack, so users can search the channel (`#bengaluru #react`).
- When a source requires attribution, add it on the job line ("via Remotive", with their URL as the link).
- When a job closes, edit its line to "❌ Closed". The post stays honest, and readers learn to apply quickly, which creates real urgency like the deals channel.
- Pinned message: what the channel is, "we never charge any fee", and how to report a suspicious post.

---

## 7. Phases

### Phase 0: Setup (1-2 days)
- Create a new channel and bot (or reuse the bot), a new Postgres DB or schema, and a new repo `it-jobs-india` forked from the dealbot structure.
- Apply for Adzuna and Jooble keys. Email Unstop and Internshala about partner or affiliate access.
- **Done when:** the bot posts a hard-coded digest to a private test channel.

### Phase 1: ATS MVP (week 1)
- Collectors: Greenhouse, Lever, Ashby, SmartRecruiters, Amazon Jobs. A `discover` script and `companies.yaml` with about 150 companies.
- Normalizer, the `jobs` table, backfill mode, IT/location gates, dedupe.
- Digest composer and the hourly cron. Every post goes through the review chat (Approve/Reject).
- **Done when:** 17 hourly posts a day go out with working apply links, and closed jobs get edited.

### Phase 2: Breadth and automation (weeks 2-3)
- Adzuna, Jooble, Remotive, Remote OK, Himalayas, Jobicy, and HN collectors, each with its own cadence and quota guard.
- Experience-bucket parser, anti-scam rules, and auto-approve for Tier 1 jobs above a score threshold. Tier 2-4 and anything with a scam flag stay in manual review.
- Click tracking through your own redirect (Cloudflare Worker, as planned for dealbot Phase 2).
- **Done when:** the channel runs unattended for 3 days with no scam or stale posts.

### Phase 3: Growth (weeks 4-6)
- Interactive bot: `/alerts react bengaluru fresher`, which DMs matching jobs (store minimal data; `/deleteme` for the DPDP Act).
- Daily "Top 10 internships" and weekly "Remote jobs for Indians" round-ups.
- Split the channel if it grows (e.g. **@…Internships & Freshers** and **@…Experienced**), all fed by the same pipeline with filters per channel.
- Share in college groups and placement cells, and collaborate with other tech communities.

### Phase 4: Monetize (month 2+)
- Labelled sponsored job posts from startups and recruiters (verify the company, never charge candidates).
- Affiliate links for courses and certifications (clearly labelled, and kept separate from job posts).
- Publisher/pay-per-click programs from aggregators if they offer them in India (check Adzuna and Jooble).
- Telegram ad revenue share or Stars for a premium "early alerts" tier.

---

## 8. Metrics

| Metric | Why |
|---|---|
| Subscribers, daily growth | Audience |
| Views per post / subscribers | Engagement |
| Apply clicks per job (redirect) | Which sources and companies people want |
| Clicks by bucket (intern/fresher/senior) | Tunes the student/pro mix |
| Closed-within-24h rate | Freshness of sources |
| Scam reports | Must stay at 0 |
| Unsubscribes after posts | Over-posting signal |

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Posting a scam job | Tier 1 first, domain allowlist, scam rules → manual review, "never pay" footer, report button |
| Breaking a source's terms | Only APIs and robots/terms-checked pages; respect polling limits (Remotive ≤4/day); attribution where required |
| ATS slug changes, or a company switches ATS | `companies.last_ok_at`; the weekly `discover` re-check flags boards that are dead or empty |
| Remote jobs that aren't open to India | A strict regex for Worldwide/APAC/India; drop US-only, EU-only, and "must be authorized to work in…" |
| Empty hours (night, weekends) | Keep a small backlog of good unposted jobs ≤72 h old; skip the post rather than posting filler |
| Aggregator quotas | Per-source counters in `kv`; stop calling a source once its daily quota is reached |
| GitHub cron drift or pause | Same as dealbot: tolerate it, re-enable it from the Actions tab, optional external ping |

---

## 10. Decisions (2026-10-27)

1. **Audience:** internships and freshers only (entry level, ≤2 years).
2. **Format:** one job per post, hourly, 07:00-00:00 IST.
3. **Language:** English.
4. **Location:** India, on-site, hybrid and remote.
5. **Review:** fully automatic. No review queue; the filters in §5 run on every job, and anything with a scam signal is dropped.
6. **Repo:** a new repo (`it-jobs-india`), not a package inside `crazy-deals-india`.

### What testing changed

Measured on 2026-10-27, these findings revised §2:

- **Company boards have little entry-level supply.** 47 boards had about 1,450 India jobs but only about 45 intern/junior titles, and most weren't IT. They stay as a high-quality source, not the main one.
- **Unstop is the main source.** About 800 open listings, of which about 80 pass the filters (paid, IT, entry level). About 5-6 new ones a day.
- **Workday career sites** work for about 30 large companies (NVIDIA, Intel, Mastercard, Citi, …) and add a few roles a week.
- **Result:** about 50 postable jobs at launch, then about 6-8 a day. The bot posts hourly while it has jobs and skips empty hours. More volume needs an aggregator API key (Adzuna or Jooble, India coverage still to be confirmed) or more company boards.
