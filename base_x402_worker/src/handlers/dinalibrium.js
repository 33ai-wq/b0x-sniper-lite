/**
 * src/handlers/dinalibrium.js — ETH/stablecoin equilibrium ratio
 */
import { Web3 } from "web3";
import { CFG } from "../config.js";

const w3 = new Web3("https://eth.llamarpc.com");

const STABLES = {
  USDC_ETH: "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
  USDT_ETH: "0xdAC17F958D2ee523a2206206994597C13D831ec7",
  DAI_ETH:  "0x6B175474E89094C44Da98b954EedeAC495271d0F",
};
const WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2";

const ERC20_ABI = [{
  constant: true, inputs: [{ name: "_owner", type: "address" }],
  name: "balanceOf", outputs: [{ name: "balance", type: "uint256" }],
  type: "function",
}];

export async function dinalibrium() {
  try {
    const addresses = Object.values(STABLES).map(a => w3.utils.toChecksumAddress(a));
    const whales = "0xBA12222222228d8Ba445958a75a0704d566BF2C8";
    const whaleC = w3.utils.toChecksumAddress(whales);
    const balances = await Promise.all(addresses.map(a => {
      const c = new w3.eth.Contract(ERC20_ABI, a);
      return c.methods.balanceOf(whaleC).call();
    }));
    const totalStable = balances.reduce((s, b) => s + Number(b), 0) / 1e6;
    return {
      whale_address: whales,
      stable_total_usd: Math.round(totalStable),
      timestamp: new Date().toISOString(),
    };
  } catch (e) {
    return { error: e.message, stable_total_usd: 0 };
  }
}
