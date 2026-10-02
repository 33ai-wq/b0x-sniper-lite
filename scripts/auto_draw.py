#!/usr/bin/env python3
"""
LitCount Auto-Draw Automation Script
=====================================
Calls triggerDrawPhase() and executeDraw() when pool conditions are met.
Run via cron: * * * * * /root/prpo_ai/litcount_repo/scripts/auto_draw.py >> /var/log/litcount_draw.log 2>&1

Network  : LitVM LitForge Testnet (chainId: 4441)
RPC      : https://liteforge.rpc.caldera.xyz/http
Contract : 0x7903e5B54913Fd67dA541F478b17c8B342C82b83
Treasury : 0xF34900299e6f526c4e1b5967b87A880fB880d2B7
"""

import os
import sys
import json
import time
import logging
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────
RPC_URL    = "https://liteforge.rpc.caldera.xyz/http"
CONTRACT   = "0x7903e5B54913Fd67dA541F478b17c8B342C82b83"
TREASURY   = "0xF34900299e6f526c4e1b5967b87A880fB880d2B7"
PRIVATE_KEY = os.environ.get("LITCOUNT_DEPLOYER_KEY", "").strip()
LOCK_FILE  = "/tmp/litcount_draw.lock"
LOG_FILE   = "/var/log/litcount_draw.log"

# Pool constants (from contract)
POOL_DURATION = 21 * 3600   # 21 hours in seconds
DRAW_WINDOW   = 21 * 60    # 21 minutes in seconds
MIN_USERS     = 21

# ── Logging ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("litcount")

# ── ABI ─────────────────────────────────────────────────────────────
LITCOUNT_POOL_ABI = [
    {
        "name": "getPoolStatus",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [
            {"name": "poolId",             "type": "uint256"},
            {"name": "participantCount",   "type": "uint256"},
            {"name": "totalStaked",        "type": "uint256"},
            {"name": "timeLeft",           "type": "uint256"},
            {"name": "inDrawPhase",        "type": "bool"},
            {"name": "jackpotEstimate",    "type": "uint256"},
            {"name": "stakerRewardEstimate","type": "uint256"},
        ],
    },
    {
        "name": "getDrawPhaseTimeLeft",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "triggerDrawPhase",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [],
        "outputs": [],
    },
    {
        "name": "executeDraw",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [],
        "outputs": [],
    },
    {
        "name": "forceReset",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [],
        "outputs": [],
    },
    {
        "name": "currentPoolId",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "isDrawPhase",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "drawExecuted",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "poolStartTime",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "lastWinner",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
    {
        "name": "getParticipantCount",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

# ── HTTP-based JSON-RPC ──────────────────────────────────────────────
import urllib.request
import urllib.error

def rpc(method: str, params: list = None) -> dict:
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "params": params or [],
        "id": 1,
    }).encode()
    req = urllib.request.Request(
        RPC_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def eth_call(to: str, data: str) -> dict:
    return rpc("eth_call", [{"to": to, "data": data}, "latest"])

def eth_send_raw_transaction(raw_tx: str) -> dict:
    return rpc("eth_sendRawTransaction", [raw_tx])

def eth_get_transaction_count(addr: str) -> str:
    return rpc("eth_getTransactionCount", [addr, "pending"])

def eth_gas_price() -> int:
    return int(rpc("eth_gasPrice", []), 16)

def eth_chain_id() -> int:
    return int(rpc("eth_chainId", []), 16)

# ── Contract helpers ─────────────────────────────────────────────────
import eth_abi

def encode_abi(fn_name: str, types: list, args: list) -> str:
    selector = eth_abi.abi.encode_abi([fn_name], [types])
    if args:
        data = eth_abi.abi.encode(types, args)
        return selector + data.hex()[8:]  # strip "0x" + 4-byte selector prefix
    return selector

def call_view(fn_name: str, types: list = [], args: list = []) -> dict:
    data = encode_abi(fn_name, types, args)
    return eth_call(CONTRACT, "0x" + data)

def pool_status() -> dict:
    """Returns (poolId, participantCount, totalStaked, timeLeft, inDrawPhase, jackpot, stakerReward)"""
    result = call_view("getPoolStatus")
    if result.get("error"):
        log.error(f"getPoolStatus error: {result['error']}")
        return None
    # Result is a list of values
    try:
        data = eth_abi.abi.decode_abi(
            ["uint256","uint256","uint256","uint256","bool","uint256","uint256"],
            bytes.fromhex(result["result"][2:])
        )
        return {
            "poolId":              data[0],
            "participantCount":    data[1],
            "totalStaked":         data[2] / 1e18,
            "timeLeft":            data[3],
            "inDrawPhase":         data[4],
            "jackpot":             data[5] / 1e18,
            "stakerReward":        data[6] / 1e18,
        }
    except Exception as e:
        log.error(f"Failed to decode pool status: {e} | result: {result}")
        return None

def draw_phase_time_left() -> int:
    result = call_view("getDrawPhaseTimeLeft")
    if result.get("error"):
        return 0
    try:
        data = eth_abi.abi.decode_abi(["uint256"], bytes.fromhex(result["result"][2:]))
        return data[0]
    except:
        return 0

def is_draw_phase() -> bool:
    result = call_view("isDrawPhase")
    if result.get("error"):
        return False
    try:
        data = eth_abi.abi.decode_abi(["bool"], bytes.fromhex(result["result"][2:]))
        return data[0]
    except:
        return False

def was_draw_executed() -> bool:
    result = call_view("drawExecuted")
    if result.get("error"):
        return False
    try:
        data = eth_abi.abi.decode_abi(["bool"], bytes.fromhex(result["result"][2:]))
        return data[0]
    except:
        return False

def participant_count() -> int:
    result = call_view("getParticipantCount")
    if result.get("error"):
        return 0
    try:
        data = eth_abi.abi.decode_abi(["uint256"], bytes.fromhex(result["result"][2:]))
        return data[0]
    except:
        return 0

# ── Transaction building ─────────────────────────────────────────────
def build_tx(fn_name: str, types: list = [], args: list = []):
    """Build signed transaction for the given function call."""
    if not PRIVATE_KEY:
        raise RuntimeError("LITCOUNT_DEPLOYER_KEY env not set")

    # Get sender from key
    from eth_keys import keys
    pk_bytes = bytes.fromhex(PRIVATE_KEY.replace("0x", ""))
    pk = keys.PrivateKey(pk_bytes)
    sender = pk.public_key.to_checksum_address()

    nonce  = int(eth_get_transaction_count(sender), 16)
    gas_price = eth_gas_price()

    data = encode_abi(fn_name, types, args)
    tx_params = {
        "from":   sender,
        "to":     CONTRACT,
        "data":   "0x" + data,
        "gas":    hex(500000),
        "gasPrice": hex(gas_price),
        "nonce":  hex(nonce),
        "chainId": hex(4441),
    }

    # Estimate gas (optional, skip if fails)
    try:
        est = rpc("eth_estimateGas", [tx_params])
        if not est.get("error"):
            tx_params["gas"] = hex(int(est["result"], 16) + 50000)
    except:
        pass

    # Sign
    tx = {
        "to":         CONTRACT,
        "data":       "0x" + data,
        "gas":        tx_params["gas"],
        "gasPrice":   hex(gas_price),
        "nonce":      hex(nonce),
        "chainId":    4441,
    }
    signed = pk.sign_transaction(tx)
    return signed.rawTransaction.hex()

def send_tx(fn_name: str, types: list = [], args: list = []) -> bool:
    """Build, sign, and send a transaction. Returns True on success."""
    try:
        raw = build_tx(fn_name, types, args)
        result = eth_send_raw_transaction("0x" + raw)
        if "result" in result:
            log.info(f"  ✅ {fn_name} tx sent: {result['result'][:20]}...")
            return True
        else:
            log.error(f"  ❌ {fn_name} failed: {result}")
            return False
    except Exception as e:
        log.error(f"  ❌ {fn_name} error: {e}")
        return False

# ── Lock ─────────────────────────────────────────────────────────────
def acquire_lock() -> bool:
    """Only one instance runs at a time."""
    lock = Path(LOCK_FILE)
    if lock.exists():
        # Check if process is alive
        try:
            pid = int(lock.read_text().strip())
            import os
            os.kill(pid, 0)
            log.debug(f"Lock held by PID {pid}, skipping")
            return False
        except (ValueError, ProcessLookupError, OSError):
            log.info("Stale lock found, taking over")
            pass
    lock.write_text(str(os.getpid()))
    return True

def release_lock():
    Path(LOCK_FILE).unlink(missing_ok=True)

# ── Main ─────────────────────────────────────────────────────────────
def main():
    log.info("=== LitCount Auto-Draw Run ===")
    if not acquire_lock():
        log.info("Already running, exiting")
        return

    try:
        # Verify network
        chain_id = eth_chain_id()
        if chain_id != 4441:
            log.error(f"Wrong network: chainId={chain_id}, expected 4441 (LitVM)")
            return

        status = pool_status()
        if not status:
            log.error("Cannot read pool status, exiting")
            return

        pool_id   = status["poolId"]
        p_count   = status["participantCount"]
        time_left = status["timeLeft"]
        in_draw   = status["inDrawPhase"]

        log.info(f"Pool #{pool_id}: {p_count} users | timeLeft={time_left}s | inDrawPhase={in_draw}")

        if not in_draw:
            # ── Pool Phase ──
            if time_left == 0 and p_count >= MIN_USERS:
                log.info("🟡 Pool expired with >=21 users — triggering draw phase!")
                send_tx("triggerDrawPhase")
            elif time_left == 0 and p_count < MIN_USERS:
                log.info(f"🟡 Pool expired but only {p_count} users (<21) — pool stays open")
            else:
                remaining = time_left // 60
                log.info(f"⏳ Pool running, {remaining}m until trigger eligibility")

        else:
            # ── Draw Phase ──
            draw_time_left = draw_phase_time_left()
            executed = was_draw_executed()

            if not executed:
                if draw_time_left > 0:
                    log.info(f"🎲 Draw phase active, {draw_time_left}s left — executing draw")
                    send_tx("executeDraw")
                elif draw_time_left == 0:
                    log.warning("⏰ Draw window expired without execution — calling forceReset")
                    send_tx("forceReset")
            else:
                log.info("✅ Draw already executed this phase")

        log.info("=== Run Complete ===\n")

    finally:
        release_lock()

if __name__ == "__main__":
    main()