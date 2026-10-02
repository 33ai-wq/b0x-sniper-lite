#!/usr/bin/env python3
"""Join dealwork.ai as an autonomous worker agent and pull the jobs that actually match our skills.

Registering is free and reversible (DELETE /api/v1/agents/me). Bidding is free; only a buyer funds
escrow, so nothing here can spend our money. Credentials go to a mode-600 file and are never printed.
"""
import json
import os
import stat
import urllib.error
import urllib.request

BASE = "https://dealwork.ai"
KEY_FILE = "/home/ubuntu/prpo_ai/keys/dealwork.env"
IDENTITY = "xhagents-prpo-vps-2026"          # stable: lets us recover instead of duplicating
NAME = "xhagents"
DESC = ("Research, technical-writing and documentation agent. I ship cited research reports, "
        "comparison analyses, API/technical documentation and cleaned datasets, usually within a few "
        "hours. Evidence-first: every claim comes with a receipt (source URL, command output, or a "
        "transaction hash you can check). I also run a live x402 API on Base (15 registered endpoints), "
        "so I can build and test the technical things I document rather than describing them.")
TAGS = ["research", "technical-writing", "documentation-api", "data-analysis", "comparison-analysis",
        "markdown", "citations", "web3", "x402", "python"]
UA = {"User-Agent": "xh-agents/1.0", "Content-Type": "application/json"}


def call(path, method="GET", body=None, key=None, timeout=45):
    headers = dict(UA)
    if key:
        headers["Authorization"] = "Bearer " + key
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:400].decode(errors="replace")


def save_creds(d: dict) -> None:
    os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
    with open(KEY_FILE, "w") as fh:
        fh.write("DEALWORK_API_KEY={}\nDEALWORK_AGENT_ID={}\nDEALWORK_HMAC_SECRET={}\n".format(
            d.get("apiKey", ""), d.get("agentAccountId", "") or d.get("agentId", ""), d.get("hmacSecret", "")))
    os.chmod(KEY_FILE, stat.S_IRUSR | stat.S_IWUSR)
    print(f"  kredensial disimpan di {KEY_FILE} (mode 600 — tidak ditampilkan)")


def main() -> None:
    key = None
    if os.path.exists(KEY_FILE):
        for line in open(KEY_FILE):
            if line.startswith("DEALWORK_API_KEY="):
                key = line.split("=", 1)[1].strip()
        print("sudah punya kredensial tersimpan")

    if not key:
        st, out = call("/api/v1/agents/onboard", "POST", {
            "autonomous": True, "agentName": NAME, "description": DESC,
            "capabilityTags": TAGS, "identityKey": IDENTITY})
        if not isinstance(out, dict):
            print("onboard gagal:", st, out)
            return
        data = out.get("data", out)
        print("onboard ->", st, "| recovered:", data.get("recovered"), "| claimUrl ada:", bool(data.get("claimUrl")))
        key = data.get("apiKey")
        if not key:
            print("  tidak ada apiKey; respons:", str(data)[:300])
            return
        save_creds(data)

    st, out = call("/api/v1/wallet/balance", key=key)
    bal = (out.get("data") if isinstance(out, dict) else None) or {}
    print(f"  wallet (sebagai worker): {st} {str(bal)[:120]}")

    st, out = call("/api/v1/jobs?limit=40", key=key)
    jobs = (out.get("data") if isinstance(out, dict) else None) or []
    meta = (out.get("meta") if isinstance(out, dict) else None) or {}
    print(f"  jobs: {st} | {len(jobs)} terlihat | meta: {str(meta)[:100]}")

    want = ("research", "writing", "data", "documentation", "development")
    picks = [j for j in jobs if str(j.get("category", "")).lower() in want and str(j.get("status")) == "bidding"]
    def budget(j):
        for k in ("fixedPrice", "budgetMax", "budgetMin"):
            v = j.get(k)
            if v not in (None, "", "0", 0):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
        return 0.0
    picks.sort(key=budget, reverse=True)
    print(f"\n  === {len(picks)} task cocok (kategori kita, masih bidding) — 5 teratas ===")
    for j in picks[:5]:
        ac = j.get("acceptanceCriteria") or []
        print(f"\n  [{j.get('id')}] {str(j.get('title'))[:78]}")
        print(f"    budget: fixed={j.get('fixedPrice')} min={j.get('budgetMin')} max={j.get('budgetMax')}"
              f" | deadline={str(j.get('deadline'))[:19]} | bidding_tutup={str(j.get('biddingDeadline'))[:19]}")
        print(f"    deliverable: {str(j.get('deliverableFormat'))[:90]}")
        print(f"    kriteria ({len(ac)}): " + " || ".join(str(c.get('description'))[:60] for c in ac[:3]))
    print("\n  (belum ada bid yang dikirim — draf bid menunggu persetujuan Boss)")


if __name__ == "__main__":
    main()
