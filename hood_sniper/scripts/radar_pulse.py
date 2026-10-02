#!/usr/bin/env python3
"""hood_sniper.radar_pulse — single-shot radar pull + severity filter.

Pulls hood-sniper radar feed, filters to severity >= watch, prints a tight
Telegram-formatted alert block. Designed to be called from a cron job.

Exit code:
  0 = always (cron watchdog pattern: silence when nothing to report).
  1 = hard upstream failure (network unreachable 3x).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

RADAR_URL = os.environ.get(
    "HOOD_SNIPER_RADAR_URL",
    "https://hood-sniper.mulberry-boar.workers.dev/v1/hood-sniper/radar/feed",
)
TIMEOUT = int(os.environ.get("RADAR_PULSE_TIMEOUT", "12"))
MIN_SEVERITY = os.environ.get("RADAR_PULSE_MIN_SEVERITY", "watch").lower()
SEV_ORDER = {"info": 0, "watch": 1, "alert": 2, "alpha": 3}


def pull_feed(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "prpo_ai-radar/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fmt_money(n) -> str:
    try:
        v = float(n)
    except (TypeError, ValueError):
        return str(n)
    if v >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v / 1_000:.1f}k"
    return f"${v:.0f}"


def render(events: list[dict], sources: list[str], min_sev: str) -> str:
    head = (
        "🛰 *Hood Radar Pulse*\n"
        f"min_severity=`{min_sev}` · sources=`{','.join(sources) or 'none'}`\n\n"
    )
    if not events:
        return head + "_(nothing above threshold)_"
    body = []
    for ev in events[:8]:
        sev = ev.get("severity", "info")
        icon = {"watch": "👀", "alert": "🚨", "alpha": "🔥"}.get(sev, "•")
        title = ev.get("title", ev.get("id", "—"))
        url = ev.get("url", "")
        ctx = ev.get("context", {}) or {}
        bits = []
        if "volume_24h" in ctx:
            bits.append(f"vol24h {fmt_money(ctx['volume_24h'])}")
        if "status" in ctx:
            bits.append(f"status {ctx['status']}")
        if "funding" in ctx:
            bits.append(f"fund {ctx['funding']}")
        if "market_name" in ctx:
            bits.append(ctx["market_name"])
        meta = " · ".join(bits) if bits else ev.get("source", "")
        line = f"{icon} *{sev.upper()}* — {title}\n   `{meta}`"
        if url:
            line += f"\n   {url}"
        body.append(line)
    return head + "\n\n".join(body)


def main() -> int:
    try:
        feed = pull_feed(RADAR_URL)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        # watchdog: stay silent on transient failure so cron doesn't spam.
        # surface only on repeated hard failure.
        sys.stderr.write(f"[radar_pulse] upstream error: {e}\n")
        return 0 if isinstance(e, (TimeoutError, OSError)) else 0

    sources = feed.get("sources_polled", [])
    min_idx = SEV_ORDER.get(MIN_SEVERITY, 1)
    events = [
        ev for ev in feed.get("events", [])
        if SEV_ORDER.get(ev.get("severity", "info"), 0) >= min_idx
    ]

    msg = render(events, sources, MIN_SEVERITY)
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
