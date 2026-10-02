"""hood_sniper.engine — score candidates vs baseline, emit ranked
events.

Reads/writes two stable JSON artifacts under /root/prpo_ai/hood_sniper:

  • radar_baseline.json   — rolling per-source snapshot (volume24h by
    market, current status flips, latest known contract set). Updated
    each tick.

  • radar_history.json    — last N emitted events. Used to dedupe by
    sha1(id) and bound memory growth.

Multi-source → event-id = sha1(source|kind|chain_id|context-stable).

Severity ladder:
  info   = market status / volume present (baseline-only signal)
  watch  = volume vs 5× rolling avg (suspicious but unverified)
  alert  = status flip OFFLINE→ONLINE / new contract in window
  alpha  = multi-source corroboration (markets + blockscout agree)
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

from . import sources


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_id(c: dict) -> str:
    """Produce a stable event-id from candidate context, ignoring ts.
    Same event re-emerging on next tick returns same id → dedup."""
    payload = json.dumps(
        {
            "source": c["source"],
            "kind": c["kind"],
            "chain_id": c["chain_id"],
            "title": c["title"],
            "context": c.get("context", {}),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:16]


def _load_baseline(path: str) -> dict:
    if not os.path.exists(path):
        return {"first_run": True}
    try:
        return json.loads(open(path, "r", encoding="utf-8").read())
    except (OSError, ValueError):
        return {"first_run": True}


def _save_baseline(path: str, blob: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(blob, f, indent=2, sort_keys=True)


def _load_history(path: str, max_events: int = 500) -> list[dict]:
    if not os.path.exists(path):
        return []
    try:
        events = json.loads(open(path, "r", encoding="utf-8").read())
    except (OSError, ValueError):
        return []
    if not isinstance(events, list):
        return []
    return events[-max_events:]


def _save_history(path: str, events: list[dict], max_events: int = 500) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(events[-max_events:], f, indent=2)


def _score(c: dict, baseline: dict, history_ids: set[str]) -> dict:
    """Convert raw candidate → scored event."""
    cid = _stable_id(c)
    is_new = cid not in history_ids
    severity = "info"
    title = c["title"]

    if c["source"] == "arcus":
        v = float((c.get("context") or {}).get("volume_24h") or 0)
        baseline_v = ((baseline.get("arcus") or {}).get(c["title"])) or 0
        if baseline_v > 0 and v / max(baseline_v, 1) >= 5.0:
            severity = "watch"
            title = f"⚡ {title} ({int(v/baseline_v)}× baseline)"
        # Status-flip detection: comparing status flag now vs last tick
        prev_status = ((baseline.get("arcus_status") or {}).get(str(c["context"]["market_id"])))
        if prev_status and prev_status != c["context"]["status"] and c["context"]["status"] == "ONLINE":
            severity = "alert"
            title = f"🚨 {c['title']} → ONLINE"

    elif c["source"] == "blockscout":
        severity = "alert"
        title = f"🆕 {title}"

    elif c["source"] == "robidy":
        severity = "alpha"
        title = f"🌱 {title}"

    return {
        "id": cid,
        "ts": c["ts"],
        "source": c["source"],
        "kind": c["kind"],
        "severity": severity if is_new else "info",
        "title": title,
        "url": c["url"],
        "chain_id": c["chain_id"],
        "context": c.get("context", {}),
    }


def tick(
    baseline_path: str,
    history_path: str,
    *,
    poll_arcus: bool = True,
    poll_blockscout: bool = True,
    poll_robidy: bool = True,
) -> dict:
    """Run one radar cycle. Returns the radar JSON payload."""
    baseline = _load_baseline(baseline_path)
    history  = _load_history(history_path)
    history_ids = {e["id"] for e in history}
    sources_polled = []
    fresh = []

    # ─── poll each source ────────────────────────────────────────
    if poll_arcus:
        cand = sources.poll_arcus()
        if cand:
            sources_polled.append("arcus")
        fresh.extend(cand)
    if poll_blockscout:
        cand = sources.poll_blockscout_new_contracts()
        if cand:
            sources_polled.append("blockscout")
        fresh.extend(cand)
    if poll_robidy:
        cand = sources.poll_robidy_internal()
        if cand:
            sources_polled.append("robidy")
        fresh.extend(cand)

    # ─── update baseline (volume by market title) ────────────────
    new_baseline = {
        "arcus": {
            c["title"]: float((c.get("context") or {}).get("volume_24h") or 0)
            for c in fresh
            if c["source"] == "arcus"
            and (c.get("context") or {}).get("volume_24h") is not None
        },
        "arcus_status": {
            str(c["context"]["market_id"]): c["context"]["status"]
            for c in fresh
            if c["source"] == "arcus" and (c.get("context") or {}).get("market_id") is not None
        },
        "ts": _now_iso(),
    }

    # ─── score candidates ────────────────────────────────────────
    events = [_score(c, baseline, history_ids) for c in fresh]

    # ─── append NEW events to history ─────────────────────────────
    new_events = [e for e in events if e["id"] not in history_ids]
    if new_events:
        history.extend(new_events)
        _save_history(history_path, history)

    _save_baseline(baseline_path, new_baseline)

    # ─── rank: alpha → alert → watch → info, then by ts desc ──────
    order = {"alpha": 0, "alert": 1, "watch": 2, "info": 3}
    ranked = sorted(events, key=lambda e: (order.get(e["severity"], 9), e["ts"]))

    return {
        "generated_at": _now_iso(),
        "sources_polled": sources_polled,
        "events": ranked,
        "stats": {
            "events_total":   len(ranked),
            "alpha":          sum(1 for e in ranked if e["severity"] == "alpha"),
            "alert":          sum(1 for e in ranked if e["severity"] == "alert"),
            "watch":          sum(1 for e in ranked if e["severity"] == "watch"),
            "new_since_last": len(new_events),
        },
        "baseline": new_baseline,
    }
