"use client";

import { ConnectButton } from "@rainbow-me/rainbowkit";
import { Zap, Wallet } from "lucide-react";

export function Navbar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4"
      style={{ background: "rgba(0,0,0,0.85)", backdropFilter: "blur(12px)", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>

      <div className="flex items-center gap-3">
        <div style={{
          width: 38, height: 38, borderRadius: 10,
          background: "linear-gradient(135deg, #0f2d1a 0%, #0a1f10 100%)",
          border: "1.5px solid rgba(34,197,94,0.5)",
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 0 12px rgba(34,197,94,0.2)",
        }}>
          <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
            <text x="50%" y="54%" dominantBaseline="middle" textAnchor="middle"
              fontFamily="system-ui, sans-serif" fontWeight="800" fontSize="13"
              fill="#22c55e" letterSpacing="-0.5">LC</text>
          </svg>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-bold text-white text-lg tracking-tight">LitCount</span>
          <span className="text-xs px-2 py-0.5 rounded-full font-medium"
            style={{ background: "rgba(34,197,94,0.1)", color: "#22c55e", border: "1px solid rgba(34,197,94,0.2)" }}>
            DeFi
          </span>
        </div>
      </div>

      <div className="hidden md:flex items-center gap-7 text-sm font-medium">
        {[
          { label: "Pool", href: "#pool" },
          { label: "How It Works", href: "#how" },
          { label: "History", href: "#history" },
        ].map((item) => (
          <a key={item.label} href={item.href}
            className="transition-colors hover:text-white"
            style={{ color: "#60a5fa" }}>
            {item.label}
          </a>
        ))}
        <a href="https://github.com/33ai-wq/litcount/blob/main/WHITEPAPER.md"
          target="_blank"
          className="flex items-center gap-1 transition-colors hover:text-white"
          style={{ color: "#60a5fa" }}>
          <Zap size={13} /> Whitepaper
        </a>
      </div>

      {/* Custom wallet button — always English */}
      <ConnectButton.Custom>
        {({ account, chain, openAccountModal, openChainModal, openConnectModal, mounted }) => {
          const connected = mounted && account && chain;
          return (
            <div>
              {!connected ? (
                <button onClick={openConnectModal}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl font-bold text-sm transition-opacity hover:opacity-90"
                  style={{ background: "linear-gradient(135deg, #22c55e, #16a34a)", color: "#000" }}>
                  <Wallet size={16} />
                  Connect Wallet
                </button>
              ) : chain.unsupported ? (
                <button onClick={openChainModal}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl font-bold text-sm"
                  style={{ background: "#ef4444", color: "#fff" }}>
                  Wrong Network
                </button>
              ) : (
                <button onClick={openAccountModal}
                  className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium"
                  style={{ background: "rgba(34,197,94,0.1)", border: "1px solid rgba(34,197,94,0.3)", color: "#22c55e" }}>
                  <Wallet size={14} />
                  {account.displayName}
                </button>
              )}
            </div>
          );
        }}
      </ConnectButton.Custom>
    </nav>
  );
}
