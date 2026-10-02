export function HowItWorks() {
  const steps = [
    {
      num: "01",
      title: "Stake 0.1 $zkLTC",
      desc: "Connect wallet, claim testnet tokens from faucet, stake exactly 0.1 $zkLTC to join the pool.",
      icon: "💰",
    },
    {
      num: "02",
      title: "Pool runs 21 hours",
      desc: "Pool stays open for 21 hours collecting participants. Minimum 21 users required for a draw.",
      icon: "⏱️",
    },
    {
      num: "03",
      title: "Draw phase (21 min)",
      desc: "After 21 hours, pool closes for 21 minutes. A random winner is selected on-chain.",
      icon: "🎲",
    },
    {
      num: "04",
      title: "Rewards distributed",
      desc: "Winner gets 70% jackpot. All stakers share 20%. 10% goes to protocol. Fair for everyone.",
      icon: "🏆",
    },
  ];

  return (
    <div id="how" className="space-y-4">
      <h2 className="text-xl font-bold text-white">How It Works</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {steps.map((s) => (
          <div key={s.num} className="card-glow p-5 space-y-3">
            <div className="flex items-center gap-3">
              <span className="text-2xl">{s.icon}</span>
              <span className="font-mono text-xs font-bold" style={{ color: "rgba(34,197,94,0.6)" }}>
                {s.num}
              </span>
            </div>
            <h4 className="font-bold text-white">{s.title}</h4>
            <p className="text-gray-400 text-sm leading-relaxed">{s.desc}</p>
          </div>
        ))}
      </div>

      {/* Rule: pool continues if <21 */}
      <div className="rounded-xl p-4 text-sm"
        style={{ background: "rgba(245,158,11,0.06)", border: "1px solid rgba(245,158,11,0.15)" }}>
        <p className="font-medium text-amber-400 mb-1">⚠️ Important: Minimum User Rule</p>
        <p className="text-gray-400">
          If less than 21 users are in the pool when the draw is triggered, no draw takes place.
          The pool reopens immediately and all current participants remain — nothing is lost.
          The 21-hour timer restarts for the next cycle.
        </p>
      </div>
    </div>
  );
}
