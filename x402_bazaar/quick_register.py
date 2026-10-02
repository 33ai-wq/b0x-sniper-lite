#!/usr/bin/env python3
"""
quick_register.py — daftarkan endpoint x402 yang SUDAH VALID ke x402bazaar.org
via POST /quick-register (signature dari wallet owner = treasury Base 0x57ee...f357).

JANGAN MENGUBAH kode endpoint (#1/#2) — hanya mendaftarkannya.
Sebelum dipakai: private key harus sudah tersimpan lewat set_bazaar_key.sh
(key file .bazaar_key mode 600). Script ini VERIFIKASI address dulu sebelum POST:
kalau key tidak menguat ke 0x57ee...f357, ia TOLAK submit (aman).

Endpoint yang didaftarkan:
  #1 x402-cf-worker.mulberry-boar.workers.dev  (Base)
  #2 b0x402-data.mulberry-boar.workers.dev      (Base)

Usage:
  /home/ubuntu/prpo_ai/venv/bin/python quick_register.py          # daftarkan #1 & #2
  /home/ubuntu/prpo_ai/venv/bin/python quick_register.py --verify  # hanya verifikasi, no POST
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
EXPECTED_OWNER = "0x57eec52d76a4a78d4562fc2564101a4bd2e3f357"

# Endpoint yang didaftarkan + info (price dalam USDC per call). JANGAN ubah kode upstream-nya.
SERVICES = [
    {
        "name": "b0x402-core-base",
        "url": "https://x402-cf-worker.mulberry-boar.workers.dev/v1/meme-hunter",
        "price": 0.01,
        "desc": "XH Agents b0x402 core - Base x402 endpoint (meme-hunter)",
    },
    {
        "name": "b0x402-data-token-safety",
        "url": "https://b0x402-data.mulberry-boar.workers.dev/v1/token-safety",
        "price": 0.10,
        "desc": "XH Agents b0x402 data - Base x402 endpoint (token safety scanner, honeypot detection)",
    },
    {
        "name": "b0x402-data-gas-tracker",
        "url": "https://b0x402-data.mulberry-boar.workers.dev/v1/gas-tracker",
        "price": 0.40,
        "desc": "XH Agents b0x402 data - Base x402 endpoint (multi-chain gas tracker)",
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
    # HexBytes.hex() sudah "0x..." prefix + JSON-serializable string
    return sig.signature.hex()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="hanya verifikasi key/address, no POST")
    ap.add_argument("--endpoint", default=None, help="hanya daftarkan satu: 1 atau 2")
    args = ap.parse_args()

    key = load_key()
    account = Account.from_key(key)
    owner = account.address

    print(f"Wallet sedang dipakai: {owner}")
    if owner.lower() != EXPECTED_OWNER.lower():
        print("❌ TIDAK COCOK dengan treasury Base x402 (0x57ee...f357).")
        print("   Ini private key yang lain. TIDAK melanjutkan submit.")
        raise SystemExit(2)
    print("✅ Key menguat ke 0x57ee...f357 — cocok utk sign quick-register.")

    if args.verify:
        print("Verify OK. Telah siap utk daftarkan service. Jalankan tanpa --verify utk submit.")
        return

    services = [s for i, s in enumerate(SERVICES, 1) if args.endpoint in (None, str(i))]

    # PENTING: server merekonstruksi message dgn ownerAddress LOWERCASE (schema Zod
    # lowercases wallet + CHECK constraint DB). Signature harus atas owner lowercase,
    # dan body ownerAddress juga harus lowercase, atau 401/signature mismatch & 500.
    owner_lc = owner.lower()

    for s in services:
        ts = int(time.time() * 1000)
        sig = sign_quick_register(key, s["url"], owner_lc, ts)
        body = {
            "url": s["url"],
            "ownerAddress": owner_lc,
            "price": s["price"],
            "name": s["name"],
            "signature": sig,
            "timestamp": ts,
            "description": s["desc"],
        }
        print(f"\nRegistering: {s['name']} @ {s['url']} (${s['price']})")
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