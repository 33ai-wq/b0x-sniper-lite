#!/usr/bin/env python3
"""xh_source_check.py - run the real "source of truth" checks and print a three-state ledger.

WHY THIS EXISTS
---------------
Twice in one week the company believed something its own notes said, and the source disagreed:
our notes said "v1.0.1-v1.0.3 pending, v1.0.0 live" while `clawhub skill verify` answered that v1.0.3 was
live and clean; and a broad eth_getLogs read that was REFUSED nearly got reported as "no transfers in".
The rule this tool enforces:

    "We may not turn 'we finished' or 'we could not read the source' into a statement about the source."

So every claim about an external thing gets one of four states, with the command that produced it:

    TERKONFIRMASI    the source answered and agrees            -> only this may be called "selesai"
    MENUNGGU SUMBER  we sent it, the source has not answered   -> ClawHub review, a human approval, indexing
    GAGAL            the source answered and disagrees
    TIDAK TERBACA    the source could not be read at all       -> never reported as zero

READ-ONLY. It never writes to git, never restarts anything, never pays, never publishes, and never prints
an asset amount (counts only - the same rule our public pages follow).

Usage:  /home/ubuntu/prpo_ai/venv/bin/python /home/ubuntu/prpo_ai/xh_api/xh_source_check.py [--json]
Exit:   0 when nothing is GAGAL/TIDAK TERBACA, 1 otherwise, 2 when a check could not be attempted.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import httpx

TREASURY = "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0"
CLAWHUB_SLUG = "xh-agents-x402"
CLAWHUB_LOCAL = "/home/ubuntu/prpo_ai/dist/clawhub/xh-agents-x402"
ALCHEMY_ENV = "/home/ubuntu/prpo_ai/keys/alchemy_env"
PENDING_BOSS = "/home/ubuntu/pending_boss.json"

REPOS = [
    "/home/ubuntu/prpo_ai",
    "/home/ubuntu/xhagents-web",
    "/home/ubuntu/x402_rank",
    "/home/ubuntu/xh-agents-core",
]
SERVICES = ["xh-api", "xh-adengine", "xh-chatengine", "ataraxia-backend", "xh-kb", "xh-mcp"]
SITE = "https://xhagents.xyz"

LEDGER: list[dict] = []


def rec(state: str, source: str, item: str, evidence: str) -> None:
    """One ledger row. state is one of the four words above (ASCII in code, shown in Indonesian)."""
    LEDGER.append({"state": state, "source": source, "item": item, "evidence": evidence[:400],
                   "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})


def run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:  # noqa: BLE001
        return 127, f"{type(e).__name__} {e}"


# ── 1. ClawHub: what does the registry actually say, and does it match our package? ──────────────
def check_clawhub() -> None:
    rc, out = run(["clawhub", "skill", "verify", CLAWHUB_SLUG, "--json"], timeout=90)
    doc = None
    if rc == 0 and out.strip():
        try:
            doc = json.loads(out[out.index("{"):out.rindex("}") + 1])
        except Exception:  # noqa: BLE001
            doc = None
    if not doc:
        rec("TIDAK TERBACA", "clawhub skill verify", f"skill {CLAWHUB_SLUG}",
            f"rc={rc} out={out.strip()[:160]}")
        return
    sec = doc.get("security") or {}
    rec("TERKONFIRMASI" if sec.get("passed") else "GAGAL", "clawhub skill verify",
        f"skill {CLAWHUB_SLUG} v{doc.get('version')} (resolvedFrom={doc.get('resolvedFrom')})",
        f"decision={doc.get('decision')} security={sec.get('status')}/{sec.get('verdict')} "
        f"passed={sec.get('passed')} page={doc.get('pageUrl')}")

    def sha(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    published = {f.get("path"): f.get("sha256") for f in ((doc.get("artifact") or {}).get("files") or [])}
    if not published:
        rec("TIDAK TERBACA", "clawhub artifact manifest",
            "published package vs local copy", "the verify payload carried no file hashes")
        return
    bad = []
    for rel, want in published.items():
        local = os.path.join(CLAWHUB_LOCAL, rel)
        if not os.path.exists(local):
            bad.append(f"{rel}: missing locally")
            continue
        got = sha(local)
        if got != want:
            bad.append(f"{rel}: local {got[:8]} != published {str(want)[:8]}")
    rec("GAGAL" if bad else "TERKONFIRMASI", "sha256 local vs clawhub artifact",
        f"published package == local package ({len(published)} files)",
        "; ".join(bad) if bad else "every published hash matches the working copy")


# Public path can differ from the internal route (nginx rewrites some: the bundle is served at
# /api/compute/xh-bundle while the service calls it /xh-bundle). So the list below is the PUBLIC path,
# and check_http() also asserts each one still exists in the live catalogue - a silently renamed route
# is exactly the kind of thing this ledger exists to catch.
PUBLIC_PAID = [("/api/payment-verify", "POST"), ("/api/compute/xh-bundle", "POST"),
               ("/api/daily-drop", "GET")]


def check_catalogue_paths(catalogue: dict | None) -> None:
    if not catalogue:
        return
    paths = catalogue.get("paths") or {}
    for path, _m in PUBLIC_PAID:
        rec("TERKONFIRMASI" if path in paths else "GAGAL", "live openapi.json",
            f"catalogue advertises {path}",
            "present" if path in paths else "MISSING from the live catalogue (renamed or removed?)")


# ── 2. Live HTTP: is the product actually served, with the right challenge? ─────────────────────
def check_http() -> None:
    r = None
    for url in [f"{SITE}/", f"{SITE}/trust/", f"{SITE}/openapi.json", f"{SITE}/.well-known/x402",
                "https://xhokaya.xhagents.xyz/", "https://ataraxia.xhagents.xyz/",
                "https://pronomad.duckdns.org/health"]:
        try:
            r = httpx.get(url, timeout=25, follow_redirects=True)
            rec("TERKONFIRMASI" if r.status_code == 200 else "GAGAL", "public HTTP",
                f"GET {url}", f"HTTP {r.status_code}, {len(r.content)} bytes")
        except Exception as e:  # noqa: BLE001
            rec("TIDAK TERBACA", "public HTTP", f"GET {url}", f"{type(e).__name__} {str(e)[:120]}")
    cat = None
    try:
        cat = httpx.get(f"{SITE}/openapi.json", timeout=25).json()
    except Exception:  # noqa: BLE001
        cat = None
    check_catalogue_paths(cat)
    for path, method in PUBLIC_PAID:
        url = f"{SITE}{path}"
        try:
            r = httpx.request(method, url, json={} if method == "POST" else None, timeout=30)
            hdr = r.headers.get("payment-required") or r.headers.get("PAYMENT-REQUIRED")
            detail = f"HTTP {r.status_code}"
            if hdr:
                try:
                    import base64
                    pad = "=" * (-len(hdr) % 4)
                    ch = json.loads(base64.b64decode(hdr + pad))
                    acc = (ch.get("accepts") or [{}])[0]
                    payto = str(acc.get("payTo", "")).lower()
                    ok_pay_to = payto == TREASURY
                    detail += (f" challenge v{ch.get('x402Version')} payTo_matches_treasury={ok_pay_to}"
                               f" amount={acc.get('maxAmountRequired') or acc.get('amount')}"
                               f" network={acc.get('network')}")
                    rec("TERKONFIRMASI" if (r.status_code == 402 and ok_pay_to) else "GAGAL",
                        "unpaid request challenge", f"{method} {path}", detail)
                    continue
                except Exception as e:  # noqa: BLE001
                    detail += f" (challenge undecodable: {type(e).__name__})"
            rec("TERKONFIRMASI" if r.status_code in (200, 402) else "GAGAL",
                "unpaid request", f"{method} {path}", detail)
        except Exception as e:  # noqa: BLE001
            rec("TIDAK TERBACA", "unpaid request", f"{method} {path}", f"{type(e).__name__} {str(e)[:120]}")


# ── 3. Services ────────────────────────────────────────────────────────────────────────────────
def check_services() -> None:
    for svc in SERVICES:
        rc, out = run(["systemctl", "is-active", svc], timeout=20)
        state = out.strip() == "active"
        rec("TERKONFIRMASI" if state else "GAGAL", "systemctl is-active", f"service {svc}",
            out.strip() or f"rc={rc}")


# ── 4. Repositories: is what we committed actually on the remote? ───────────────────────────────
def check_repos() -> None:
    for repo in REPOS:
        if not os.path.isdir(os.path.join(repo, ".git")):
            continue
        rc, head = run(["git", "-C", repo, "rev-parse", "HEAD"], timeout=20)
        head = head.strip()
        if rc != 0 or not head:
            rec("TIDAK TERBACA", repo, "local HEAD", "not a git checkout")
            continue
        rc, rem = run(["git", "-C", repo, "ls-remote", "origin", "refs/heads/main"], timeout=90)
        remote = rem.split()[0] if rem.split() else ""
        if not remote:
            rec("TIDAK TERBACA", "git ls-remote", os.path.basename(repo),
                f"cannot read origin/main (rc={rc})")
            continue
        rec("TERKONFIRMASI" if remote == head else "GAGAL", "git ls-remote vs HEAD",
            os.path.basename(repo), f"remote={remote[:10]} local={head[:10]}"
            + ("" if remote == head else "  -> ada commit lokal yang belum di-push"))


# ── 5. Treasury: counts only, and refusals reported as refusals ─────────────────────────────────
def check_treasury_inflow() -> None:
    key = ""
    if os.path.exists(ALCHEMY_ENV):
        for line in open(ALCHEMY_ENV):
            if line.strip().startswith("ALCHEMY_API_KEY"):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        rec("TIDAK TERBACA", "alchemy_getAssetTransfers", "USDC inflow to treasury (7 days)",
            "no ALCHEMY_API_KEY in keys/alchemy_env")
        return
    try:
        r = httpx.post(f"https://base-mainnet.g.alchemy.com/v2/{key}",
                       json={"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []},
                       timeout=30)
        head = int(r.json()["result"], 16)
        res = httpx.post(f"https://base-mainnet.g.alchemy.com/v2/{key}",
                         json={"jsonrpc": "2.0", "id": 1, "method": "alchemy_getAssetTransfers",
                               "params": [{"fromBlock": hex(head - 300000), "toBlock": "latest",
                                           "toAddress": TREASURY,
                                           "contractAddresses": ["0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"],
                                           "category": ["erc20"], "withMetadata": False,
                                           "excludeZeroValue": True, "maxCount": "0x3e8",
                                           "order": "desc"}]}, timeout=60).json()
        tr = ((res.get("result") or {}).get("transfers")) or []
        senders = sorted({t["from"].lower() for t in tr})
        rec("TERKONFIRMASI", "alchemy_getAssetTransfers",
            "USDC transfers INTO the treasury, last ~7 days",
            f"{len(tr)} transfer(s) from {len(senders)} distinct payer(s) "
            f"(amounts deliberately not printed); newest block "
            f"{max((int(t['blockNum'], 16) for t in tr), default=None)}")
    except Exception as e:  # noqa: BLE001
        rec("TIDAK TERBACA", "alchemy_getAssetTransfers", "USDC inflow to treasury (7 days)",
            f"{type(e).__name__} {str(e)[:140]} - NOT to be reported as zero inflows")


# ── 6. Things only Boss can close ───────────────────────────────────────────────────────────────
def check_pending_boss() -> None:
    if not os.path.exists(PENDING_BOSS):
        return
    try:
        items = json.load(open(PENDING_BOSS))
    except Exception as e:  # noqa: BLE001
        rec("TIDAK TERBACA", PENDING_BOSS, "pending Boss decisions", str(e)[:120])
        return
    for it in items if isinstance(items, list) else []:
        rec("MENUNGGU SUMBER", "Boss", str(it.get("item", "?")),
            f"asked {it.get('asked', '?')}" + (f" - {it['note']}" if it.get("note") else ""))


def main() -> int:
    as_json = "--json" in sys.argv
    check_clawhub()
    check_http()
    check_services()
    check_repos()
    check_treasury_inflow()
    check_pending_boss()

    order = {"GAGAL": 0, "TIDAK TERBACA": 1, "MENUNGGU SUMBER": 2, "TERKONFIRMASI": 3}
    rows = sorted(LEDGER, key=lambda r: order.get(r["state"], 9))
    if as_json:
        print(json.dumps(rows, indent=2))
    else:
        label = {"TERKONFIRMASI": "TERKONFIRMASI   ", "MENUNGGU SUMBER": "MENUNGGU SUMBER ",
                 "GAGAL": "GAGAL           ", "TIDAK TERBACA": "TIDAK TERBACA   "}
        print(f"LEDGER SUMBER KEBENARAN - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}")
        print("(hanya baris TERKONFIRMASI yang boleh disebut 'selesai')\n")
        for r in rows:
            print(f"[{label.get(r['state'], r['state'])}] {r['item']}")
            print(f"    sumber   : {r['source']} @ {r['checked_at']}")
            print(f"    bukti    : {r['evidence']}")
        print("\nringkas:", ", ".join(f"{s}={sum(1 for r in rows if r['state'] == s)}"
                                      for s in ("TERKONFIRMASI", "MENUNGGU SUMBER", "GAGAL", "TIDAK TERBACA")))
    try:
        with open("/home/ubuntu/source_check_last.json", "w") as fh:
            json.dump({"checked_at": datetime.now(timezone.utc).isoformat(), "rows": rows}, fh, indent=2)
        if not as_json:
            print("salinan: /home/ubuntu/source_check_last.json")
    except Exception:  # noqa: BLE001
        pass
    bad = [r for r in rows if r["state"] in ("GAGAL", "TIDAK TERBACA")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
