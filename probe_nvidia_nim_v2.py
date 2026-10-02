#!/usr/bin/env python3
"""
Probe kandidat fallback yang benar-benar ada di katalog NIM.
Tujuan: konfirmasi Nemotron-3-Ultra-550b callable; tegaskan Claude-Opus-5 &
Anthropic-Fable-5 TIDAK ada di NIM (cek di semua endpoint umum).
"""
import os, json, ssl, urllib.request, urllib.error, time

KEY = os.environ["NVIDIA_NIM_API_KEY"]
BASE = "https://integrate.api.nvidia.com"

CANDIDATES = [
    # Kandidat paling dekat dengan "Nemotron 3 Ultra" di katalog NIM
    ("nvidia/nemotron-3-ultra-550b-a55b",        "Nemotron-3-Ultra-550b"),
    ("nvidia/llama-3.1-nemotron-ultra-253b-v1",  "Nemotron-Ultra-253b-v1"),
    # Konfirmasi negatif: Claude Opus 5 dan Anthropic Fable 5
    ("anthropic/claude-opus-5",                  "Claude-Opus-5-NEGATIVE"),
    ("anthropic/claude-opus-4-5",                "Claude-Opus-4.5-NEGATIVE"),
    ("anthropic/fable-5",                        "Anthropic-Fable-5-NEGATIVE"),
    # Sanity: minimax-m3 (model aktif) harus tetap hidup
    ("minimaxai/minimax-m3",                     "minimax-m3-PRIMARY"),
    # AVOID-list (Boss minta JANGAN jadi fallback)
    ("nvidia/llama-3.3-nemotron-super-49b-v1.5", "Nemotron-Super-49B-AVOID"),
    ("nvidia/nemotron-3-super-120b-a12b",        "Nemotron-3-Super-120B-AVOID"),
    ("meta/llama-3.1-70b-instruct",              "LLaMA-3.1-70B-AVOID"),
]

PROMPT = "Reply with EXACTLY 3 lines: MODEL: <id> | STATUS: OK | REASON: 1 sentence why fit for BOSSY Nomad-7 fallback."

def hit(path, payload=None, method="GET"):
    url = f"{BASE}{path}"
    headers = {"Authorization": f"Bearer {KEY}", "Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
        method = "POST"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
            return {"http": r.status, "elapsed": round(time.time()-t0,2),
                    "body": r.read().decode("utf-8", errors="replace")[:800]}
    except urllib.error.HTTPError as e:
        return {"http": e.code, "elapsed": round(time.time()-t0,2),
                "body": e.read().decode("utf-8", errors="replace")[:400]}
    except Exception as e:
        return {"http": None, "elapsed": round(time.time()-t0,2),
                "body": f"{type(e).__name__}: {e}"}

print(f"KEY len={len(KEY)}  BASE={BASE}\n")

results = []
for mid, alias in CANDIDATES:
    print(f"--- {alias}  ({mid}) ---")
    payload = {"model": mid, "messages":[{"role":"user","content":PROMPT}],
               "max_tokens":80, "temperature":0.2, "stream":False}
    res = hit("/v1/chat/completions", payload)
    results.append((mid, alias, res))
    print(f"  HTTP {res['http']}  elapsed {res['elapsed']}s")
    if res['http'] == 200:
        try:
            j = json.loads(res['body'])
            content = j["choices"][0]["message"]["content"].replace("\n"," | ")
            print(f"  model_returned: {j.get('model')}")
            print(f"  reply: {content[:200]}")
            print(f"  usage: {j.get('usage')}")
        except Exception as e:
            print(f"  parse_err: {e}")
            print(f"  raw: {res['body'][:200]}")
    else:
        print(f"  body: {res['body'][:200]}")
    print()

# Summary
print("=" * 84)
print(f"{'MODEL_ID':<46}  {'ALIAS':<28}  {'HTTP':<5}  {'OK'}")
print("-" * 84)
for mid, alias, res in results:
    ok = "YES" if res['http'] == 200 else "NO"
    print(f"{mid:<46}  {alias:<28}  {str(res['http']):<5}  {ok}")
print("=" * 84)

out = "/home/ubuntu/prpo_ai/probe_nvidia_nim_v2_result.json"
with open(out, "w") as f:
    json.dump([{"model_id":m,"alias":a,"result":r} for m,a,r in results], f, indent=2, default=str)
print(f"\nJSON saved: {out}")

priority_ok = any(r['http']==200 for m,_,r in results
                  if "NEGATIVE" not in [a for _,a,_ in [(m,a,r) for m,a,r in results] if True][:0])  # noop
priority_ok = any(r['http']==200 for m,_,r in results if m in [
    "nvidia/nemotron-3-ultra-550b-a55b","nvidia/llama-3.1-nemotron-ultra-253b-v1"])
print(f"\n>>> Any Nemotron-Ultra reachable? {priority_ok}")
