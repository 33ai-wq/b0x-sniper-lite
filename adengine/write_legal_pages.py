#!/usr/bin/env python3
"""Write real content into the legal pages (+ a new About page) and link About everywhere.

Why: all three legal pages were refactor placeholders ("Placeholder — replace with the real
copy..."). Google AdSense reviews a site for exactly this kind of unfinished page, so before
asking for approval they have to be real, accurate and consistent with the new nav labels.

Idempotent: safe to run twice (it replaces the .legal-body content wholesale).
"""
import re, shutil, datetime, pathlib

ROOT = pathlib.Path("/var/www/xhagents-www")
STAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
CONTACT = "partner@xhagents.xyz"

NAV_FIX = [("Core Capabilities", "Capabilities"), ("Live Metrics", "Live status"),
           ("Exhibition Hall", "Products"), ("Community", "Partner")]

FOOTER_ADD = ('<a href="/about.html" data-astro-cid-sz7xmlte>About</a> ')

PRIVACY = """
<p>
  This policy explains what XH Agents (the operator of <strong>xhagents.xyz</strong>) does with data when
  you use this website, its paid endpoints and its advertising surfaces. Last updated: 23 September 2026.
</p>

<h3>What we do not collect</h3>
<p>
  There are no user accounts, no sign-up forms and no advertising or analytics trackers of our own. We do
  not ask for, and will never ask for, a private key, seed phrase or exchange password. Nobody should ever
  request those from you on our behalf.
</p>

<h3>What we do process</h3>
<p>
  <strong>On-chain data.</strong> Payments are settled in USDC on Base (and Solana) and verified by reading
  the public blockchain: wallet address, amount and transaction hash. That data is public by nature of the
  networks, not something we collect privately.
</p>
<p>
  <strong>Order and enquiry forms.</strong> The advertising order form sends us your email address, the
  wallet address you pay from and your ad copy, so the placement can be produced and matched to your
  payment. The partner form opens your own mail client and sends the message to {contact}; we keep it only
  to answer you.
</p>
<p>
  <strong>Service data.</strong> The paid AI Trading Assistant stores a message credit counter keyed to the
  wallet address you connect, plus the questions and answers needed to keep the conversation coherent. Web
  server logs (IP address, user agent, timestamp) are kept briefly for security, abuse prevention and rate
  limiting.
</p>

<h3>Cookies and third-party advertising</h3>
<p>
  This site carries <strong>Google AdSense</strong>. Google and its partners may use cookies (including the
  DoubleClick DART cookie) to serve ads based on your visits to this and other websites, and to measure ad
  performance. Where required (e.g. the EEA, the UK, Switzerland), a Google-certified consent management
  platform asks for your choice before personalised advertising cookies are used.
</p>
<ul>
  <li>Opt out of personalised Google advertising: <a href="https://adssettings.google.com" rel="noopener">Google Ads Settings</a>.</li>
  <li>Opt out of participating third-party vendors: <a href="https://www.aboutads.info" rel="noopener">aboutads.info</a>.</li>
  <li>Google's own practices: <a href="https://policies.google.com/technologies/partner-sites" rel="noopener">How Google uses information from sites that use its services</a>.</li>
</ul>
<p>
  Placements we sell directly (the section labelled <em>Sponsored</em>) are served from our own ad engine and
  are always labelled as advertising; they are separate from the AdSense units Google may display.
</p>

<h3>Your choices</h3>
<p>
  You can block or delete cookies in your browser without losing access to anything on this site. To ask
  what a form submission contains, or to have it removed, write to {contact}.
</p>

<h3>Retention, security and children</h3>
<p>
  Form and order data is kept as long as needed to serve the order, the enquiry or the accounting, then
  deleted. Payment verification data is derived from the public chain and cannot be deleted. Access to our
  systems is restricted to the operator and to the agents that run under it. This site is not directed at
  children under 13 and we do not knowingly collect their data.
</p>

<h3>Changes</h3>
<p>
  Material changes to this policy will be published on this page with a new date. Questions about privacy:
  {contact}.
</p>
""".replace("{contact}", CONTACT)

TERMS = """
<p>
  By using <strong>xhagents.xyz</strong> and the prototypes it links to, you agree to these terms. Last
  updated: 23 September 2026.
</p>

<h3>What this site is</h3>
<p>
  XH Agents is an autonomous software operation: a small fleet of AI agents that build, run and sell
  software services, with payments settled on public blockchains. There is <strong>no token, no
  presale, no investment offering and no claim on any asset or revenue</strong> — nothing on this site is
  an offer of securities, and we do not publish asset or portfolio values.
</p>

<h3>Paid services (x402)</h3>
<p>
  Some services are paid per use in USDC on Base or Solana, for example the AI Trading Assistant
  (0.10 USDC per message) and the knowledge-base endpoint (0.03 USDC per query). Prices are shown before
  you pay. A payment your wallet has already broadcast cannot be reversed by us — blockchain transactions
  are final. If a message cannot be answered because our side fails, no credit is consumed.
</p>

<h3>Advertising on this site</h3>
<p>
  We sell placements directly: 728×90 at $40/month, 300×250 at $35/month and 480×320 at $60/month, settled
  in USDC. Every submission is reviewed before it goes live; we may decline or remove any placement that is
  unlawful, misleading, or that we judge harmful to the site or its audience. A placement runs for 30 days
  from activation and is not refundable once activated, because the payment is already final on-chain.
</p>
<p>
  This site also carries third-party advertising served by Google AdSense. Those ads are selected by Google,
  not by us, and are covered by Google's own policies.
</p>

<h3>Acceptable use</h3>
<p>
  Do not attack, overload, scrape abusively or attempt to bypass payment on our endpoints; do not use them
  for anything unlawful. We may rate-limit or block traffic that harms the service.
</p>

<h3>No warranty, limitation of liability</h3>
<p>
  The services are provided "as is", without warranties of any kind, including accuracy of third-party
  market data or uninterrupted availability. To the maximum extent permitted by law, we are not liable for
  indirect or consequential losses, or for decisions you take based on anything you read here.
</p>

<h3>Changes, jurisdiction, contact</h3>
<p>
  We may update these terms; the current version always lives on this page. They are governed by the laws
  applicable where the operator resides, without overriding mandatory consumer protections you may have.
  Contact: {contact}.
</p>
""".replace("{contact}", CONTACT)

DISCLAIMER = """
<p>
  This page states plainly what the things on this site are and what they are not. Last updated:
  23 September 2026.
</p>

<h3>Not financial or investment advice</h3>
<p>
  Nothing here is financial, investment, legal or tax advice, and nothing here is a recommendation to buy or
  sell any asset. XH Agents does not manage funds, does not accept deposits and does not promise a return of
  any kind.
</p>

<h3>Autonomous agents make mistakes</h3>
<p>
  The AI assistants on this site are software. They can be wrong, incomplete or out of date, they can lose
  context, and they can be confidently mistaken. Always verify anything important against a primary source
  before acting on it.
</p>

<h3>Market data is third-party and may be delayed</h3>
<p>
  Prices and market figures are fetched from public third-party APIs while you are reading them. They may be
  delayed, throttled or wrong, and they are not suitable for trading, accounting or valuation purposes.
</p>

<h3>Blockchain payments are irreversible</h3>
<p>
  Payments settle in USDC on public networks. Once a transaction is confirmed it cannot be recalled, and
  network, bridge or contract-level risks are borne by the sender. We never ask for a private key or seed
  phrase — anybody who does is not us.
</p>

<h3>No token, no investment product</h3>
<p>
  XH Agents has no token and no roadmap of one. Any page, post or message implying otherwise — including
  anything claiming to raise funds for XH Agents — is unauthorised and should be reported to {contact}.
</p>

<h3>Availability and external links</h3>
<p>
  We aim to keep the site and its endpoints running, but we do not guarantee uptime. Pages we link to
  (including prototypes on subdomains and advertising), are operated separately unless stated otherwise,
  and their content is their own.
</p>
""".replace("{contact}", CONTACT)

ABOUT = """
<p>
  XH Agents is a small autonomous software company: seven AI agents, one server, and a set of products that
  earn in USDC. This page explains what we actually build and how we make money, so you can judge the site
  for yourself.
</p>

<h3>The agents</h3>
<ul>
  <li><strong>Hermes</strong> — orchestrator: plans the work, writes the code, deploys and verifies it.</li>
  <li><strong>Scout</strong> — market intelligence: feeds the live metrics on the home page.</li>
  <li><strong>Trader</strong> — on-chain execution, gated by risk rules.</li>
  <li><strong>Treasury</strong> — wallets and inbound payments.</li>
  <li><strong>Scribe</strong> — writing and publishing.</li>
  <li><strong>Sentinel</strong> — the risk gate: every outbound payment needs its approval.</li>
  <li><strong>Keeper</strong> — infrastructure: services, deployment, backups.</li>
</ul>

<h3>What we run today</h3>
<ul>
  <li><strong>Ataraxia</strong> — a quiet room on Base: free breathing exercises, plus four long animations
    unlocked for 0.10 USDC each. No levels, no streaks, no token.</li>
  <li><strong>AI Trading Assistant</strong> — pay per message (0.10 USDC on Base) for a market-aware answer,
    with the price of the assets you ask about fetched live at the moment you ask.</li>
  <li><strong>Knowledge-base endpoint</strong> — 0.03 USDC per query over our curated operational notes, for
    other agents and developers.</li>
  <li><strong>Sponsorship</strong> — labelled placements in the Sponsored section of the home page, and in
    the AI Trading Assistant, settled in USDC.</li>
</ul>

<h3>How we earn, and how we do not</h3>
<p>
  Revenue comes from the paid services above and from advertising. There is no token and there never will
  be one, we do not run a fund, and we deliberately never publish asset or portfolio figures — including
  our own. Everything is priced in the open before you pay.
</p>

<h3>How the engineering works</h3>
<p>
  Everything is self-hosted and small on purpose: one VPS, open code where it can be open, payments verified
  by reading the blockchain directly rather than through a third-party payment processor, and every money
  path covered by automated tests. When something breaks we write down what happened so the next agent does
  not repeat it.
</p>

<h3>Work with us</h3>
<p>
  Advertise, partner, or use a product — write to {contact}. We answer questions about how the payment and
  verification machinery works, and we publish what we are working on as it goes live.
</p>
""".replace("{contact}", CONTACT)

PAGES = {"privacy.html": PRIVACY, "terms.html": TERMS, "disclaimer.html": DISCLAIMER, "about.html": ABOUT}
TITLES = {"privacy.html": "Privacy Policy — XH Agents", "terms.html": "Terms of Service — XH Agents",
          "disclaimer.html": "Disclaimer — XH Agents", "about.html": "About — XH Agents"}
DESCRIPTIONS = {
    "privacy.html": "How XH Agents handles data: on-chain payments, order forms, server logs, and the cookies used by Google AdSense — plus how to opt out.",
    "terms.html": "Terms of service for xhagents.xyz: x402 payments in USDC, advertising placements, acceptable use, liability and contact.",
    "disclaimer.html": "What XH Agents is not: no financial advice, no token, no fund; autonomous agents make mistakes and on-chain payments are irreversible.",
    "about.html": "What XH Agents is: seven autonomous agents, the products they run, how they earn in USDC — and what they deliberately never do.",
}

# privacy.html is the structural template (header/footer/legal styles are identical across the legal pages)
template_path = ROOT / "privacy.html"
template = template_path.read_text(encoding="utf-8")

for name, body in PAGES.items():
    target = ROOT / name
    html = template if not target.exists() else target.read_text(encoding="utf-8")

    # 1) real content replaces the placeholder body wholesale
    html = re.sub(r'(<div class="legal-body"[^>]*>).*?(</div>)', lambda m: m.group(1) + body + m.group(2),
                  html, count=1, flags=re.S)

    # 2) page-specific title / description / heading
    html = re.sub(r"<title>.*?</title>", f"<title>{TITLES[name]}</title>", html, count=1, flags=re.S)
    html = re.sub(r'<meta name="description" content="[^"]*"',
                  f'<meta name="description" content="{DESCRIPTIONS[name]}"', html, count=1)
    h2 = {"privacy.html": "Privacy Policy", "terms.html": "Terms of Service",
          "disclaimer.html": "Disclaimer", "about.html": "About XH Agents"}[name]
    html = re.sub(r"<h2[^>]*>.*?</h2>", f'<h2 data-astro-cid-jue3ldzs>{h2}</h2>', html, count=1, flags=re.S)

    # 3) nav labels consistent with the live home page
    def fix_nav(m):
        nav = m.group(0)
        for old, new in NAV_FIX:
            nav = nav.replace(f">{old}<", f">{new}<")
        return nav
    html = re.sub(r'<nav class="nav mono"[^>]*>.*?</nav>', fix_nav, html, count=1, flags=re.S)

    # 4) About link in the footer of every page
    html = re.sub(r'(<nav class="footer-links"[^>]*>)', r'\1' + FOOTER_ADD, html, count=1)

    if target.exists():
        shutil.copyfile(target, str(target) + f".bak.{STAMP}_legal")
    target.write_text(html, encoding="utf-8")
    print(f"  ✓ {name}: {len(body)} chars of real content, title/description/nav/footer updated")

# home page + ad-order + trading get the About link too (navigation matters for a review)
for extra in ["index.html", "ad-order.html", "trading/index.html"]:
    p = ROOT / extra
    if not p.exists():
        continue
    s = p.read_text(encoding="utf-8")
    if 'href="/about.html"' in s:
        print(f"  = {extra}: About link already present"); continue
    s2 = re.sub(r'(<nav class="footer-links"[^>]*>)', r'\1' + FOOTER_ADD, s, count=1)
    if s2 == s:  # some pages use a different footer wrapper
        s2 = s.replace('<a href="/privacy.html"', '<a href="/about.html">About</a> <a href="/privacy.html"', 1)
    if s2 != s:
        shutil.copyfile(p, str(p) + f".bak.{STAMP}_about")
        p.write_text(s2, encoding="utf-8")
        print(f"  ✓ {extra}: About link added to the footer")
    else:
        print(f"  ! {extra}: footer not matched — About link not added")
