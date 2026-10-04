#!/usr/bin/env python3
"""trust_sweep — sapu katalog x402 publik dengan trust layer kita, lalu rangkum per origin.

Untuk setiap origin: satu endpoint diambil sebagai sampel, dinilai oleh x402_trust (dokumen discovery,
challenge 402, reputasi payTo on-chain, kewajaran harga), lalu hasilnya diagregasi jadi peringkat.

Hasil ditulis ke JSON; trust_leaderboard.py menyajikannya (gratis: ringkasan + halaman, berbayar: data penuh).

Contoh:
    python3 trust_sweep.py --origins 200 --concurrency 6
    python3 trust_sweep.py --origins 40 --only-origin h2h.example.com
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BAZAAR = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=1000"
UA = {"User-Agent": "xh-agents-trust-sweep/1.0 (+https://xhagents.xyz/trust)"}
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.join(HERE, "data", "trust_sweep.json")


def fetch_bazaar(limit: int = 40000) -> list[dict]:
    items: list[dict] = []
    seen = set()
    offset = 0
    while offset < limit:
        req = urllib.request.Request(f"{BAZAAR}&offset={offset}", headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode())
        except Exception as e:
            print(f"  bazaar fetch error at offset {offset}: {type(e).__name__}")
            break
        batch = d.get("items") or []
        if not batch:
            break
        for it in batch:
            key = it.get("resource")
            if key and key not in seen:
                seen.add(key)
                items.append(it)
        offset += len(batch)
        total = (d.get("pagination") or {}).get("total") or 0
        if offset >= total:
            break
        time.sleep(0.05)
    return items


def pick_origins(items: list[dict], n: int, only: str | None = None) -> list[dict]:
    by_origin: dict[str, dict] = {}
    for it in items:
        url = it.get("resource") or ""
        if not url.startswith("http"):
            continue
        accs = it.get("accepts") or [{}]
        a0 = accs[0] if accs else {}
        try:
            price = int(a0.get("amount") or a0.get("maxAmountRequired") or 0) / 1e6
        except Exception:
            price = 0.0
        origin = "{u.scheme}://{u.netloc}".format(u=urllib.parse.urlparse(url))
        if only and origin != only:
            continue
        row = by_origin.setdefault(origin, {"origin": origin, "count": 0, "endpoints": [], "prices": [],
                                            "networks": set()})
        row["count"] += 1
        row["endpoints"].append({"url": url, "price_usd": price, "network": a0.get("network") or "",
                                 "payTo": a0.get("payTo") or ""})
        row["prices"].append(price)
        row["networks"].add(a0.get("network") or "")
    rows = sorted(by_origin.values(), key=lambda r: -r["count"])
    for r in rows:
        # sampel: endpoint termurah (yang paling mungkin dipanggil agen berkali-kali)
        r["sample"] = sorted(r["endpoints"], key=lambda e: (e["price_usd"] or 0, e["url"]))[0]
        r["networks"] = sorted(x for x in r["networks"] if x)
        r["price_median"] = statistics.median(r["prices"]) if r["prices"] else None
        r.pop("endpoints")
    return rows[:n]


def assess_one(ctx, row: dict, timeout: float) -> dict:
    import x402_trust
    url = row["sample"]["url"]
    try:
        rep = x402_trust.assess(ctx, url, method="POST", body={})
    except Exception as e:
        rep = {"url": url, "reachable": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}
    return {
        "origin": row["origin"], "url": url, "count": row["count"],
        "score": rep.get("score"), "verdict": rep.get("verdict"), "reachable": bool(rep.get("reachable")),
        "status": rep.get("status"), "latency_ms": rep.get("latency_ms"),
        "points": rep.get("points"), "penalty": rep.get("penalty"),
        "payto": (rep.get("accepts") or [{}])[0].get("payTo"),
        "network": (rep.get("accepts") or [{}])[0].get("network") or row.get("networks", [None])[0],
        "findings": (rep.get("findings") or [])[:6],
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--origins", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--only-origin", default=None)
    ap.add_argument("--refresh-days", type=float, default=7.0,
                    help="origin yang sudah diperiksa dalam N hari terakhir dilewati (0 = periksa ulang semua)")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    prev = {}
    if os.path.exists(args.out):
        try:
            old = json.load(open(args.out))
            for r in old.get("origins", []):
                prev[r["origin"]] = r
            print(f"hasil sebelumnya: {len(prev)} origin ({old.get('generated_at')})")
        except Exception as e:
            print(f"hasil lama tidak terbaca: {type(e).__name__}")

    old = json.load(open(args.out)) if os.path.exists(args.out) else {"origins": []}
    keep: list[dict] = []
    cutoff = time.time() - args.refresh_days * 86400
    for r in old.get("origins", []):
        try:
            ts = time.mktime(time.strptime(r["checked_at"], "%Y-%m-%dT%H:%M:%SZ")) - time.timezone
        except Exception:
            ts = 0
        if cutoff and ts >= cutoff:
            keep.append(r)

    print("mengambil katalog Coinbase Bazaar …")
    items = fetch_bazaar()
    print(f"  {len(items)} resource unik")
    rows = pick_origins(items, args.origins, args.only_origin)
    print(f"  {len(rows)} origin dipilih (sampel 1 endpoint per origin)")
    if not rows:
        print("tidak ada origin untuk diperiksa")
        return

    import server  # menyediakan _check_ssrf/_decode_challenge/_rpc — jalur yang sama dengan endpoint live
    import x402_trust
    ctx = x402_trust.Ctx(check_ssrf=server._check_ssrf, decode_challenge=server._decode_challenge,
                         rpc=server._rpc, erc20=server.erc20_call, is_address=server._is_address,
                         alchemy_url=server._DEDICATED_RPC)

    verified = {r["origin"] for r in keep}
    todo = [r for r in rows if r["origin"] not in verified] or rows

    results = list(keep)
    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {ex.submit(assess_one, ctx, r, args.timeout): r for r in todo}
        for f in as_completed(futs):
            results.append(f.result())
            done += 1
            if done % 25 == 0 or done == len(todo):
                rate = done / max(1e-9, time.time() - t0)
                print(f"  {done}/{len(todo)} origin diperiksa ({rate:.1f}/s)")

    scored = [r for r in results if isinstance(r.get("score"), (int, float))]
    scored.sort(key=lambda r: -r["score"])
    verdict_counts: dict[str, int] = {}
    for r in results:
        v = r.get("verdict") or ("unreachable" if not r.get("reachable") else "unknown")
        verdict_counts[v] = verdict_counts.get(v, 0) + 1
    penalties: dict[str, int] = {}
    for r in results:
        for f in r.get("findings") or []:
            key = f.split(":")[0][:70]
            penalties[key] = penalties.get(key, 0) + 1

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": ("one representative endpoint per origin, scored with XH Agents' x402 trust layer: unpaid 402 "
                   "probe, challenge conformance, discovery documents, on-chain payTo reputation, price sanity"),
        "source": "Coinbase Bazaar discovery catalogue + live probes",
        "counts": {"origins_in_catalogue": None, "origins_scored": len(scored), "origins_total": len(results),
                   "verdicts": verdict_counts},
        "score_stats": {
            "median": statistics.median([r["score"] for r in scored]) if scored else None,
            "mean": round(statistics.fmean([r["score"] for r in scored]), 1) if scored else None,
            "p90": (sorted([r["score"] for r in scored])[int(len(scored) * 0.9)] if len(scored) > 3 else None),
            "unreachable": len([r for r in results if not r.get("reachable")]),
        },
        "common_penalties": dict(sorted(penalties.items(), key=lambda kv: -kv[1])[:15]),
        "origins": sorted(results, key=lambda r: -(r.get("score") or -1)),
        "not_checked": ["behaviour after payment", "uptime over time", "operator identity", "content accuracy"],
    }
    json.dump(payload, open(args.out, "w"), indent=2)
    print(f"\nditulis: {args.out}")
    print(f"  {len(scored)} origin berskor dari {len(results)} (median {payload['score_stats']['median']}, "
          f"mean {payload['score_stats']['mean']}, tidak terjangkau {payload['score_stats']['unreachable']})")
    print("  verdict:", json.dumps(verdict_counts))
    print("  lima teratas:", [(r["origin"], r["score"]) for r in scored[:5]])
    print("  lima terendah:", [(r["origin"], r["score"]) for r in scored[-5:]])


if __name__ == "__main__":
    main()
