# jobbot: IT internships & fresher jobs in India, on Telegram

Every hour it collects internships and entry-level IT jobs in India (on-site, hybrid and
remote), drops anything that isn't IT, entry level, paid, or safe, and posts new jobs
to your channel in English, **up to 5 per hour**. Each post has **Apply now** and **Share** buttons. When a job closes, its post is edited to **❌ CLOSED**.
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
| **Small-company hiring tools** (Workable, Recruitee, SmartRecruiters) | Open roles at the many smaller companies that run their careers page on these tools | Their public careers feeds, no key. Add companies with `discover` or the **discover** workflow. Field names come from vendor docs and have not yet been checked against a live response |
| **Workday career sites** | Interns/graduates at NVIDIA, Intel, Mastercard, Citi, Deutsche Bank, Micron, … | The JSON the public career site calls; every 3 h |

The company list is `data/companies.json`, 75 boards that had India jobs when I tested them. Add more with `discover` (below).

Not used, on purpose: LinkedIn, Naukri, Indeed and Internshala. Their terms or robots.txt forbid automated collection.

Not built yet: Wellfound, Cutshort, Hirist and Instahyre (their terms and any public feed could not be checked, so they stay off until someone confirms access or a partner feed), and Freshteam, Zoho Recruit and Keka (no public per-company feed was confirmed; Keka's `/careers/api/jobs/{portal}/active` looks usable but its field names need a live sample).

To add small companies: run the **discover** workflow from the Actions tab (or `python -m jobbot discover "Company"` locally) with their names, then paste the printed lines into `data/companies.json`. Run `preview` once to see what a new board returns.

## What gets posted

A job is posted only if **all** of these hold:

1. **India**: an Indian city, "India", or remote from India.
2. **IT**: the title names a tech role (developer, SDE, data, ML/AI, DevOps, cloud, QA, security, UI/UX, IT support …), or the source's main category is one. Sales, BD, HR, marketing, data entry, etc. are dropped even if the source tags them "tech".
3. **Entry level**: internship/trainee/apprentice, or a title such as graduate, fresher, junior, associate engineer, SDE-1, Engineer I. Unstop jobs count unless they ask for more than 2 years. Anything senior/lead/II+ is dropped. A plain "Software Engineer" with no level is dropped.
4. **Paid**: unpaid internships are skipped (`SKIP_UNPAID=0` to allow them).
5. **No scam signals**: fees, deposits, "WhatsApp only", "earn ₹X per day", "guaranteed placement".
6. **Fresh**: published in the last 10 days, and the deadline (if any) is **tomorrow or later** (IST). Jobs closing today or already closed are dropped; jobs with no deadline are fine.
7. **Not a repeat**: same company + title isn't posted twice within 30 days (across sources).

Each run posts the jobs that pass, **at most 5 in any rolling hour** (`MAX_POSTS_PER_HOUR`, 0 = off). Anything over the cap stays pending and goes out on the next run. The order is newest first, company sites slightly ahead of aggregators, alternating internships and jobs.

The **📤 Share** button opens Telegram's share sheet with the channel link plus the job's title and apply link, so readers can forward a job and bring friends to the channel. It needs a public `@handle` channel id; otherwise it shares the job link only.

Optional limits, all **off** by default: `QUIET_START_HOUR`/`QUIET_END_HOUR` (IST), `POST_INTERVAL_MINUTES`, `MAX_POSTS_PER_DAY`, `COMPANY_COOLDOWN_HOURS` (see `.env.example`).

## Volume: what to expect

Measured live on 2026-10-27:

- **About 50 jobs pass every filter at launch.** With the 5-per-hour cap, that backlog drains over about 10 hours (as long as runs happen hourly).
- **About 6-8 new ones appear per day after that**, mostly from Unstop. Each run posts whatever is new and posts nothing when there is nothing new, rather than posting filler. To get more, add sources (see "Next steps").

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

## Website

`site/` holds a one-page website for the channel (same navy, gold and teal look as the posts). The **pages** workflow publishes it to GitHub Pages at `https://iamyogeshmalkani.github.io/it-jobs-india/` whenever `site/` changes on `main`.

One-time setup: Settings → Pages → Build and deployment → Source: **GitHub Actions**, then run the **pages** workflow once (Actions → pages → Run workflow). The site is plain HTML and CSS, so to preview it, open `site/index.html` in a browser. If you change the channel handle, update it in `site/index.html` (the join links, the QR code in `site/assets/channel-qr.png`, and the social image `site/assets/og.png`).

## Changing the channel

Message ids belong to one channel, so the bot remembers which channel it posts to. If `TELEGRAM_CHANNEL_ID` changes, scheduled runs **stop without posting or editing anything** until you move over on purpose:

1. Add the bot to the new channel as **admin** (*Post messages* and *Edit messages of others*).
2. Update the `TELEGRAM_CHANNEL_ID` secret to the new `@handle`.
3. Go to Actions → **jobbot** → Run workflow, tick **repost_all**, and run it. It re-queues every job that is still open, posts them all to the new channel with no hourly cap (about 3 s apart), and records the new channel.
4. Done. The hourly schedule carries on from there as normal, posting new jobs to the new channel.

Closed jobs are not reposted, and jobs whose deadline has passed are dropped. The old channel's posts are left as they are, so delete or archive that channel yourself. Do step 2 and 3 back to back.

GitHub pauses scheduled workflows in repos with no activity for 60 days. If the channel goes quiet, re-enable it from the Actions tab.

## Commands

| Command | What it does |
|---|---|
| `python -m jobbot run` | One cycle: collect due sources, close ended jobs, post new jobs (max 5/hour) |
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
