#!/usr/bin/env python3
"""Shared, tested payment verification for XH Agents (Base USDC + Solana USDC).

Why this file exists
--------------------
Both engines used to detect payments in ways that could not work or could be
abused:

* `eth_getLogs` was filtered with `address = <treasury>`, but ERC-20 `Transfer`
  logs are emitted by the **USDC contract**. The filter therefore never matched
  and no Base payment was ever detected.
* Matching was amount-only (`value >= price*0.99`) with no recipient and no tx
  binding, so an unrelated transfer could activate an ad / credit messages, and
  the same transfer could be re-credited on every call.

These helpers do it properly:
  - filter logs by token contract + topic0 Transfer + topic2 = recipient
    (+ topic1 = sender when known),
  - verify a specific tx hash from its receipt (smart-wallet / ERC-4337 safe),
  - record processed tx hashes so one payment is credited exactly once.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Iterable, Optional

import requests

USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDC_SOLANA_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

BASE_RPC = os.environ.get("XH_BASE_RPC", "https://mainnet.base.org")
# Public RPC hosts sit behind Cloudflare and answer 403 to the default python-requests
# User-Agent, and they rate-limit or time out at random — so identify ourselves and fall back.
BASE_RPC_FALLBACKS = [u.strip() for u in os.environ.get(
    "XH_BASE_RPC_FALLBACKS", "https://base-rpc.publicnode.com,https://mainnet.base.org").split(",") if u.strip()]
SOL_RPC = os.environ.get("XH_SOL_RPC", "https://api.mainnet-beta.solana.com")


# ───────────────────────────── RPC plumbing ──────────────────────────────

def _rpc(method: str, params: list, rpc: str = BASE_RPC, timeout: int = 12):
    """JSON-RPC call with a sender identity and a fallback list.

    A bare python-requests User-Agent gets 403 from the Cloudflare-fronted public RPCs,
    which used to surface as `rpc_error:403 Forbidden` on a payment that was actually fine.
    """
    last: str = ""
    # eth_getLogs: public endpoints first — a dedicated RPC on a free plan caps the block range
    # (Alchemy Free allows 10 blocks), which would fail every settlement scan.
    urls = ([u for u in BASE_RPC_FALLBACKS if u] + [rpc]) if method == "eth_getLogs" \
        else [rpc] + [u for u in BASE_RPC_FALLBACKS if u and u != rpc]
    for url in urls:
        try:
            r = requests.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                              headers={"User-Agent": "xh-agents-verify/1.0", "Content-Type": "application/json"},
                              timeout=timeout)
            r.raise_for_status()
            body = r.json()
            if body.get("error"):
                raise RuntimeError(f"{method}: {body['error']}")
            return body.get("result")
        except Exception as e:  # try the next endpoint
            last = f"{url}: {type(e).__name__} {e}"[:200]
    raise RuntimeError(f"rpc_unavailable ({last})")


def _topic_to_addr(topic: str) -> str:
    return "0x" + topic[-40:].lower()


def _addr_topic(addr: str) -> str:
    a = addr.lower()
    if a.startswith("0x"):
        a = a[2:]
    return "0x" + a.rjust(64, "0")


# ───────────────────────────── Base (EVM) ────────────────────────────────

def find_incoming_usdc(
    to_address: str,
    from_address: Optional[str] = None,
    min_atomic: int = 0,
    lookback_blocks: int = 5000,
    token: str = USDC_BASE,
    rpc: str = BASE_RPC,
) -> list[dict]:
    """USDC transfers INTO `to_address` (newest first), optionally only from one sender.

    Returns [{tx_hash, from, to, value_atomic, block}] — recipient always verified.
    """
    if not to_address:
        return []
    topics: list = [TRANSFER_TOPIC, None, _addr_topic(to_address)]
    if from_address:
        topics[1] = _addr_topic(from_address)

    latest = int(_rpc("eth_blockNumber", [], rpc), 16)
    frm = max(0, latest - max(1, int(lookback_blocks)))
    logs = _rpc(
        "eth_getLogs",
        [{
            "fromBlock": hex(frm),
            "toBlock": "latest",
            "address": token,
            "topics": topics,
        }],
        rpc,
    ) or []

    out: list[dict] = []
    want_to = to_address.lower()
    want_from = from_address.lower() if from_address else None
    want_token = token.lower()
    for lg in logs:
        # Re-check locally instead of trusting that the RPC honoured the filter:
        # public/fallback providers have been known to ignore topics.
        if str(lg.get("address", "")).lower() != want_token:
            continue
        tp = lg.get("topics") or []
        if len(tp) < 3 or str(tp[0]).lower() != TRANSFER_TOPIC:
            continue
        if _topic_to_addr(tp[2]) != want_to:
            continue
        if want_from and _topic_to_addr(tp[1]) != want_from:
            continue
        try:
            val = int(lg.get("data", "0x0"), 16)
        except Exception:
            continue
        if val < int(min_atomic):
            continue
        out.append({
            "tx_hash": str(lg.get("transactionHash", "")).lower(),
            "from": _topic_to_addr(tp[1]),
            "to": _topic_to_addr(tp[2]),
            "value_atomic": val,
            "block": int(lg.get("blockNumber", "0x0"), 16),
        })
    out.sort(key=lambda x: x["block"], reverse=True)
    return out


def verify_tx_usdc(
    tx_hash: str,
    to_address: str,
    min_atomic: int,
    from_address: Optional[str] = None,
    token: str = USDC_BASE,
    rpc: str = BASE_RPC,
    min_confirmations: int = 1,
) -> tuple[bool, str, dict]:
    """Receipt-based verification of one tx hash.

    Keyed on the Transfer *log* (not tx.from) so ERC-4337 / Base Account smart
    wallets work: there the tx sender is a bundler while the log carries the
    smart-wallet address.
    """
    if not tx_hash or not tx_hash.startswith("0x") or len(tx_hash) != 66:
        return False, "bad_tx_hash", {}
    try:
        receipt = _rpc("eth_getTransactionReceipt", [tx_hash], rpc)
    except Exception as e:  # noqa: BLE001
        return False, f"rpc_error:{e}", {}
    if not receipt:
        return False, "tx_not_found", {}
    if int(receipt.get("status", "0x0"), 16) != 1:
        return False, "tx_failed", {}

    try:
        head = int(_rpc("eth_blockNumber", [], rpc), 16)
        blk = int(receipt.get("blockNumber", "0x0"), 16)
        if (head - blk + 1) < min_confirmations:
            return False, "not_confirmed", {}
    except Exception:  # noqa: BLE001
        pass

    want_to = to_address.lower()
    want_from = from_address.lower() if from_address else None
    want_token = token.lower()

    for lg in receipt.get("logs") or []:
        if str(lg.get("address", "")).lower() != want_token:
            continue
        tp = lg.get("topics") or []
        if len(tp) < 3 or str(tp[0]).lower() != TRANSFER_TOPIC:
            continue
        if _topic_to_addr(tp[2]) != want_to:
            continue
        if want_from and _topic_to_addr(tp[1]) != want_from:
            continue
        try:
            val = int(lg.get("data", "0x0"), 16)
        except Exception:
            continue
        if val < int(min_atomic):
            continue
        return True, "ok", {
            "from": _topic_to_addr(tp[1]),
            "to": _topic_to_addr(tp[2]),
            "value_atomic": val,
            "block": int(receipt.get("blockNumber", "0x0"), 16),
        }
    return False, "no_matching_usdc_transfer", {}


# ───────────────────────────── Solana ────────────────────────────────────

def solana_ata_owner(token_account: str, rpc: str = SOL_RPC) -> tuple[Optional[str], Optional[str]]:
    """(owner_wallet, mint) of an SPL token account, or (None, None)."""
    try:
        res = _rpc("getAccountInfo", [token_account, {"encoding": "jsonParsed"}], rpc)
    except Exception:  # noqa: BLE001
        return None, None
    if not res:
        return None, None
    info = (((res.get("value") or {}).get("data") or {}).get("parsed") or {}).get("info") or {}
    return info.get("owner"), info.get("mint")


def find_incoming_solana_usdc(
    treasury: str,
    from_wallet: Optional[str] = None,
    min_atomic: int = 0,
    limit: int = 25,
    mint: str = USDC_SOLANA_MINT,
    rpc: str = SOL_RPC,
) -> list[dict]:
    """USDC transfers whose DESTINATION token account is owned by `treasury`.

    Unlike the old code this does not accept "any >=0.1 transfer out of the
    user's wallet": the destination account's owner must be the treasury.
    """
    sigs = _rpc("getSignaturesForAddress", [treasury, {"limit": max(1, int(limit))}], rpc) or []
    found: list[dict] = []
    for entry in sigs:
        sig = entry.get("signature")
        if not sig:
            continue
        try:
            tx = _rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}], rpc)
        except Exception:  # noqa: BLE001
            continue
        if not tx:
            continue
        ixs = ((tx.get("transaction") or {}).get("message") or {}).get("instructions") or []
        for ix in ixs:
            if ix.get("program") not in ("spl-token", "spl-token-2022"):
                continue
            info = (ix.get("parsed") or {}).get("info") or {}
            if not info.get("destination") or info.get("mint", mint) != mint:
                continue
            try:
                amount = int(info.get("amount", "0"))
            except Exception:
                amount = 0
            if amount < int(min_atomic):
                continue
            owner, _ = solana_ata_owner(info["destination"], rpc)
            if owner != treasury:
                continue
            if from_wallet:
                # authority is the signer for SPL transfers
                auth = info.get("authority") or info.get("source")
                if auth and auth != from_wallet:
                    continue
            found.append({
                "tx_hash": sig,
                "from": info.get("authority") or info.get("source") or "",
                "to": treasury,
                "value_atomic": amount,
                "block": tx.get("slot") or 0,
                "mint": info.get("mint", mint),
            })
    found.sort(key=lambda x: x["block"], reverse=True)
    return found


# ───────────────────────── idempotency (one tx = one credit) ─────────────

class ProcessedTxs:
    """Remembers which on-chain payments have already been credited.

    Without this, an endpoint that re-scans the chain on every call credits the
    same transfer repeatedly — free ads / free messages forever.
    """

    def __init__(self, db_path: str, table: str = "processed_txs"):
        self.db_path = db_path
        self.table = table
        conn = sqlite3.connect(db_path)
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {table}("
            "tx_hash TEXT PRIMARY KEY, purpose TEXT, ref TEXT, value_atomic INTEGER, ts INTEGER)"
        )
        conn.commit()
        conn.close()

    def seen(self, tx_hash: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(f"SELECT 1 FROM {self.table} WHERE tx_hash=?", (tx_hash.lower(),)).fetchone()
            return bool(row)
        finally:
            conn.close()

    def claim(self, tx_hash: str, purpose: str = "", ref: str = "", value_atomic: int = 0) -> bool:
        """Atomically claim a tx. False when it was already used."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                f"INSERT INTO {self.table}(tx_hash,purpose,ref,value_atomic,ts) VALUES(?,?,?,?,?)",
                (tx_hash.lower(), purpose, ref, int(value_atomic), int(time.time())),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def release(self, tx_hash: str) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(f"DELETE FROM {self.table} WHERE tx_hash=?", (tx_hash.lower(),))
            conn.commit()
        finally:
            conn.close()


PROCESSED_DB = os.environ.get("XH_PROCESSED_DB", "/home/ubuntu/prpo_ai/processed_payments.db")
processed = ProcessedTxs(PROCESSED_DB)
