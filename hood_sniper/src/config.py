"""hood_sniper.config — runtime knobs.

Override any of these via environment variables matching the upper-case
key (e.g. `ARCUS_BASE_URL`, `BLOCKSCOUT_BASE_URL`). Defaults match the
verified endpoints documented in the parent skill (July 2026).
"""

import os


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


# ─── Arcus REST ────────────────────────────────────────────────
ARCUS_BASE_URL  = _env("ARCUS_BASE_URL",  "https://api.arcus.xyz")
ARCUS_DOCS_URL  = _env("ARCUS_DOCS_URL",  "https://docs.arcus.xyz/llms.txt")

# ─── RH Chain canonical RPC ────────────────────────────────────
# chain_id 4663, ETH-style L2 (Arbitrum tech). May be DNS-hijacked in
# Indo networks — see skill § "DNS layer attack". Worker code falls
# back to Arcus REST when RPC is unreachable.
RHCHAIN_RPC_URL = _env("RHCHAIN_RPC_URL", "https://rpc.mainnet.chain.robinhood.com")
RHCHAIN_CHAIN_ID = 4663

# ─── Blockscout mirror (verified-pair § references) ────────────
BLOCKSCOUT_BASE_URL = _env(
    "BLOCKSCOUT_BASE_URL", "https://robinhoodchain.blockscout.com"
)

# ─── Robidy launches (Next.js streaming payload) ───────────────
ROBIDY_BASE_URL = _env("ROBIDY_BASE_URL", "https://robidy.app")

# ─── Radar behaviour ──────────────────────────────────────────
RADAR_POLL_INTERVAL_SEC = int(_env("RADAR_POLL_INTERVAL_SEC", "60"))
RADAR_HISTORY_PATH      = _env(
    "RADAR_HISTORY_PATH",
    "/root/prpo_ai/hood_sniper/radar_history.json"
)
RADAR_BASELINE_PATH     = _env(
    "RADAR_BASELINE_PATH",
    "/root/prpo_ai/hood_sniper/radar_baseline.json"
)
RADAR_FREE_EVENT_LIMIT  = int(_env("RADAR_FREE_EVENT_LIMIT", "5"))
RADAR_RECENT_HOURS      = int(_env("RADAR_RECENT_HOURS", "24"))

# ─── Thresholds ────────────────────────────────────────────────
VOLUME_SPIKE_RATIO      = float(_env("VOLUME_SPIKE_RATIO", "5.0"))
VOLUME_SPIKE_FLOOR_USD  = float(_env("VOLUME_SPIKE_FLOOR_USD", "1000"))
NEW_CONTRACT_LOOKBACK_BLOCKS = int(_env("NEW_CONTRACT_LOOKBACK_BLOCKS", "7200"))
