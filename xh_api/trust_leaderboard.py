"""trust_leaderboard — the public ranking of x402 sellers, scored by the same trust layer we sell.

An agent deciding who to pay rarely has a way to compare sellers. This serves the sweep: every origin in the
catalogue, one representative endpoint each, scored 0-100, with the verdict spread and the most common
reasons points were lost. The free method page shows the top ten so a buyer can see the shape before paying.

Data comes from trust_sweep.py, refreshed on a schedule; every row carries the timestamp it was checked at,
so a buyer can see how fresh the judgement is.
"""

import json
import os
from dataclasses import dataclass
from typing import Any

DEFAULT_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "trust_sweep.json")
SWEEP_JSON = os.environ.get("XH_TRUST_SWEEP_JSON", DEFAULT_JSON)


@dataclass
class Ctx:
    pass


def _load() -> dict:
    try:
        with open(SWEEP_JSON) as f:
            return json.load(f)
    except Exception:
        return {"origins": [], "generated_at": None, "counts": {}, "score_stats": {}, "common_penalties": {}}


def query(ctx: Ctx, limit: int = 50, verdict: str | None = None, min_score: float | None = None,
          max_score: float | None = None, origin: str | None = None, order: str = "best",
          include_findings: bool = True) -> dict:
    data = _load()
    rows: list[dict[str, Any]] = [dict(r) for r in data.get("origins", [])]
    if origin:
        rows = [r for r in rows if r.get("origin") == origin]
    if verdict:
        rows = [r for r in rows if (r.get("verdict") or "") == verdict]
    if min_score is not None:
        rows = [r for r in rows if isinstance(r.get("score"), (int, float)) and r["score"] >= min_score]
    if max_score is not None:
        rows = [r for r in rows if isinstance(r.get("score"), (int, float)) and r["score"] <= max_score]
    rows.sort(key=lambda r: (r.get("score") if isinstance(r.get("score"), (int, float)) else -1),
              reverse=(order != "worst"))
    limit = max(1, min(int(limit), 500))
    rows = rows[:limit]
    if not include_findings:
        for r in rows:
            r.pop("findings", None)

    return {
        "generated_at": data.get("generated_at"),
        "counts": data.get("counts"),
        "score_stats": data.get("score_stats"),
        "common_penalties": data.get("common_penalties"),
        "order": order,
        "returned": len(rows),
        "ranking": rows,
        "method": data.get("method"),
        "not_checked": data.get("not_checked"),
        "caveat": ("A score is a point-in-time judgement from the outside, not an audit or an endorsement. "
                   "The sweep probes one endpoint per origin — an origin may operate others that behave "
                   "differently. Scores move as sellers change; each row carries its own checked_at."),
    }


def register(app, ctx: Ctx) -> None:
    from pydantic import BaseModel, Field

    class LBReq(BaseModel):
        limit: int = Field(50, ge=1, le=500)
        verdict: str | None = Field(None, description="pay | pay_with_caution | avoid")
        min_score: float | None = Field(None, ge=0, le=100)
        max_score: float | None = Field(None, ge=0, le=100)
        origin: str | None = Field(None, description="One origin only, e.g. https://example.com")
        order: str = Field("best", description="best | worst")
        include_findings: bool = True

    @app.get("/trust-leaderboard/method")
    def index():
        data = _load()
        rows = (data.get("origins") or [])[:10]
        return {
            "provider": "XH Agents — x402 seller trust leaderboard",
            "what_it_is": ("Every origin we can find in the public x402 catalogue, one representative endpoint "
                           "probed each and scored 0-100 by the same trust layer we sell as /api/x402-trust: "
                           "402 behaviour, challenge conformance, discovery documents, on-chain payTo "
                           "reputation and price sanity."),
            "price_usdc_per_call": 0.05,
            "endpoints": [{"route": "POST /api/trust-leaderboard", "price_usd": 0.05},
                          {"route": "GET /api/trust-leaderboard?limit=100&order=worst", "price_usd": 0.05}],
            "freshness": data.get("generated_at"),
            "coverage": data.get("counts"),
            "score_stats": data.get("score_stats"),
            "common_penalties": data.get("common_penalties"),
            "free_preview_top_10": [{"origin": r.get("origin"), "score": r.get("score"),
                                     "verdict": r.get("verdict"), "endpoints": r.get("count")} for r in rows],
            "not_checked": data.get("not_checked"),
            "caveat": ("Point-in-time, from the outside, one endpoint per origin — not an audit and not an "
                       "endorsement."),
        }

    def _run(req: LBReq) -> dict:
        return query(ctx, req.limit, req.verdict, req.min_score, req.max_score, req.origin, req.order,
                     req.include_findings)

    @app.post("/trust-leaderboard")
    def lb_post(req: LBReq):
        return _run(req)

    @app.get("/trust-leaderboard")
    def lb_get(limit: int = 50, verdict: str | None = None, min_score: float | None = None,
               max_score: float | None = None, origin: str | None = None, order: str = "best",
               include_findings: bool = True):
        return query(ctx, limit, verdict, min_score, max_score, origin, order, include_findings)
