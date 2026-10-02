// Chain profiles for supported networks
// Source: adapted from solotop999/opensea-nft-public-mint

export interface ChainProfile {
  key: string;
  name: string;
  chainId: number;
  nativeSymbol: string;
  rpcDefault: string;
  explorer: string;
  explorerTx: (txHash: string) => string;
  seaDropAddress: string;
}

export const CHAINS: ChainProfile[] = [
  {
    key: "ethereum",
    name: "Ethereum",
    chainId: 1,
    nativeSymbol: "ETH",
    rpcDefault: "https://eth.llamarpc.com",
    explorer: "https://etherscan.io",
    explorerTx: (txHash: string) => `https://etherscan.io/tx/${txHash}`,
    seaDropAddress: "0x00005EA00Ac477B1030CE78506496e8C2dE24bf5",
  },
  {
    key: "base",
    name: "Base",
    chainId: 8453,
    nativeSymbol: "ETH",
    rpcDefault: "https://mainnet.base.org",
    explorer: "https://basescan.org",
    explorerTx: (txHash: string) => `https://basescan.org/tx/${txHash}`,
    seaDropAddress: "0x00005EA00Ac477B1030CE78506496e8C2dE24bf5",
  },
  {
    key: "robinhood",
    name: "Robinhood Chain",
    chainId: 4663,
    nativeSymbol: "RH",
    rpcDefault: "https://rpc.mainnet.chain.robinhood.com",
    explorer: "https://robinhoodchain.blockscout.com",
    explorerTx: (txHash: string) => `https://robinhoodchain.blockscout.com/tx/${txHash}`,
    seaDropAddress: "0x00005EA00Ac477B1030CE78506496e8C2dE24bf5", // Verify on RH Chain
  },
];

export function resolveChain(key: string): ChainProfile | undefined {
  return CHAINS.find((c) => c.key === key.toLowerCase());
}

export function resolveChainById(chainId: number): ChainProfile | undefined {
  return CHAINS.find((c) => c.chainId === chainId);
}

export function getDefaultChain(): ChainProfile {
  const envChain = (process.env.CHAIN || "robinhood").toLowerCase();
  return resolveChain(envChain) || CHAINS[2]; // Default to Robinhood Chain
}