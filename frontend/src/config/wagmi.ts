import { getDefaultConfig } from "@rainbow-me/rainbowkit";
import { LITVM_TESTNET } from "@/lib/config";

// ── Contract addresses ──
export const CONTRACT_ADDRESSES = {
  zkLTC: process.env.NEXT_PUBLIC_ZKLTC_ADDRESS as `0x${string}`,
  pool:  process.env.NEXT_PUBLIC_POOL_ADDRESS  as `0x${string}`,
};

export const wagmiConfig = getDefaultConfig({
  appName: "LitCount",
  projectId: process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID || "YOUR_PROJECT_ID",
  chains: [LITVM_TESTNET],
  ssr: true,
});
