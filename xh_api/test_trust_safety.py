#!/usr/bin/env python3
"""Uji nyata dua modul baru: x402_trust + token_safety (lewat helper server yang asli)."""
import json
import sys

sys.path.insert(0, "/home/ubuntu/prpo_ai/xh_api")
import server  # noqa: E402
import token_safety  # noqa: E402
import x402_trust  # noqa: E402

tctx = x402_trust.Ctx(check_ssrf=server._check_ssrf, decode_challenge=server._decode_challenge,
                      rpc=server._rpc, erc20=server.erc20_call, is_address=server._is_address,
                      alchemy_url=server._DEDICATED_RPC)
sctx = token_safety.Ctx(rpc=server._rpc, erc20=server.erc20_call, is_address=server._is_address,
                        alchemy_url=server._DEDICATED_RPC)

what = sys.argv[1] if len(sys.argv) > 1 else "trust"

if what == "trust":
    for url in ["https://xhagents.xyz/api/kb/ask",
                "https://xhagents.xyz/api/hundred-x-hunter",
                "https://pronomad.duckdns.org/v1/meme-hunter"]:
        r = x402_trust.assess(tctx, url, "POST", {})
        print(f"\n=== {url}")
        print(f"    skor {r['score']} ({r['verdict']}) | status {r.get('status')} | "
              f"poin {r['points']} | penalti {r.get('penalty')}")
        print(f"    payTo: {json.dumps({k: v for k, v in (r.get('payto_inspection') or {}).items() if k != 'address'})[:220]}")
        for f in (r.get("findings") or [])[:6]:
            print(f"    - {f}")
else:
    for tok in ["0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",   # USDC
                "0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed",   # DEGEN
                "0xB2000000000000000000004c27f6523082f41D01"]:  # Basecat
        r = token_safety.assess(sctx, tok)
        print(f"\n=== {tok} {r.get('symbol')}")
        print(f"    skor {r['score']} ({r['verdict']}) | poin {r['points']}")
        print(f"    likuiditas ${(r.get('market') or {}).get('liquidity_usd', 0):,.0f} | "
              f"top10 {r.get('top10_share_pct')}% | verified {r['contract'].get('verified')} | "
              f"proxy {r['contract'].get('proxy', {}).get('upgradeable')}")
        for f in (r.get("findings") or [])[:6]:
            print(f"    - {f}")
