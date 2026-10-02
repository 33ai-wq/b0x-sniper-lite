#!/usr/bin/env python3
"""
Verify TOHSENO token holdings for a given wallet on Base mainnet.
Uses public RPC endpoints (no API key needed).
"""

import json
import sys
import requests

# Configurable via command line or edit below
WALLET = "0x99cc2ca01841ca704c834415b5909be591f36d27"
TOKEN_CONTRACT = "0x364415f884fc93775a4c1825c1a3af1f0c2d8ba3"
# Public RPC endpoints (try multiple)
RPC_URLS = [
    "https://base.meowrpc.com",
    "https://mainnet.base.org",
    "https://base.publicnode.com",
]

def rpc_call(url, method, params=None):
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or [],
        "id": 1
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            return None, data["error"]
        return data.get("result"), None
    except Exception as e:
        return None, str(e)

def call_contract(url, contract_address, function_signature, arg=None):
    # function_signature: e.g., "balanceOf(address)"
    # Compute method id: first 4 bytes of keccak256
    import hashlib
    sig = function_signature
    method_id = "0x" + hashlib.sha3_256(sig.encode()).hexdigest()[:8]
    # encode args
    if arg is None:
        data = method_id
    else:
        # arg is address, pad to 64 hex chars (32 bytes) without 0x
        if arg.startswith("0x"):
            arg = arg[2:]
        arg = arg.lower().rjust(64, '0')
        data = method_id + arg
    result, err = rpc_call(url, "eth_call", [{"to": contract_address, "data": data}, "latest"])
    return result, err

def get_balance_of(wallet, contract):
    # returns raw integer (wei) or None
    res, err = call_contract(RPC_URLS[0], contract, "balanceOf(address)", wallet)
    if err:
        # try other rpcs
        for url in RPC_URLS[1:]:
            res, err = call_contract(url, contract, "balanceOf(address)", wallet)
            if not err:
                break
    if err:
        return None, err
    # hex to int
    try:
        return int(res, 16), None
    except:
        return None, "Failed to parse balance"

def get_token_info(contract):
    info = {}
    # name
    res, err = call_contract(RPC_URLS[0], contract, "name()")
    if not err:
        # remove null bytes and decode
        try:
            # remove 0x, then every two hex to char
            hex_str = res[2:] if isinstance(str, str) and res.startswith("0x") else res[2:]
            # but web3 returns hex string with possible padding; we'll decode
            # remove trailing zeros? Actually string is dynamic; we need to parse properly.
            # Simpler: use bytes.fromhex and strip null
            b = bytes.fromhex(res[2:])
            # find null terminator
            null_idx = b.find(b'\x00')
            if null_idx != -1:
                b = b[:null_idx]
            info["name"] = b.decode('utf-8', errors='ignore')
        except Exception:
            info["name"] = res
    else:
        info["name"] = None
    # symbol
    res, err = call_contract(RPC_URLS[0], contract, "symbol()")
    if not err:
        try:
            b = bytes.fromhex(res[2:])
            null_idx = b.find(b'\x00')
            if null_idx != -1:
                b = b[:null_idx]
            info["symbol"] = b.decode('utf-8', errors='ignore')
        except Exception:
            info["symbol"] = res
    else:
        info["symbol"] = None
    # decimals
    res, err = call_contract(RPC_URLS[0], contract, "decimals()")
    if not err:
        try:
            info["decimals"] = int(res, 16)
        except:
            info["decimals"] = None
    else:
        info["decimals"] = None
    # totalSupply
    res, err = call_contract(RPC_URLS[0], contract, "totalSupply()")
    if not err:
        try:
            raw = int(res, 16)
            if info.get("decimals") is not None:
                info["totalSupply"] = raw / (10 ** info["decimals"])
            else:
                info["totalSupplyRaw"] = raw
        except:
            info["totalSupply"] = None
    else:
        info["totalSupply"] = None
    return info

def get_code(contract):
    res, err = rpc_call(RPC_URLS[0], "eth_getCode", [contract, "latest"])
    if err:
        # try others
        for url in RPC_URLS[1:]:
            res, err = rpc_call(url, "eth_getCode", [contract, "latest"])
            if not err:
                break
    return res, err

def main():
    print(f"Checking wallet: {WALLET}")
    print(f"Token contract: {TOKEN_CONTRACT}")
    print("="*60)
    # 1. Check if contract has code
    code, err = get_code(TOKEN_CONTRACT)
    if err:
        print(f"[ERROR] Failed to get contract code: {err}")
    else:
        if code == "0x" or code == "0x0":
            print("[FAIL] Contract address has no code (not a contract).")
        else:
            print("[OK] Contract code exists.")
    # 2. Get token info
    info = get_token_info(TOKEN_CONTRACT)
    print("\nToken info:")
    for k, v in info.items():
        print(f"  {k}: {v}")
    # 3. Get balance
    bal_raw, err = get_balance_of(WALLET, TOKEN_CONTRACT)
    if err:
        print(f"\n[ERROR] Failed to get balance: {err}")
    else:
        decimals = info.get("decimals", 18)
        if bal_raw is not None:
            bal_human = bal_raw / (10 ** decimals)
            print(f"\nBalance of {WALLET}:")
            print(f"  Raw: {bal_raw}")
            print(f"  Human: {bal_human:,.{f'{decimals}' if isinstance(decimals, int) else 'f'}} {info.get('symbol', 'TOKEN')}")
        else:
            print("\n[FAIL] Could not retrieve balance.")
    print("\nDone.")

if __name__ == "__main__":
    # allow override via args
    if len(sys.argv) >= 2:
        WALLET = sys.argv[1]
    if len(sys.argv) >= 3:
        TOKEN_CONTRACT = sys.argv[2]
    main()