#!/usr/bin/env python3
"""Send 0.03 USDC from test-buyer to KB treasury on Base (optimized gas)"""
import os
import json
import requests
from eth_account import Account
from web3 import Web3

# Test-buyer private key (throwaway)
PRIVATE_KEY = "6800edd38d44875c99c6b83a6f0257a70ac9c2c32acb99ceae3852c6471b1322"
TEST_BUYER = "0x47da2ae8C7912C2c40927830a301B29a3A21EBCC"
KB_TREASURY = "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
AMOUNT_ATOMIC = 30000  # 0.03 USDC (6 decimals)

# Base RPC
BASE_RPC = "https://mainnet.base.org"

# USDC ABI (minimal)
USDC_ABI = json.loads('''[
    {"constant": false, "inputs": [{"name": "to", "type": "address"}, {"name": "value", "type": "uint256"}], "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
    {"constant": true, "inputs": [{"name": "account", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"}
]''')

def main():
    acct = Account.from_key(PRIVATE_KEY)
    w3 = Web3(Web3.HTTPProvider(BASE_RPC))
    
    print(f"Test-buyer: {acct.address}")
    print(f"KB Treasury: {KB_TREASURY}")
    print(f"Amount: {AMOUNT_ATOMIC} atomic USDC ({AMOUNT_ATOMIC/1e6} USDC)")
    
    # Check balance
    usdc = w3.eth.contract(address=w3.to_checksum_address(USDC_BASE), abi=USDC_ABI)
    balance = usdc.functions.balanceOf(acct.address).call()
    print(f"Test-buyer USDC balance: {balance/1e6} USDC")
    
    if balance < AMOUNT_ATOMIC:
        print("ERROR: Insufficient USDC balance")
        return
    
    # Check ETH balance
    eth_balance = w3.eth.get_balance(acct.address)
    print(f"Test-buyer ETH balance: {eth_balance/1e18} ETH ({eth_balance} wei)")
    
    # Build transaction with optimized gas
    nonce = w3.eth.get_transaction_count(acct.address)
    
    # Estimate gas first
    try:
        estimated_gas = usdc.functions.transfer(
            w3.to_checksum_address(KB_TREASURY),
            AMOUNT_ATOMIC
        ).estimate_gas({'from': acct.address})
        print(f"Estimated gas: {estimated_gas}")
        gas_limit = estimated_gas + 10000  # buffer
    except Exception as e:
        print(f"Gas estimation failed: {e}, using default 60000")
        gas_limit = 60000
    
    print(f"Gas limit: {gas_limit}")
    
    # Current base fee (use 1 gwei max priority, base fee ~0)
    # Base uses EIP-1559
    latest_block = w3.eth.get_block('latest')
    base_fee = latest_block.get('baseFeePerGas', w3.to_wei('1', 'gwei'))
    max_priority = w3.to_wei('1', 'gwei')
    max_fee = base_fee + max_priority
    
    print(f"Base fee: {base_fee/1e9} gwei, Max fee: {max_fee/1e9} gwei")
    print(f"Max tx cost: {gas_limit * max_fee / 1e18} ETH")
    
    tx = usdc.functions.transfer(
        w3.to_checksum_address(KB_TREASURY),
        AMOUNT_ATOMIC
    ).build_transaction({
        'from': acct.address,
        'nonce': nonce,
        'gas': gas_limit,
        'maxFeePerGas': max_fee,
        'maxPriorityFeePerGas': max_priority,
        'chainId': 8453
    })
    
    # Sign and send
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    tx_hash_hex = tx_hash.hex()
    print(f"Transaction sent: {tx_hash_hex}")
    
    # Wait for receipt
    print("Waiting for confirmation...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    print(f"Confirmed! Block: {receipt.blockNumber}, Gas used: {receipt.gasUsed}, Status: {receipt.status}")
    
    return tx_hash_hex

if __name__ == "__main__":
    main()
