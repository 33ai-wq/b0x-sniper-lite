#!/usr/bin/env python3
"""Scan a tx on Robinhood Chain mainnet (chainId 4663)."""
import sys, requests

# Robinhood Chain mainnet
RH_RPCS = [
    "https://rpc.robinhoodchain.org",
    "https://mainnet.rpc.robinhood.com",
    "https://4663.rpc.thirdweb.com",
]

def rpc(method, params):
    for u in RH_RPCS:
        try:
            r = requests.post(u, json={"jsonrpc":"2.0","method":method,"params":params,"id":1}, timeout=10)
            r.raise_for_status()
            d = r.json()
            if "error" in d and d["error"].get("code") != -32000:
                # -32000 = "execution reverted"-style errors, treat as empty result; not found = null result
                continue
            if d.get("result") is None and "error" in d:
                return None, None  # not found
            return d.get("result"), None
        except Exception as e:
            last = str(e)
    return None, last

def fetch_tx(tx_hash):
    tx, err = rpc("eth_getTransactionByHash", [tx_hash])
    if err: return None, err
    rcpt, err = rpc("eth_getTransactionReceipt", [tx_hash])
    if err: return None, err
    return (tx, rcpt), None

def hex_int(x):
    if x is None: return None
    if isinstance(x, str) and x.startswith("0x"):
        return int(x, 16)
    return x

def wei_to_eth(x):
    return hex_int(x) / 1e18 if x else 0

def main():
    hashes = sys.argv[1:]
    for h in hashes:
        print("="*70)
        print(f"TX HASH: {h}")
        try:
            (tx, rcpt), err = fetch_tx(h)
            if err:
                print(f"[ERROR] {err}")
                continue
            if tx is None:
                print("[NOT FOUND] tx not found on Robinhood Chain")
                continue
            print(f"  Block:        {hex_int(tx.get('blockNumber'))}")
            print(f"  From:         {tx.get('from')}")
            print(f"  To:           {tx.get('to')}")
            print(f"  Value (ETH):  {wei_to_eth(tx.get('value')):.8f}")
            print(f"  Gas:          {hex_int(tx.get('gas'))}")
            print(f"  Gas Price:    {hex_int(tx.get('gasPrice'))}")
            print(f"  Nonce:        {hex_int(tx.get('nonce'))}")
            inp = tx.get('input','0x')
            print(f"  Input (len):  {len(inp)} chars")
            if inp and inp != '0x':
                sel = inp[:10]
                print(f"  Method ID:    {sel}")
                try:
                    r = requests.get(f"https://api.openchain.xyz/signature-database/v1/lookup?function={sel}&filter=true", timeout=8)
                    if r.status_code == 200:
                        fns = r.json().get('result',{}).get('function',{}).get(sel,[])
                        if fns:
                            print(f"  Decoded:      {fns[0].get('name')} {fns[0].get('signature')}")
                except Exception:
                    pass
            if rcpt:
                print(f"  Status:       {'SUCCESS' if hex_int(rcpt.get('status'))==1 else 'FAILED'}")
                print(f"  Gas Used:     {hex_int(rcpt.get('gasUsed'))}")
                logs = rcpt.get('logs',[])
                print(f"  Logs:         {len(logs)} events")
                for i, lg in enumerate(logs[:5]):
                    addr = lg.get('address')
                    topics = lg.get('topics',[])
                    print(f"    [{i}] contract={addr} topics={len(topics)}")
                    if topics:
                        evt = topics[0]
                        try:
                            r = requests.get(f"https://api.openchain.xyz/signature-database/v1/lookup?event={evt}&filter=true", timeout=8)
                            if r.status_code == 200:
                                evs = r.json().get('result',{}).get('event',{}).get(evt,[])
                                if evs:
                                    print(f"        event: {evs[0].get('name')} ({evs[0].get('signature')})")
                        except Exception:
                            pass
        except Exception as e:
            print(f"[ERROR] {e}")

if __name__ == "__main__":
    main()
