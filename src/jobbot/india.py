"""India-specific formatting and time helpers (INR grouping, LPA, IST)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")


def format_inr(amount: int) -> str:
    """Format rupees with Indian digit grouping: 149999 -> ₹1,49,999."""
    n = int(round(amount))
    sign = "-" if n < 0 else ""
    digits = str(abs(n))
    if len(digits) <= 3:
        return f"{sign}₹{digits}"
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{sign}₹{','.join(groups + [tail])}"


def lakhs(amount: int) -> str:
    """600000 -> '6', 450000 -> '4.5', 1250000 -> '12.5' (lakh rupees)."""
    value = round(amount / 100000, 1)
    return f"{value:g}"


def to_ist(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, IST)


def is_quiet_hours(now_ts: int, start_hour: int, end_hour: int) -> bool:
    """True when IST hour is in [start_hour, end_hour). Handles wrap past midnight."""
    hour = to_ist(now_ts).hour
    if start_hour <= end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def ist_day_start(now_ts: int) -> int:
    local = to_ist(now_ts)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(midnight.timestamp())


def format_deadline(deadline_ts: int, now_ts: int) -> str:
    """'Apply by 9 Nov' plus a real countdown when it closes within two days."""
    when = to_ist(deadline_ts)
    text = f"Apply by {when.day} {when.strftime('%b')}"
    hours = (deadline_ts - now_ts) // 3600
    if 0 < hours < 48:
        text += f" (closes in {hours} h)" if hours >= 1 else " (closes within the hour)"
    return text
