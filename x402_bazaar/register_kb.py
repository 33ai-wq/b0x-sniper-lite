#!/usr/bin/env python3
"""
Register KB Ask endpoint to x402bazaar.org via quick-register
Using the old x402 treasury key for signing, but KB treasury for payments
"""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import requests
from eth_account import Account

D = Path(__file__).parent
KEY_FILE = D / ".bazaar_key"
SERVER = os.environ.get("BAZAAR_SERVER", "https://x402-api.onrender.com")
EXPECTED_OWNER = "0x57eec52d76a4a78d4562fc2564101a4bd2e3f357"  # Old x402 treasury (has private key)
KB_TREASURY = "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0"  # KB Treasury (Smart Wallet, no private key)

SERVICES = [
    {
        "name": "xh-agents-kb-ask",
        "url": "https://xhagents.xyz/api/kb/ask",
        "price": 0.03,
        "desc": "XH Agents Knowledge Base - Ask questions and get technical solutions from 15 curated entries covering devops, AI infra, payments, trading bots, and content automation",
        "pay_to": KB_TREASURY,  # Payments go to KB Treasury
    },
]

def load_key() -> str:
    if not KEY_FILE.exists():
        raise SystemExit("Key tidak ada. Jalankan: bash set_bazaar_key.sh dulu.")
    k = KEY_FILE.read_text().strip()
    if not k.startswith("0x"):
        k = "0x" + k
    return k

def sign_quick_register(key, url, owner, timestamp) -> str:
    from eth_account.messages import encode_defunct
    account = Account.from_key(key)
    msg = f"quick-register:{url}:{owner}:{timestamp}"
    sig = account.sign_message(encode_defunct(text=msg))
    return sig.signature.hex()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="hanya verifikasi key/address, no POST")
    args = ap.parse_args()

    key = load_key()
    account = Account.from_key(key)
    owner = account.address

    print(f"Wallet sedang dipakai: {owner}")
    if owner.lower() != EXPECTED_OWNER.lower():
        print(f"❌ TIDAK COCOK dengan x402 Treasury ({EXPECTED_OWNER}).")
        raise SystemExit(2)
    print("✅ Key menguat ke x402 Treasury — cocok utk sign quick-register.")
    print(f"   Payments will route to KB Treasury: {KB_TREASURY}")

    if args.verify:
        print("Verify OK. Telah siap utk daftarkan service. Jalankan tanpa --verify utk submit.")
        return

    for s in SERVICES:
        ts = int(time.time() * 1000)
        sig = sign_quick_register(key, s["url"], owner.lower(), ts)
        body = {
            "url": s["url"],
            "ownerAddress": owner.lower(),  # Signer (old treasury)
            "price": s["price"],
            "name": s["name"],
            "signature": sig,
            "timestamp": ts,
            "description": s["desc"],
        }
        print(f"\nRegistering: {s['name']} @ {s['url']} (${s['price']})")
        print(f"  Owner (signer): {owner.lower()}")
        print(f"  PayTo (payments): {s.get('pay_to', KB_TREASURY)}")
        try:
            r = requests.post(f"{SERVER}/quick-register", json=body, timeout=30)
            print(f"  HTTP {r.status_code}")
            try:
                print("  ", json.dumps(r.json(), indent=2)[:800])
            except Exception:
                print("  raw:", r.text[:300])
        except Exception as e:
            print("  ERR:", e)

if __name__ == "__main__":
    main()
