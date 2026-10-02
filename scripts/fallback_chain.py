#!/usr/bin/env python3
"""
fallback_chain.py — Manual 5-tier fallback chain trigger.

Use case: kalau PRIMARY nemotron-3-ultra-550b-a55b + Hermes auto-fallback minimax-m3
juga kena rate limit / network error, pakai script ini untuk explicit
try chain sampai dapat reply OK dari salah satu tier.

Chain (updated 2026-08-14 per BOSSY directive — nemotron as PRIMARY):
  TIER 1: nvidia/nemotron-3-ultra-550b-a55b (nvidia)           — PRIMARY (agentic reasoning, 1M ctx)
  TIER 2: minimaxai/minimax-m3 (nvidia NIM)                     — FALLBACK (sharp coding, rate limited 40 RPM)
  TIER 3: minimax/minimax-m3 (OpenRouter via DeepInfra)         — EXTENDED (less rate limit via DeepInfra)
  TIER 4: z-ai/glm-5.2 (nvidia)                                 — EXTENDED (agentic workflows, coding)
  TIER 5: stepfun-ai/step-3.7-flash (nvidia)                    — EXTENDED (enterprise/coding, sparse MoE)

Usage:
  python3 fallback_chain.py "your prompt here"
  echo "your prompt" | python3 fallback_chain.py
  python3 fallback_chain.py --tier 3 "prompt"     # start from specific tier
  python3 fallback_chain.py --list                # list all tiers

Exit codes:
  0  = reply OK (printed to stdout)
  1  = all tiers failed
  2  = invalid usage
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error

ENV_FILE = "/home/ubuntu/prpo_ai/.env"

# 5-Tier Chain Definition (reordered 2026-08-14: nemotron PRIMARY)
TIERS = [
    {
        "name": "TIER 1: nvidia/nemotron-3-ultra-550b-a55b (nvidia PRIMARY)",
        "model": "nvidia/nemotron-3-ultra-550b-a55b",
        "provider": "nvidia",
        "base_url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "key_env": "NVIDIA_API_KEY",
        "strength": "Agentic reasoning, long-context (1M), RTL/coding, token-efficient",
        "max_tokens": 1024,
    },
    {
        "name": "TIER 2: minimaxai/minimax-m3 (nvidia NIM FALLBACK)",
        "model": "minimaxai/minimax-m3",
        "provider": "nvidia",
        "base_url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "key_env": "NVIDIA_API_KEY",
        "strength": "Sharp coding, debugging, tool-calling, fast (138 tok/s) — rate limited 40 RPM",
        "max_tokens": 1024,
    },
    {
        "name": "TIER 3: minimax/minimax-m3 (OpenRouter via DeepInfra)",
        "model": "minimax/minimax-m3",
        "provider": "openrouter",
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "key_env": "OPENROUTER_API_KEY",
        "strength": "Sharp coding, debugging, less rate limit via DeepInfra",
        "max_tokens": 256,  # reasoning model needs more tokens
    },
    {
        "name": "TIER 4: z-ai/glm-5.2 (nvidia EXTENDED)",
        "model": "z-ai/glm-5.2",
        "provider": "nvidia",
        "base_url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "key_env": "NVIDIA_API_KEY",
        "strength": "Agentic workflows, coding, long-horizon reasoning",
        "max_tokens": 4096,  # reasoning model
    },
    {
        "name": "TIER 5: stepfun-ai/step-3.7-flash (nvidia EXTENDED)",
        "model": "stepfun-ai/step-3.7-flash",
        "provider": "nvidia",
        "base_url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "key_env": "NVIDIA_API_KEY",
        "strength": "Enterprise/coding, sparse MoE, multimodal agentic",
        "max_tokens": 4096,  # reasoning model
    },
]


def load_env(path):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def probe_tier(tier_name, url, headers, body, timeout=60):
    """Probe 1 tier. Return (ok: bool, reply: str or None, latency_ms: int, error: str or None)."""
    t0 = time.time()
    try:
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
            # Handle reasoning models where content may be null
            msg = data["choices"][0]["message"]
            reply = msg.get("content", "").strip()
            if not reply and "reasoning" in msg:
                reply = msg["reasoning"].strip()
            latency = int((time.time() - t0) * 1000)
            return True, reply, latency, None
    except urllib.error.HTTPError as e:
        latency = int((time.time() - t0) * 1000)
        body_err = e.read().decode()[:200]
        return False, None, latency, f"HTTP {e.code}: {body_err}"
    except urllib.error.URLError as e:
        latency = int((time.time() - t0) * 1000)
        return False, None, latency, f"URL error: {e.reason}"
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return False, None, latency, f"{type(e).__name__}: {e}"


def build_chain(prompt, env, start_tier=1):
    """Build the chain from start_tier (1-indexed). Returns list of (name, url, headers, body)."""
    chain = []
    for tier in TIERS[start_tier - 1:]:
        api_key = env.get(tier["key_env"], "")
        if not api_key:
            print(f"  ⚠️  Skipping {tier['name']}: {tier['key_env']} not found in .env", file=sys.stderr)
            continue
        chain.append((
            tier["name"],
            tier["base_url"],
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json.dumps({
                "model": tier["model"],
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": tier["max_tokens"],
                "temperature": 0,
            }).encode(),
        ))
    if not chain:
        raise RuntimeError("No valid tiers with API keys found in .env")
    return chain


def print_tiers():
    """Print all available tiers."""
    print("Available tiers:")
    for i, tier in enumerate(TIERS, 1):
        print(f"  {i}. {tier['name']}")
        print(f"     Model: {tier['model']}")
        print(f"     Provider: {tier['provider']}")
        print(f"     Endpoint: {tier['base_url']}")
        print(f"     Key: {tier['key_env']}")
        print(f"     Strength: {tier['strength']}")
        print()


def main():
    # Parse args
    if len(sys.argv) < 2:
        print("Usage: python3 fallback_chain.py \"your prompt here\"", file=sys.stderr)
        print("       python3 fallback_chain.py --tier N \"prompt\"   # start from tier N", file=sys.stderr)
        print("       python3 fallback_chain.py --list                 # list all tiers", file=sys.stderr)
        sys.exit(2)

    start_tier = 1
    prompt = None

    if sys.argv[1] == "--list":
        print_tiers()
        return 0
    elif sys.argv[1] == "--tier":
        if len(sys.argv) < 4:
            print("Usage: python3 fallback_chain.py --tier N \"prompt\"", file=sys.stderr)
            sys.exit(2)
        try:
            start_tier = int(sys.argv[2])
            if not 1 <= start_tier <= len(TIERS):
                print(f"Tier must be 1-{len(TIERS)}", file=sys.stderr)
                sys.exit(2)
        except ValueError:
            print("Tier must be a number", file=sys.stderr)
            sys.exit(2)
        prompt = sys.argv[3]
    else:
        prompt = sys.argv[1]

    env = load_env(ENV_FILE)
    chain = build_chain(prompt, env, start_tier)

    print(f"Chain trigger: prompt={len(prompt)} chars, tiers={len(chain)} (start from tier {start_tier})\n", file=sys.stderr)

    for i, (name, url, headers, body) in enumerate(chain, start_tier):
        print(f"[{name}]", file=sys.stderr)
        ok, reply, latency, err = probe_tier(name, url, headers, body)
        if ok:
            print(f"  ✅ LIVE in {latency}ms", file=sys.stderr)
            print(reply)
            return 0
        else:
            print(f"  ❌ {err} ({latency}ms)", file=sys.stderr)
            if i < start_tier + len(chain) - 1:
                print(f"  → fallthrough to next tier\n", file=sys.stderr)
            else:
                print(f"\n[FATAL] all {len(chain)} tiers failed", file=sys.stderr)
                return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())