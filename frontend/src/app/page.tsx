import { Navbar }      from "@/components/Navbar";
import { PoolStatus }  from "@/components/PoolStatus";
import { JoinCard }    from "@/components/JoinCard";
import { HowItWorks }  from "@/components/HowItWorks";
import { PoolHistory } from "@/components/PoolHistory";

export default function Home() {
  return (
    <div className="min-h-screen bg-black">
      <Navbar />

      {/* Hero */}
      <section className="pt-28 pb-16 px-6 text-center relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none" style={{
          background: "radial-gradient(ellipse 800px 400px at 50% 0%, rgba(34,197,94,0.06) 0%, transparent 70%)",
        }} />

        {/* Hero Logo */}
        <div className="relative mx-auto mb-6 flex items-center justify-center"
          style={{ width: 80, height: 80, borderRadius: 24,
            background: "linear-gradient(135deg, #0f2d1a 0%, #0a1a0c 100%)",
            border: "1.5px solid rgba(34,197,94,0.4)",
            boxShadow: "0 0 40px rgba(34,197,94,0.15)" }}>
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <text x="50%" y="54%" dominantBaseline="middle" textAnchor="middle"
              fontFamily="system-ui, sans-serif" fontWeight="900" fontSize="22"
              fill="#22c55e" letterSpacing="-1">LC</text>
          </svg>
        </div>

        <h1 className="relative text-5xl font-black text-white tracking-tight mb-4">
          Lit<span className="text-gradient">Count</span>
        </h1>
        <p className="relative text-xl text-gray-300 mb-2">Just stake it and get reward.</p>
        <p className="relative text-sm text-gray-500 max-w-md mx-auto mb-8">
          Pool staking DeFi on LitVM Testnet. Stake 0.1 $zkLTC, win the jackpot or earn base rewards every 21 hours.
        </p>

        <div className="relative flex flex-wrap items-center justify-center gap-2 text-xs">
          {["DeFi", "LitVM Testnet", "$zkLTC", "Save & Win", "Becoming a Truly Rich Person"].map((b) => (
            <span key={b} className="px-3 py-1.5 rounded-full" style={{
              background: "rgba(34,197,94,0.06)",
              border: "1px solid rgba(34,197,94,0.15)",
              color: "#86efac",
            }}>{b}</span>
          ))}
        </div>
      </section>

      {/* Main content */}
      <main className="max-w-6xl mx-auto px-4 md:px-6 pb-24 space-y-12" id="pool">
        {/* Pool section */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <PoolStatus />
          <JoinCard />
        </div>

        {/* How it works */}
        <HowItWorks />

        {/* History */}
        <PoolHistory />

        {/* About */}
        <div className="card-glow p-8 text-center space-y-3">
          <p className="text-2xl">🌟</p>
          <h3 className="font-bold text-white text-xl">Becoming a Truly Rich Person</h3>
          <p className="text-gray-400 max-w-lg mx-auto text-sm leading-relaxed">
            LitCount is more than a DeFi pool — it&apos;s a mindset. Save consistently, take calculated risks,
            and let the protocol work for you. Every round is a step toward financial abundance.
          </p>
          <div className="flex flex-wrap justify-center gap-4 pt-2 text-sm">
            <a href="https://github.com/33ai-wq/litcount/blob/main/WHITEPAPER.md"
              target="_blank"
              className="px-4 py-2 rounded-xl font-medium transition-opacity hover:opacity-80"
              style={{ background: "rgba(34,197,94,0.1)", color: "#22c55e", border: "1px solid rgba(34,197,94,0.2)" }}>
              Read Whitepaper
            </a>
            <a href="https://github.com/33ai-wq/litcount" target="_blank"
              className="px-4 py-2 rounded-xl font-medium text-gray-400 hover:text-white transition-colors"
              style={{ border: "1px solid rgba(255,255,255,0.1)" }}>
              GitHub
            </a>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t text-center py-8 space-y-1"
        style={{ borderColor: "rgba(255,255,255,0.06)" }}>
        <p className="text-gray-500 text-xs">LitCount © 2026 · Built on LitVM Testnet · DeFi Category</p>
        <p className="text-gray-600 text-xs">
          Smart contract: Foundry · Frontend: Next.js · Deploy: Vercel
        </p>
      </footer>
    </div>
  );
}
