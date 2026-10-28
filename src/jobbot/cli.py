"""Command line entry point: python -m jobbot <command>."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from typing import List

from jobbot import classify
from jobbot.collectors import build_collectors, http_client
from jobbot.collectors.ats import BOARDS
from jobbot.composer import compose
from jobbot.config import Config, load_dotenv
from jobbot.db import STATUS_CANDIDATE, Db, Repo
from jobbot.pipeline import Pipeline, raw_from_json
from jobbot.telegram import Telegram, TelegramError


def _open(cfg: Config) -> Repo:
    repo = Repo(Db(cfg.database_url))
    repo.init()
    return repo


def _print_post(text: str) -> None:
    plain = re.sub(r'<a href="([^"]+)">([^<]+)</a>', r"\2 [\1]", text)
    plain = re.sub(r"</?(b|s|i)>", "", plain)
    print("┌──\n" + "\n".join("│ " + line for line in plain.splitlines()) + "\n└──")


def cmd_run(cfg: Config, _: argparse.Namespace) -> int:
    missing = [name for name, val in (("TELEGRAM_BOT_TOKEN", cfg.bot_token),
                                      ("TELEGRAM_CHANNEL_ID", cfg.channel_id)) if not val]
    if os.environ.get("GITHUB_ACTIONS") == "true" and not cfg.database_url:
        missing.append("DATABASE_URL")  # the runner's disk is wiped after every run
    if missing and not cfg.dry_run:
        print(f"Missing required settings: {', '.join(missing)}", file=sys.stderr)
        return 2
    tg = Telegram(cfg.bot_token, dry_run=cfg.dry_run)
    pipe = Pipeline(cfg, _open(cfg), tg, build_collectors(cfg, http_client(cfg)))
    stats = pipe.run()
    print(json.dumps({**stats, "skipped": dict(pipe.skipped.most_common())}))
    for msg in tg.outbox:
        if msg["method"] == "sendMessage":
            _print_post(msg["text"])
    # A failed post is worth a red run in GitHub Actions; a flaky source is not.
    return 1 if any(e.startswith("telegram") for e in pipe.errors) else 0


def cmd_check(cfg: Config, _: argparse.Namespace) -> int:
    ok = True
    print(f"{'Database':<20} {cfg.database_url.split('@')[-1] if cfg.database_url else 'SQLite (jobbot.db)'}")
    try:
        _open(cfg)
        print(f"{'':<20} connected, tables ready")
    except Exception as exc:
        ok = False
        print(f"{'':<20} FAILED: {exc}")
    sources = build_collectors(cfg, http_client(cfg))
    print(f"{'Sources':<20} {len(sources)} ({'Unstop + ' if cfg.enable_unstop else ''}"
          f"{len(sources) - cfg.enable_unstop} company boards)")
    print(f"{'Channel':<20} {cfg.channel_id or 'MISSING'}")
    if not cfg.bot_token:
        print(f"{'Bot token':<20} MISSING")
        return 1
    tg = Telegram(cfg.bot_token)
    try:
        me = tg.get_me()
        print(f"{'Bot':<20} @{me['username']}")
        if cfg.channel_id:
            member = tg.get_chat_member(cfg.channel_id, me["id"])
            can_post = member.get("can_post_messages", False)
            can_edit = member.get("can_edit_messages", False)
            admin = member.get("status") in ("administrator", "creator")
            print(f"{'Bot in channel':<20} {member.get('status')}, post={can_post}, edit={can_edit}")
            if not (admin and can_post and can_edit):
                ok = False
                print("  -> Make the bot a channel admin with 'Post messages' and 'Edit messages of others'.")
    except TelegramError as exc:
        ok = False
        print(f"{'Telegram':<20} FAILED: {exc}")
    return 0 if ok else 1


def cmd_preview(cfg: Config, args: argparse.Namespace) -> int:
    """Fetch every source live and show what would be posted. Sends and stores nothing."""
    cfg.database_url, cfg.dry_run = ":memory:", True
    repo = _open(cfg)
    pipe = Pipeline(cfg, repo, Telegram("", dry_run=True, min_interval=0),
                    build_collectors(cfg, http_client(cfg)))
    pipe.collect()
    now = pipe.clock()
    rows = sorted(repo.by_status(STATUS_CANDIDATE), key=lambda r: pipe.priority(r, now, None),
                  reverse=True)
    by_source: dict = {}
    for r in rows:
        key = r["source"].split(":")[0]
        by_source[key] = by_source.get(key, 0) + 1
    print(f"Sources fetched: {len(repo.sources())}, failed: {len(pipe.errors)} {pipe.errors or ''}")
    print(f"Ready to post: {len(rows)} {by_source}")
    print(f"Interns: {sum(r['job_type'] == 'internship' for r in rows)}, "
          f"jobs: {sum(r['job_type'] == 'job' for r in rows)}")
    print(f"Filtered out: {dict(pipe.skipped.most_common())}\n")
    for r in rows[:args.limit]:
        _print_post(compose(raw_from_json(r["raw"]), now, cfg.channel_url).text)
    return 0


def cmd_discover(cfg: Config, args: argparse.Namespace) -> int:
    """Find a company's Greenhouse/Lever/Ashby board and print a companies.json entry."""
    client = http_client(cfg)
    for name in args.names:
        base = re.sub(r"[^a-z0-9]", "", name.lower())
        slugs = list(dict.fromkeys([base, re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"),
                                    base + "careers", base + "india"]))
        found = False
        for kind, cls in BOARDS.items():
            for slug in slugs:
                try:
                    jobs = cls(slug, name, client).fetch()
                except Exception:
                    continue
                if not jobs:
                    continue
                india = [j for j in jobs if classify.in_india(j)]
                print(json.dumps({"name": name, "ats": kind, "slug": slug}) +
                      f"   # {len(jobs)} jobs, {len(india)} in India")
                found = True
        if not found:
            print(f"# {name}: no Greenhouse/Lever/Ashby board found (try its careers page; "
                  "Workday sites need host/tenant/site from the careers URL)")
    return 0


COMMANDS = {"run": cmd_run, "check": cmd_check, "preview": cmd_preview, "discover": cmd_discover}


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(prog="jobbot", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="one cycle: collect, close ended jobs, post new jobs (max 5/hour)")
    sub.add_parser("check", help="verify database, bot token and channel admin rights")
    p = sub.add_parser("preview", help="fetch live and print what would be posted (sends nothing)")
    p.add_argument("--limit", type=int, default=5)
    d = sub.add_parser("discover", help="find companies' job boards for data/companies.json")
    d.add_argument("names", nargs="+")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()
    return COMMANDS[args.command](Config.from_env(), args)
