"""hood_sniper — Robinhood Chain discovery radar.

The detection engine polls four sources, dedupes by event-id, scores
delta vs rolling-24h baseline, and emits a ranked JSON feed. Used by:

  • worker/src/index.js  — CF Worker x402-paid radar endpoint
  • scripts/radar.py     — local cron/scheduled fetch
  • scripts/x_alert.py   — push alerts to X (Bos handles credentials)

Source polling is purposely defensive — every upstream call has a
fallback path documented in the parent skill:
  robinhood-chain-arcus-airdrop § "Alternate intel when RPC is unreachable".

Output schema (stable contract for endpoints + cron jobs):

    {
      "generated_at": "2026-07-16T22:00:00Z",
      "sources_polled": ["arcus", "blockscout", "robidy"],
      "events": [
        {
          "id": "<sha1>",
          "ts": "2026-07-16T21:55:00Z",
          "source": "arcus",
          "kind": "market_online" | "volume_spike" | "new_contract"
                  | "new_erc20" | "new_launchpage" | "robidy_phase_start",
          "severity": "info" | "watch" | "alert" | "alpha",
          "title": "...short headline...",
          "url": "https://...",
          "chain_id": 4663,
          "context": {...source-specific...}
        }
      ],
      "stats": {"events_total": N, "alert_alpha": K, ...},
      "baseline": {"arcus_markets_online": M, "arcus_total_volume_24h": V}
    }
"""
