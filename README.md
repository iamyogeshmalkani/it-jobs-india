# jobbot: IT internships & fresher jobs in India, on Telegram

Every hour it collects internships and entry-level IT jobs in India (on-site, hybrid and
remote), drops anything that isn't IT, entry level, paid, or safe, and posts **one job**
to your channel in English. When a job closes, its post is edited to **❌ CLOSED**.
Fully automatic, no review step, ₹0 to run (GitHub Actions + free Postgres).

Built on the same architecture as [crazy-deals-india](https://github.com/iamyogeshmalkani/crazy-deals-india).

## What a post looks like

```
🎓 INTERNSHIP

Data Science Internship
🏢 Yugensoft Innovations
📍 Remote (India)
💰 Stipend: ₹7,000–₹12,000/month
⏳ Apply by 9 Nov
🛠 Python, SQL, Machine Learning Concepts, R (Programming Language)

👉 Apply here (via Unstop)

#internship #remote #python #datascience #ml
🚫 Never pay anyone to get a job or internship.
                                   [ Apply now ]
```

Lines only appear when the source gives the data. Pay, deadline and work mode are never guessed.

## Sources

| Source | What it gives | How |
|---|---|---|
| **Unstop** | Most of the volume: student internships and fresher jobs with stipend/salary, work mode, deadline | The public listing endpoint unstop.com's own pages use (`/api/public/`, allowed by its robots.txt) |
| **Company boards** (Greenhouse, Lever, Ashby) | Interns/new-grad roles at Razorpay, Groww, CRED, Meesho, Stripe, Databricks, MongoDB, … | Official public job-board APIs, no key |
| **Workday career sites** | Interns/graduates at NVIDIA, Intel, Mastercard, Citi, Deutsche Bank, Micron, … | The JSON the public career site calls; every 3 h |

The company list is `data/companies.json`, 75 boards that had India jobs when I tested them. Add more with `discover` (below).

Not used, on purpose: LinkedIn, Naukri, Indeed and Internshala. Their terms or robots.txt forbid automated collection.

## What gets posted

A job is posted only if **all** of these hold:

1. **India**: an Indian city, "India", or remote from India.
2. **IT**: the title names a tech role (developer, SDE, data, ML/AI, DevOps, cloud, QA, security, UI/UX, IT support …), or the source's main category is one. Sales, BD, HR, marketing, data entry, etc. are dropped even if the source tags them "tech".
3. **Entry level**: internship/trainee/apprentice, or a title such as graduate, fresher, junior, associate engineer, SDE-1, Engineer I. Unstop jobs count unless they ask for more than 2 years. Anything senior/lead/II+ is dropped. A plain "Software Engineer" with no level is dropped.
4. **Paid**: unpaid internships are skipped (`SKIP_UNPAID=0` to allow them).
5. **No scam signals**: fees, deposits, "WhatsApp only", "earn ₹X per day", "guaranteed placement".
6. **Fresh**: published in the last 10 days, and at least 12 h before its deadline.
7. **Not a repeat**: same company + title isn't posted twice within 30 days (across sources). At most one post per company every 12 h.

Order: newest first, company sites slightly ahead of aggregators, alternating internships and jobs.

## Volume: what to expect

Measured live on 2026-10-27:

- **About 50 jobs pass every filter at launch.** That's about three days of hourly posts.
- **About 6-8 new ones appear per day after that**, mostly from Unstop.

So the channel posts every hour while it has jobs, then **skips hours rather than posting filler**. To post more often, add sources (see "Next steps").

## Setup

1. **Channel**: create a public Telegram channel.
2. **Bot**: create one with @BotFather, or reuse your deals bot. Add it to the channel as **admin** with *Post messages* and *Edit messages of others*.
3. **Database**: any Postgres. Your deals bot's Supabase database works: tables here are prefixed `job_`. Or create a new free Supabase/Neon project.
4. **Check locally**:
   ```bash
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
   cp .env.example .env            # fill in the three required values
   PYTHONPATH=src .venv/bin/python -m jobbot check     # DB, bot, admin rights
   PYTHONPATH=src .venv/bin/python -m jobbot preview   # live fetch, prints what would be posted
   .venv/bin/python -m pytest                          # 93 tests
   ```
5. **Deploy**: push to a **public** GitHub repo (free Actions minutes), add `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, `DATABASE_URL` as repository **secrets**, and enable Actions. For a first trial, set the repository **variable** `DRY_RUN=1`. The run log shows the post without sending it. Then remove the variable.

GitHub pauses scheduled workflows in repos with no activity for 60 days. If the channel goes quiet, re-enable it from the Actions tab.

## Commands

| Command | What it does |
|---|---|
| `python -m jobbot run` | One cycle: collect due sources, close ended jobs, post at most one job |
| `python -m jobbot check` | Tests the database, bot token, and the bot's admin rights in the channel |
| `python -m jobbot preview [--limit N]` | Live fetch into a throwaway DB; prints counts, filter reasons, and the next N posts |
| `python -m jobbot discover "Company" …` | Finds a company's Greenhouse/Lever/Ashby board and prints a line for `companies.json` |

Run them with `PYTHONPATH=src`.

## How closing works

- **Company boards**: a job missing from the company's board for 2 h counts as closed. A failed fetch never closes anything.
- **Unstop**: closed at its application deadline.
- **Workday**: no automatic close (search results aren't a full list); posts stay as they are.

## Known limits

- **Unstop's terms of service:** I couldn't read them (the page needs a browser), so read https://unstop.com/terms before going live. The bot sends Unstop traffic (every link goes to Unstop), but it's their call. Set `ENABLE_UNSTOP=0` to turn it off.
- **Endpoints can change:** Unstop and Workday are not documented APIs, so an endpoint change breaks that collector until it is fixed. Other sources keep working, and failures show in the run log and the `job_sources` table.
- **Untested on Postgres and against live Telegram:** the tests use SQLite and a dry-run Telegram client; the live sources were tested with dry runs. Run `check`, then post to a private test channel first.

## Next steps

- **More volume:** add an aggregator with a free API key (Adzuna, Jooble) and more company boards via `discover`.
- **Click tracking:** a short-link redirect (Cloudflare Worker), as planned for dealbot.
- **Subscriber alerts:** a bot command such as `/alerts python remote` that DMs matching jobs.
