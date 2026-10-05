#!/usr/bin/env python3
"""Tambah/lihat record DNS di DNSPod (Tencent) untuk domain kita — dipakai untuk memasang DMARC.

Memakai Tencent Cloud DNSPod API v3 dengan TC3-HMAC-SHA256 dan kredensial yang sudah ada di
/home/ubuntu/keys/tokenhub_cam.env (TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY).
Tidak pernah menampilkan nilai kredensial.

Contoh:
    python3 dnspod_dmarc.py list                    # lihat record xhagents.xyz
    python3 dnspod_dmarc.py check                   # cek khusus _dmarc / SPF / MX
    python3 dnspod_dmarc.py create-dmarc            # buat _dmarc TXT (p=none, rua=basefortyblock@gmail.com)
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HOST = "dnspod.tencentcloudapi.com"
SERVICE = "dnspod"
VERSION = "2021-03-23"
ENV_FILE = "/home/ubuntu/keys/tokenhub_cam.env"
DOMAIN = "xhagents.xyz"
DMARC_VALUE = "v=DMARC1; p=none; rua=mailto:basefortyblock@gmail.com; fo=1"


def creds() -> tuple[str, str]:
    sid = skey = ""
    for line in open(ENV_FILE):
        line = line.strip()
        if line.startswith("TENCENTCLOUD_SECRET_ID"):
            sid = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("TENCENTCLOUD_SECRET_KEY"):
            skey = line.split("=", 1)[1].strip().strip('"')
    if not sid or not skey:
        raise SystemExit("kredensial Tencent tidak ditemukan di " + ENV_FILE)
    return sid, skey


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def call(action: str, params: dict, sid: str, skey: str) -> dict:
    payload = json.dumps(params, separators=(",", ":"))
    ts = int(time.time())
    date = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
    hashed = hashlib.sha256(payload.encode()).hexdigest()
    canonical = (f"POST\n/\n\ncontent-type:application/json; charset=utf-8\nhost:{HOST}\n\n"
                 f"content-type;host\n{hashed}")
    scope = f"{date}/{SERVICE}/tc3_request"
    to_sign = (f"TC3-HMAC-SHA256\n{ts}\n{scope}\n"
               f"{hashlib.sha256(canonical.encode()).hexdigest()}")
    k_date = _sign(("TC3" + skey).encode(), date)
    k_service = _sign(k_date, SERVICE)
    k_signing = _sign(k_service, "tc3_request")
    sig = hmac.new(k_signing, to_sign.encode(), hashlib.sha256).hexdigest()
    auth = (f"TC3-HMAC-SHA256 Credential={sid}/{scope}, "
            f"SignedHeaders=content-type;host, Signature={sig}")
    req = urllib.request.Request(
        f"https://{HOST}/", data=payload.encode(), method="POST",
        headers={"Authorization": auth, "Content-Type": "application/json; charset=utf-8",
                 "Host": HOST, "X-TC-Action": action, "X-TC-Version": VERSION,
                 "X-TC-Timestamp": str(ts), "X-TC-Region": ""})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"Response": {"Error": {"Code": f"HTTP{e.code}", "Message": e.read().decode()[:200]}}}


def show(records: list[dict]) -> None:
    print(f"{'nama':28} {'tipe':6} {'baris':6} {'nilai'}")
    for rec in sorted(records, key=lambda r: (r.get("Name", ""), r.get("Type", ""))):
        val = (rec.get("Value") or "")[:88]
        print(f"{str(rec.get('Name'))[:28]:28} {str(rec.get('Type'))[:6]:6} "
              f"{str(rec.get('Line'))[:6]:6} {val}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["list", "check", "create-dmarc"])
    ap.add_argument("--domain", default=DOMAIN)
    args = ap.parse_args()
    sid, skey = creds()
    print(f"kredensial: SecretId {len(sid)} karakter, SecretKey {len(skey)} karakter (tidak ditampilkan)")

    if args.action == "create-dmarc":
        existing = call("DescribeRecordList", {"Domain": args.domain, "Subdomain": "_dmarc"}, sid, skey)
        recs = ((existing.get("Response") or {}).get("RecordList")) or []
        if recs:
            print("_dmarc sudah ada — tidak membuat ulang:")
            show(recs)
            return
        body = {"Domain": args.domain, "SubDomain": "_dmarc", "RecordType": "TXT",
                "RecordLine": "默认", "Value": DMARC_VALUE, "TTL": 600}
        out = call("CreateRecord", body, sid, skey)
        resp = out.get("Response") or {}
        if resp.get("Error"):
            print("record line 默认 ditolak:", json.dumps(resp["Error"])[:160])
            body["RecordLine"] = "default"
            out = call("CreateRecord", body, sid, skey)
            resp = out.get("Response") or {}
        if resp.get("Error"):
            print("GAGAL membuat record:", json.dumps(resp["Error"])[:300])
            sys.exit(1)
        print("dibuat:", json.dumps(resp.get("RecordId")), "| nilai:", DMARC_VALUE)
        return

    out = call("DescribeRecordList", {"Domain": args.domain, "Limit": 200}, sid, skey)
    resp = out.get("Response") or {}
    if resp.get("Error"):
        print("GAGAL membaca record:", json.dumps(resp["Error"])[:300])
        print("(kalau Code = AuthFailure/UnauthorizedOperation, kredensial ini tidak punya izin DNSPod;"
              " berarti record harus ditambah manual di panel DNSPod)")
        sys.exit(1)
    recs = resp.get("RecordList") or []
    print(f"record {args.domain}: {resp.get('RecordCountInfo', {}).get('TotalCount')} total, {len(recs)} terbaca")
    if args.action == "check":
        for key in ("_dmarc", "spf", "mx", "dkim"):
            hits = [r for r in recs if key.lower() in (str(r.get("Name")) + str(r.get("Value"))).lower()]
            print(f"  {key:8}: {len(hits)} record")
            for h in hits[:3]:
                print(f"      {h.get('Name')} {h.get('Type')} -> {str(h.get('Value'))[:90]}")
    else:
        show(recs)


if __name__ == "__main__":
    main()
