from __future__ import annotations

import json
from pathlib import Path
from typing import List

import httpx

from jobbot.collectors.ats import (BOARDS, AshbyCollector, GreenhouseCollector, LeverCollector,
                                    RecruiteeCollector, SmartRecruitersCollector,
                                    WorkableCollector)
from jobbot.collectors.base import Collector
from jobbot.collectors.unstop import UnstopCollector
from jobbot.collectors.workday import WorkdayCollector
from jobbot.config import Config

__all__ = ["AshbyCollector", "Collector", "GreenhouseCollector", "LeverCollector",
           "RecruiteeCollector", "SmartRecruitersCollector", "UnstopCollector",
           "WorkableCollector", "WorkdayCollector", "build_collectors", "http_client"]


def http_client(cfg: Config) -> httpx.Client:
    return httpx.Client(timeout=30, follow_redirects=True,
                        headers={"User-Agent": cfg.user_agent, "Accept": "application/json"})


def build_collectors(cfg: Config, client: httpx.Client) -> List[Collector]:
    """Unstop plus one collector per company in the companies file."""
    collectors: List[Collector] = []
    if cfg.enable_unstop:
        collectors.append(UnstopCollector(client, cfg.unstop_pages))
    path = Path(cfg.companies_file)
    if path.is_file():
        for entry in json.loads(path.read_text()):
            if entry.get("disabled"):
                continue
            ats = entry["ats"]
            if ats in BOARDS:
                collectors.append(BOARDS[ats](entry["slug"], entry["name"], client))
            elif ats == "workday":
                collectors.append(WorkdayCollector(entry["host"], entry["tenant"], entry["site"],
                                                   entry["name"], client))
            else:
                raise ValueError(f"{path}: unknown ats {ats!r} for {entry.get('name')}")
    return collectors
