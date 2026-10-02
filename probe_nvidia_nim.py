#!/usr/bin/env python3
"""
Probe Nvidia NIM API key + check target model availability.
Target models (priority order):
  1. nvidia/llama-3.1-nemotron-3-ultra-253b (Nemotron 3 Ultra)
  2. anthropic/claude-opus-5           (Claude Opus 5)
  3. anthropic/fable-5                 (Anthropic Fable 5)

For BOSSY: if minimax-m3 unavailable, fallback chain uses ONLY these three.
Do NOT fallback to Nemotron-Super / LLaMA — no shared memory learning.
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
import ssl
from typing import Optional

NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"

# Targets we want to probe. (model_id, alias_for_display)
TARGETS = [
    ("nvidia/llama-3.1-nemotron-3-ultra-253b",  "Nemotron-3-Ultra"),
    ("anthropic/claude-opus-5",                 "Claude-Opus-5"),
    ("anthropic/fable-5",                       "Anthropic-Fable-5"),
    # Sanity-check: confirm Nemotron-Super is available (so we know to AVOID it as fallback)
    ("nvidia/llama-3.1-nemotron-3-super-253b",  "Nemotron-3-Super-AVOID"),
    ("meta/llama-3.1-70b-instruct",             "LLaMA-3.1-70B-AVOID"),
]

PROMPT = (
    "Reply with EXACTLY 3 lines:\n"
    "MODEL: <your model id>\n"
    "STATUS: OK\n"
    "REASON: short 1-sentence reason you are the right model for BOSSY Nomad-7 fallback."
)


def get_api_key() -> Optional[str]:
    return os.environ.get("NVIDIA_NIM_API_KEY") or os.environ.get("NVIDIA_API_KEY")


def probe_model(api_key: str, model_id: str, timeout: int = 30) -> dict:
    """Send one chat completion request, return structured result."""
    url = f"{NVIDIA_BASE}/chat/completions"
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "You are a model availability probe. Follow instructions exactly."},
            {"role": "user",   "content": PROMPT},
        ],
        "max_tokens": 120,
        "temperature": 0.2,
        "stream": False,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        },
        method="POST",
    )
    ctx = ssl.create_default_context()
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read().decode("utf-8", errors="replace")
            elapsed = time.time() - t0
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                return {"ok": False, "http": r.status, "elapsed": elapsed,
                        "error": "non-json response", "raw": raw[:400]}
            if r.status != 200:
                return {"ok": False, "http": r.status, "elapsed": elapsed,
                        "error": body.get("error", body)}
            try:
                content = body["choices"][0]["message"]["content"]
            except (KeyError, IndexError):
                content = ""
            return {
                "ok": True,
                "http": r.status,
                "elapsed": round(elapsed, 2),
                "model_returned": body.get("model", model_id),
                "content": content.strip(),
                "usage": body.get("usage", {}),
                "raw_keys": list(body.keys()),
            }
    except urllib.error.HTTPError as e:
        elapsed = time.time() - t0
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        return {"ok": False, "http": e.code, "elapsed": round(elapsed, 2),
                "error": f"HTTP {e.code}", "err_body": err_body}
    except urllib.error.URLError as e:
        return {"ok": False, "http": None, "elapsed": round(time.time() - t0, 2),
                "error": f"URLError: {e.reason}"}
    except Exception as e:
        return {"ok": False, "http": None, "elapsed": round(time.time() - t0, 2),
                "error": f"{type(e).__name__}: {e}"}


def main():
    api_key = get_api_key()
    if not api_key:
        print("FATAL: NVIDIA_NIM_API_KEY (or NVIDIA_API_KEY) is not set.", file=sys.stderr)
        sys.exit(2)

    print(f"Using NVIDIA NIM base: {NVIDIA_BASE}")
    print(f"API key present: yes (len={len(api_key)})")
    print(f"Probing {len(TARGETS)} models...\n")

    results = []
    for mid, alias in TARGETS:
        print(f"--- {alias}  ({mid}) ---")
        res = probe_model(api_key, mid)
        results.append((mid, alias, res))
        if res["ok"]:
            print(f"  HTTP {res['http']}  elapsed {res['elapsed']}s  model={res['model_returned']}")
            print(f"  usage: {res.get('usage')}")
            preview = (res.get("content") or "").replace("\n", " | ")
            if len(preview) > 200:
                preview = preview[:200] + "..."
            print(f"  reply: {preview}")
        else:
            print(f"  FAIL  http={res.get('http')}  elapsed={res.get('elapsed')}s  err={res.get('error')}")
            if res.get("err_body"):
                print(f"  body: {res['err_body']}")
        print()

    # Summary table
    print("=" * 78)
    print(f"{'MODEL_ID':<48}  {'ALIAS':<22}  {'HTTP':<6}  {'OK':<3}")
    print("-" * 78)
    for mid, alias, res in results:
        http = str(res.get("http") or "-")
        ok = "YES" if res["ok"] else "NO"
        print(f"{mid:<48}  {alias:<22}  {http:<6}  {ok:<3}")
    print("=" * 78)

    # Save full JSON
    out_path = "/home/ubuntu/prpo_ai/probe_nvidia_nim_result.json"
    with open(out_path, "w") as f:
        json.dump(
            [{"model_id": m, "alias": a, "result": r} for m, a, r in results],
            f, indent=2, default=str,
        )
    print(f"\nFull JSON saved to: {out_path}")

    # Exit code: 0 if any of the 3 priority targets OK, else 1
    priority_ok = any(r["ok"] for m, _, r in results if m in [t[0] for t in TARGETS[:3]])
    sys.exit(0 if priority_ok else 1)


if __name__ == "__main__":
    main()
