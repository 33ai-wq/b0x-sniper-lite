/**
 * src/handlers/wallet-profile.js - Migrated from CF Worker
 * Uses web3.js for on-chain queries
 */
import { Web3 } from "web3";
import { CFG } from "../config.js";

const w3 = new Web3(CFG.rpcUrl);

export async function walletProfile(params) {
  const address = params.address;
  if (!address || !/^0x[a-fA-F0-9]{40}$/.test(address)) {
    return { error: "missing_or_invalid_address" };
  }

  try {
    const [txCount, balanceWei] = await Promise.all([
      w3.eth.getTransactionCount(address),
      w3.eth.getBalance(address),
    ]);

    return {
      address,
      tx_count: Number(txCount),
      eth_balance_wei: balanceWei.toString(),
      eth_balance: Number(w3.utils.fromWei(balanceWei, "ether")).toFixed(6),
      timestamp: new Date().toISOString(),
      chain: "base",
    };
  } catch (e) {
    return { error: e.message, address, chain: "base" };
  }
}
