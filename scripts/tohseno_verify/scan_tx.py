#!/usr/bin/env python3
"""Scan a Base tx by hash: read receipt + trace from/to/value/method."""
import sys, requests

RPC_URLS = [
    "https://base.meowrpc.com",
    "https://mainnet.base.org",
    "https://base.publicnode.com",
]

def rpc(method, params):
    for u in RPC_URLS:
        try:
            r = requests.post(u, json={"jsonrpc":"2.0","method":method,"params":params,"id":1}, timeout=10)
            r.raise_for_status()
            d = r.json()
            if "error" in d:
                continue
            return d.get("result"), None
        except Exception as e:
            last = str(e)
    return None, last

def fetch_tx(tx_hash):
    # get transaction
    tx, err = rpc("eth_getTransactionByHash", [tx_hash])
    if err: return None, err
    # get receipt
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
    if not hashes:
        print("Usage: scan_tx.py <txhash1> [txhash2] ...")
        return
    for h in hashes:
        print("="*70)
        print(f"TX HASH: {h}")
        try:
            (tx, rcpt), err = fetch_tx(h)
            if err:
                print(f"[ERROR] {err}")
                continue
            if tx is None:
                print("[NOT FOUND] tx not found on Base")
                continue
            print(f"  Block:        {hex_int(tx.get('blockNumber'))}")
            print(f"  From:         {tx.get('from')}")
            print(f"  To:           {tx.get('to')}")
            print(f"  Value (ETH):  {wei_to_eth(tx.get('value')):.8f}")
            print(f"  Gas:          {hex_int(tx.get('gas'))}")
            print(f"  Gas Price:    {hex_int(tx.get('gasPrice'))}")
            print(f"  Nonce:        {hex_int(tx.get('nonce'))}")
            print(f"  Input (len):  {len(tx.get('input','0x'))} chars")
            inp = tx.get('input','')
            if inp and inp != '0x':
                # show method selector (first 4 bytes) + decoded hints
                sel = inp[:10]
                print(f"  Method ID:    {sel}")
                # If 4byte signature dictionary is available, decode
                try:
                    r = requests.get(f"https://api.openchain.xyz/signature-database/v1/lookup?function={sel}&filter=true", timeout=8)
                    if r.status_code == 200:
                        d = r.json()
                        fns = d.get('result',{}).get('function',{}).get(sel,[])
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
                        # topic[0] = event sig
                        evt = topics[0]
                        try:
                            r = requests.get(f"https://api.openchain.xyz/signature-database/v1/lookup?event={evt}&filter=true", timeout=8)
                            if r.status_code == 200:
                                d = r.json()
                                evs = d.get('result',{}).get('event',{}).get(evt,[])
                                if evs:
                                    print(f"        event: {evs[0].get('name')} ({evs[0].get('signature')})")
                        except Exception:
                            pass
        except Exception as e:
            print(f"[ERROR] {e}")

if __name__ == "__main__":
    main()
