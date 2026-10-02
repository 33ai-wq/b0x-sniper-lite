# SENTINEL_GATE_PROTOCOL.md

## Purpose
Defines the mandatory verification checkpoint for any agent action that is irreversible, financial, or public-facing. Created in response to the earlier Nomad7/MiniMax-M3 grounding incident (repetition bug, unverified claims before self-correction) — the goal is to make sure no unverified model output becomes a real-world action without a check.

## When the gate applies
- **Trader** — before any trade, swap, or LP execution
- **Treasury** — before any outbound transfer or settlement
- **Scribe** — before publishing any numeric or factual claim

## Flow
1. Requesting agent submits a ticket to Sentinel:
   ```
   {requesting_agent, action, amount_or_claim, source_data, confidence}
   ```
2. Sentinel cross-checks the request against source data, SAFETY_RULES.md, and recent grounding history for that agent.
3. Sentinel returns one of:
   - `APPROVE` — issues a ticket ID, valid for that single action only
   - `REJECT` — with a stated reason
   - `FLAG-UNCERTAIN` — escalates to Hermes for Philo's review
4. The requesting agent may act only on `APPROVE`, and only with the matching ticket ID.
5. All ticket decisions are logged for audit (Keeper retains the log).

## Size / risk thresholds
Tune these to your comfort level:
- Trade or transfer above [0.1 SOL / 1 USD] → requires BOSSY's explicit confirmation even after Sentinel `APPROVE`
- Any `FLAG-UNCERTAIN` → goes straight to Hermes, never auto-retried by the requesting agent

## Violation handling
An agent that acts on a gated action without a valid, matching Sentinel ticket is a protocol violation:
- Keeper logs the violation
- Hermes alerts BOSSY immediately
- The offending agent's next 5 gated requests are auto-flagged for manual review, regardless of Sentinel's verdict
