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
import re
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

# ── jalur kedua: API klasik DNSPod (dnsapi.cn) dengan login_token ───────────────────────────────
# Dipakai kalau kunci Tencent Cloud tidak punya izin tulis dnspod:CreateRecord. Token DNSPod dibuat di
# panel dnspod.cn (用户中心 → 密钥管理) dan disimpan di berkas mode 600, tidak pernah lewat chat.
CLASSIC_ENV = "/home/ubuntu/keys/dnspod_token.env"


def classic_token() -> tuple[str, str]:
    """Ambil (id, token) DNSPod dari berkas kunci. Format berkas: DNSPOD_LOGIN_TOKEN=12345,abcdef…"""
    if not os.path.exists(CLASSIC_ENV):
        raise SystemExit(f"belum ada {CLASSIC_ENV} — jalankan /home/ubuntu/keys/set_dnspod_token.sh dulu")
    raw = open(CLASSIC_ENV).read()
    m = re.search(r"DNSPOD_LOGIN_TOKEN\s*=\s*[\"']?([0-9]+)\s*,\s*([A-Za-z0-9]+)", raw)
    if not m:
        raise SystemExit("format DNSPOD_LOGIN_TOKEN tidak dikenali (harus: <id>,<token>)")
    return m.group(1), m.group(2)


def classic(action: str, params: dict) -> dict:
    import urllib.parse
    tid, tok = classic_token()
    data = {"login_token": f"{tid},{tok}", "format": "json", "lang": "en", **params}
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(f"https://dnsapi.cn/{action}", data=body,
                                 headers={"User-Agent": "xh-agents-dns/1.0 (+https://xhagents.xyz)"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"status": {"code": str(e.code), "message": e.read().decode()[:200]}}
    except Exception as e:
        return {"status": {"code": "network", "message": f"{type(e).__name__}: {str(e)[:160]}"}}


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
    ap.add_argument("action", choices=["list", "check", "create-dmarc",
                                       "classic-check", "classic-create-dmarc"])
    ap.add_argument("--domain", default=DOMAIN)
    args = ap.parse_args()

    if args.action.startswith("classic-"):
        # jalur API klasik DNSPod (login_token di keys/dnspod_token.env)
        info = classic("Info.Version", {})
        st = info.get("status") or {}
        print("token DNSPod:", "sah" if st.get("code") in ("1", "2") else f"masalah: {st.get('code')} {st.get('message')}")
        rl = classic("Record.List", {"domain": args.domain})
        if (rl.get("status") or {}).get("code") != "1":
            print("Record.List gagal:", json.dumps(rl.get("status"))[:200])
            sys.exit(1)
        records = rl.get("records") or []
        print(f"record {args.domain}: {len(records)} terbaca")
        dmarc = [r for r in records if r.get("name") == "_dmarc"]
        if dmarc:
            print("_dmarc sudah ada:", [(r.get("name"), r.get("type"), r.get("value")) for r in dmarc])
            return
        print("_dmarc belum ada")
        if args.action == "classic-check":
            return
        out = classic("Record.Create", {"domain": args.domain, "sub_domain": "_dmarc",
                                        "record_type": "TXT", "record_line": "默认",
                                        "value": DMARC_VALUE, "ttl": 600})
        st = out.get("status") or {}
        if st.get("code") == "1":
            rec = out.get("record") or {}
            print(f"dibuat: id={rec.get('id')} name={rec.get('name')} value={rec.get('value')}")
        else:
            out2 = classic("Record.Create", {"domain": args.domain, "sub_domain": "_dmarc",
                                             "record_type": "TXT", "record_line": "default",
                                             "value": DMARC_VALUE, "ttl": 600})
            st2 = out2.get("status") or {}
            if st2.get("code") == "1":
                print("dibuat (record line 'default'):", json.dumps(out2.get("record"))[:160])
            else:
                print("GAGAL:", json.dumps(st)[:200], "|", json.dumps(st2)[:200])
                sys.exit(1)
        return

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
