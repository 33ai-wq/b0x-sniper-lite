#!/usr/bin/env python3
"""Fund test-buyer with ETH then send USDC"""
import os
import json
import requests
from eth_account import Account
from web3 import Web3

# Fund from this wallet (has ETH)
FUNDER_PRIVATE_KEY = os.getenv("FUNDER_PRIVATE_KEY")  # Need to set this
# Or use a known funded wallet

# Test-buyer
TEST_BUYER_PK = "6800edd38d44875c99c6b83a6f0257a70ac9c2c32acb99ceae3852c6471b1322"
TEST_BUYER = "0x47da2ae8C7912C2c40927830a301B29a3A21EBCC"
KB_TREASURY = "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
AMOUNT_ATOMIC = 30000  # 0.03 USDC

BASE_RPC = "https://mainnet.base.org"

USDC_ABI = json.loads('''[
    {"constant": false, "inputs": [{"name": "to", "type": "address"}, {"name": "value", "type": "uint256"}], "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
    {"constant": true, "inputs": [{"name": "account", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"}
]''')

def main():
    # Check if test-buyer has ETH
    acct = Account.from_key(TEST_BUYER_PK)
    w3 = Web3(Web3.HTTPProvider(BASE_RPC))
    
    eth_balance = w3.eth.get_balance(acct.address)
    print(f"Test-buyer ETH balance: {eth_balance/1e18} ETH")
    
    if eth_balance == 0:
        print("Test-buyer needs ETH for gas. Send ~0.001 ETH to:", acct.address)
        return
    
    usdc = w3.eth.contract(address=w3.to_checksum_address(USDC_BASE), abi=USDC_ABI)
    usdc_balance = usdc.functions.balanceOf(acct.address).call()
    print(f"Test-buyer USDC balance: {usdc_balance/1e6} USDC")
    
    if usdc_balance < AMOUNT_ATOMIC:
        print(f"Insufficient USDC (need {AMOUNT_ATOMIC/1e6})")
        return
    
    # Send USDC
    nonce = w3.eth.get_transaction_count(acct.address)
    
    tx = usdc.functions.transfer(
        w3.to_checksum_address(KB_TREASURY),
        AMOUNT_ATOMIC
    ).build_transaction({
        'from': acct.address,
        'nonce': nonce,
        'gas': 100000,
        'maxFeePerGas': w3.to_wei('1', 'gwei'),
        'maxPriorityFeePerGas': w3.to_wei('1', 'gwei'),
        'chainId': 8453
    })
    
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    tx_hash_hex = tx_hash.hex()
    print(f"Transaction sent: {tx_hash_hex}")
    
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    print(f"Confirmed! Block: {receipt.blockNumber}, Gas used: {receipt.gasUsed}")
    
    # Verify KB treasury received
    kb_balance = usdc.functions.balanceOf(KB_TREASURY).call()
    print(f"KB Treasury USDC balance: {kb_balance/1e6} USDC")
    
    return tx_hash_hex

if __name__ == "__main__":
    main()
