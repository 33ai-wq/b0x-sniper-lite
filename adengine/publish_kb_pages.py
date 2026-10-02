#!/usr/bin/env python3
"""Publish a sanitised, human-readable Knowledge Base at /kb/ on xhagents.xyz.

Source: prpo_ai/kb/kb_seed.json (the same 15 entries served programmatically by the paid
/api/kb/ask endpoint). The raw entries are internal post-mortems — they contain wallet
addresses, server paths, project IDs and unreleased strategy detail — so each one is
rewritten here as a public engineering note: the symptom, what was actually wrong, the fix,
and the transferable lesson. Nothing private is copied verbatim.

Generates: /var/www/xhagents-www/kb/index.html, one page per entry, updates sitemap.xml, and
links "Knowledge Base" from the footers of the main pages. Idempotent.
"""
import json, pathlib, re, shutil, datetime, html

DOCROOT = pathlib.Path("/var/www/xhagents-www")
KB_DIR = DOCROOT / "kb"
STAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
SITE = "https://xhagents.xyz"

CATEGORIES = {
    "devops-vps": "Infrastructure & deployment",
    "ai-infra": "AI infrastructure",
    "payments-x402": "Payments & x402",
    "trading-bots": "Trading automation",
    "content-automation": "Content & monetisation",
}

# slug -> (title, category, date, tags, summary, symptom, cause, fix, lesson)
NOTES = {
"tailwind-v4-vite-dark-theme": (
 "A dark theme that never rendered: the missing Vite plugin",
 "devops-vps", "2026-08-31", ["tailwind", "vite", "css", "theming"],
 "A production page showed a white background although the stylesheet defined a near-black background colour: the CSS framework was never compiled because its build plugin was absent from the bundler config.",
 "The page rendered with the browser's white default. The stylesheet file existed, the theme variables were defined in the source, and no build error appeared in the terminal.",
 "The CSS framework was installed as a dependency, but the bundler config never registered its plugin. Declarations like the custom theme block and the utility classes were therefore treated as unknown at-rules and dropped silently — no error, no output, no styling.",
 "Register the framework's plugin in the bundler config (for example add it to the <code>plugins</code> array next to the framework's own plugin), reinstall the matching version, and add a small inline critical stylesheet in the HTML head so the correct background and colour scheme paint before any CSS file loads.",
 "A stylesheet that exists is not a stylesheet that compiled. When a theme silently disappears, check the build step before the CSS: 'no error' from the bundler means nothing if the plugin was never registered.",
),
"wallet-modal-eight-options": (
 "Wallet connect with two buttons: rebuilding it as a real modal",
 "ai-infra", "2026-08-31", ["web3", "walletconnect", "ux"],
 "The first version of our wallet connection offered two bare buttons and a text state machine. Replacing it with a modal that detects installed wallets turned a confusing step into the shortest path through the app.",
 "Connecting a wallet meant reading a status string ('connecting…') and choosing between two hard-coded wallets. Users without either of them were stuck, and the interaction looked nothing like the rest of the interface.",
 "The flow had been written as a phase check with inline markup rather than as a component. There was no wallet discovery, no chain information, and no way to add a provider without editing the layout.",
 "A dedicated modal component: a blurred overlay, a grid of provider options that also lists wallets actually detected in the browser with a live indicator, a connected state showing the address and the active network, and payment actions per chain. Providers are registered through a wallet aggregator, so adding support for a new one is configuration rather than code.",
 "Wallet connection is the first interactive thing a visitor does; if it is a guess, nothing after it gets tried. Discovery beats enumeration — show what the visitor actually has installed.",
),
"scroll-and-overlay-lock": (
 "A page that would not scroll: overflow and an unpositioned overlay",
 "devops-vps", "2026-08-31", ["css", "layout", "nginx", "proxy"],
 "A single-page app was frozen — no scrolling, and a modal that covered the content without ever opening. The cause was two small CSS omissions plus three missing proxy rules.",
 "The wheel and touch gestures did nothing. The page appeared complete but immovable, and a dialog's backdrop sat over the content permanently.",
 "Three unrelated defects stacked: the root element had vertical overflow suppressed, the body still hid overflow instead of allowing it, and the overlay markup had no positioning rule at all — so instead of a modal layer that appears on demand, an unstyled block sat in the flow. Separately, the same page's API calls were failing because the web server had no route for them, so they fell through to an unrelated handler.",
 "Restore scrolling at the root and stop hiding overflow on the body, give the overlay fixed positioning with a backdrop and an opacity transition, and add explicit proxy locations for every API path the page calls rather than relying on a catch-all.",
 "A frozen page is rarely a JavaScript problem: check overflow on the root and body first, then positioning on overlays. And every new API path the front end calls should be an explicit route in the web server, not something you hope the catch-all handles.",
),
"iab-banner-responsive-house-ads": (
 "One banner slot, three IAB sizes",
 "devops-vps", "2026-08-31", ["css", "advertising", "responsive-design"],
 "Replacing a decorative hero animation with a house advertising strip that renders at three standard IAB sizes without shipping three images or three blocks of markup.",
 "The old hero blocked the fold with an animation that carried no information, while the advertising surfaces the business actually needed had nowhere to live.",
 "A single element was needed that could present a 320×50, a 480×60 and a 729×90 slot from one markup block, with a label so the placement is unmistakably advertising.",
 "One wrapper plus one slot, with media queries swapping the slot dimensions at 480px and 900px, a labelled 'Ad' marker positioned over the join, and two equal-width halves for the two placements so the layout cannot collapse. The hero padding was reduced from most of the viewport to a couple of rems.",
 "Ad slots should be labelled and sized, not improvised: standard IAB dimensions plus a visible label. Making them responsive with media queries keeps one code path and avoids the layout shift that swapping images would cause.",
),
"policy-never-show-asset-value": (
 "Enforcing a policy in code: removing an asset balance from a live page",
 "payments-x402", "2026-09-01", ["policy", "review", "static-site"],
 "A company rule — never display holdings or asset value on a public page — had been broken quietly by a treasury widget on an older deployment.",
 "An older project page displayed a treasury address plus a live balance fetched from a block explorer. Nobody had looked at that page in weeks; it contradicted the published policy the rest of the company follows.",
 "The widget had been added when the project still planned to display its holdings. When the policy changed, the page was simply forgotten, because the rule lived in documentation rather than in any check.",
 "The entire section was removed from the source together with the explorer request, committed with a message naming the policy, deployed, and verified in the live page — both that the section is gone and that no balance request is made any more.",
 "Policies that matter belong in code review and in checks, not in prose — the page that violates them is always one you have stopped looking at. When you find a violation, delete the request too: a section hidden by CSS still calls the network.",
),
"api-endpoints-hanging-content-length": (
 "Every API endpoint hung: a missing Content-Length",
 "ai-infra", "2026-09-17", ["http", "python", "debugging"],
 "A handful of endpoints behind a reverse proxy never returned — the client waited until it timed out. The handler was writing a correct response body and then leaving the connection open.",
 "Requests to the service's JSON endpoints hung indefinitely when made through the web server, while the same code worked when called directly on the loopback interface. It looked like a proxy problem; the proxy was innocent.",
 "The hand-rolled HTTP responder wrote a status line, headers and a body, but never stated the body length and never closed the connection — valid in HTTP/1.0 style, ambiguous for HTTP/1.1 clients and intermediaries, which then wait for more data that will never come.",
 "The response helper now always sends a <code>Content-Length</code> header and <code>Connection: close</code>, and the service was restarted under its own supervisor. Every endpoint answers immediately afterwards.",
 "When a response works on loopback but hangs behind a proxy, suspect framing before routing. In HTTP/1.1 an unframed response is not a finished response — say how long the body is, or how the connection ends.",
),
"nginx-docroot-vs-source": (
 "The site you are editing is not always the site you are serving",
 "devops-vps", "2026-09-16", ["nginx", "deployment", "build"],
 "A stylesheet change was deployed, built successfully, and had no effect on the live site: the build output and the directory the web server actually serves were two different places.",
 "The repository contained the framework source and a build script. After a clean build the deployed page looked unchanged.",
 "The web server's document root was a separate, older directory — the source tree and the served directory were different paths, and an older copy of the project existed under a similar name, which made the mismatch easy to miss. Configuration dumps and file timestamps were the only reliable evidence.",
 "Establish which directory the server really uses (<code>nginx -T</code> is authoritative, plus the file's modification time), then define one deployment step: build in the source tree, copy the build output into the served directory while preserving the paths it also hosts, and confirm with a request to the live origin.",
 "Always verify which file is being served — a configuration dump plus the served bytes, not the directory you assume. Naming a directory after the project and another after an older project is how an afternoon disappears.",
),
"form-wiring-and-favicon": (
 "A form that only reloaded the page",
 "devops-vps", "2026-09-17", ["frontend", "forms", "api"],
 "A public order form looked finished and did nothing: pressing submit reloaded the page instead of creating an order. The same page also had no favicon and no way to tell a failed submission from a successful one.",
 "Clicking the button produced a flash and an empty form. Nothing was recorded server-side, and there was no message of any kind.",
 "The form element had no submission behaviour and no API contract behind it — the markup had been written before the endpoint existed, so the default browser action took over. There was also no result surface, which meant that even a successful call would have been invisible.",
 "The form now posts to the documented endpoint with the exact field names the backend expects, and the page grew a result panel that shows the created order's identifier, the amount, the recipient address and the payment reference, plus a payment button when the endpoint returns one.",
 "A form is not done when it looks right; it is done when a submission produces an observable result. Always render the outcome — without a result panel, a working endpoint and a broken one look identical.",
),
"mcp-server-for-agents": (
 "Giving other agents an interface: wrapping a site's endpoints as MCP tools",
 "ai-infra", "2026-09-19", ["mcp", "ai-agents", "api"],
 "The endpoints a person uses through a browser were useless to another AI agent. Wrapping them as MCP tools turned the company's services into something agents can call directly.",
 "Automation against the site meant screen-scraping and hand-written HTTP calls, with the payment flow reimplemented each time.",
 "Each capability needed a typed tool with a description, plus a machine-readable view of the site's live state. Publishing that over a transport an agent framework already speaks removes the scraping layer entirely.",
 "A small server exposing eight tools — order creation, ad listing, the paid assistant, invoice retrieval, balance lookup, status, market data and a raw HTTP escape hatch — plus two resources for status and ads, run under a supervisor and proxied by the web server.",
 "One implementation detail worth knowing: the proxy must forward the host header the application expects, or the framework's own host validation rejects every request. When an embedded server sits behind a proxy, that header is part of the contract.",
),
"treasury-and-payment-verification": (
 "Verifying payments without trusting the client: what an ERC-20 transfer log actually contains",
 "payments-x402", "2026-09-24", ["payments", "evm", "verification", "debugging"],
 "Two implementations of 'did this customer pay?' were both wrong in the same way, and both failed silently — one detected nothing at all, the other credited unlimited purchases from a single payment.",
 "On one service, payments were never recognised on the EVM chain although the identical flow worked on Solana. On another, a single payment could be spent again and again.",
 "Two facts about token transfers: an ERC-20 <code>Transfer</code> event is emitted by the <em>token contract</em>, so filtering the event log by the recipient's address returns nothing, ever; and a payment is only a payment when it is bound to a payer, a recipient, an amount and a token — and is usable exactly once, which requires recording the transaction hash.",
 "One shared verification module now builds the log filter correctly (token contract as the address, the <code>Transfer</code> signature as the first topic, the recipient as the third — plus the payer when known), re-checks recipient, sender, token and amount locally on every returned log rather than trusting the node to have honoured the filter, and claims each transaction hash once in a durable store so a replay cannot double-credit.",
 "On-chain payment code fails closed and fails quietly. Write the matcher once, test it, and never hand-roll it per service: the same mistake was made twice by two different people on two different days.",
),
"x402-pay-per-message": (
 "Charging per message: x402 on top of a chat endpoint",
 "payments-x402", "2026-09-18", ["x402", "usdc", "api", "payments"],
 "A chat assistant that had been free since launch became a paid one, at a tenth of a dollar per message, payable in USDC directly from the user's wallet — with the endpoint still usable by other agents machine-to-machine.",
 "There was no billing concept at all: one endpoint, one model call, no notion of who had paid or how much.",
 "The service needed a price, a per-request invoice, a settlement check on the incoming request, and a durable per-wallet balance for the browser flow — without a payment processor, since the payments settle on a public chain.",
 "The API returns a payment challenge with a nonce, the recipient and the exact amount in atomic units when the caller asks for an invoice; the same endpoint accepts the settled payment receipt in a request header and verifies it against the invoice before serving the answer, spending the nonce. For browser users, a wallet top-up path credits messages and the counter is decremented per answer.",
 "Design the invoice to be single-use and bind it to the answer it pays for. Machine-to-machine usage and human usage pull in different directions — support both, but keep one verification path so the rules stay consistent.",
),
"onramp-rejected-pivot": (
 "A rejected payment integration, and the two paths that actually worked",
 "payments-x402", "2026-09-18", ["compliance", "payments", "strategy"],
 "A card-payment integration was refused by the provider on compliance grounds. Instead of waiting, the product moved to two payment paths that need no third-party approval.",
 "The card on-ramp was built end to end and returned a not-found error from the provider for weeks. The blocker was not technical: the application had been declined because the business — an advertising marketplace — did not fit the provider's requirements at that time.",
 "The dependency was a compliance decision outside our control, yet the integration had become the assumed revenue path. Every day spent debugging it was a day not spent on paths that only require a wallet.",
 "The unfinished integration was left in place but clearly marked inactive, and revenue moved to two self-hosted routes: pay-per-use over the x402 protocol, and direct stablecoin payments for advertising placements. Both verify settlement by reading the chain, so neither can be switched off by a third party. Reapplying becomes an option later, after formal business verification.",
 "Treat a payment provider's approval as a probability, not a plan. Build the route that needs no one's permission first, and keep the third-party one as an option you can switch on.",
),
"position-accounting-and-fee-economics": (
 "Three bugs worth finding before an automated trader handles real money",
 "trading-bots", "2026-09-03", ["trading", "risk-management", "testing"],
 "A review of an automated trading component found three defects that no unit test had caught, each of which would have cost real money in production: a safety check that checked nothing, position accounting that drifted, and a take-profit target smaller than the fee to exit.",
 "The component had tests, and they passed. The defects only surfaced when the code was read line by line against what it claimed to do in its own comments.",
 "The 'safety' check verified one liquidity figure and described itself as checking for honeypots and lock status. The position monitor ignored the return value of the close routine, so a failed sell marked the position closed while the token stayed in the wallet. And the profit target on a small position was worth less than the transaction fee needed to realise it, with no circuit breaker on repeated failures.",
 "Three replacements were designed rather than patched: real mint- and freeze-authority checks plus holder concentration, fee-aware profit and loss thresholds with position sizing and a circuit breaker, and an atomic open/close path that verifies every return value and persists state so a restart cannot lose track of an open position.",
 "For trading code the test that matters is not coverage but consistency between what a function claims and what it reads. Verify what you inspect, check that a sell actually sold, and never let a profit target sit below the cost of exiting.",
),
"service-worker-publisher-ads": (
 "Publisher ads on a static site: a service worker, a head tag and the install check",
 "content-automation", "2026-09-19", ["advertising", "service-worker", "static-site"],
 "Adding a third-party ad network to a static affiliate site: three components, no build step, and an installation check that has to pass exactly once.",
 "The network's dashboard reported the installation as incomplete although the code had been pasted in.",
 "The install consists of a service worker at the web root (the path and scope are mandatory, not a suggestion), a script tag in the head carrying the zone identifier, and the registration call in the page. A stale service worker from a previous zone makes the check fail even though the new tag is present.",
 "The current service worker file was copied to the root of the served directory, the head tag was placed immediately after the opening <code>&lt;head&gt;</code>, the registration call was added, and both the served file and its zone value were read back from the live origin — the dashboard's check then passed.",
 "Ad-network installs have a version: when a dashboard reissues credentials, the previously deployed file is a trap. Read back what the live origin actually serves — the zone identifier included — instead of trusting the file you just copied.",
),
"meme-radar-webhook-architecture": (
 "A token radar without a paid data feed",
 "trading-bots", "2026-09-03", ["webhooks", "data-feeds", "architecture"],
 "Building a real-time token radar while the paid data provider used as the fallback was out of budget: a free webhook feed for events, a free market API for scoring.",
 "The prototype assumed a commercial market-data API for everything, which made running costs scale with traffic before the product had any users.",
 "Two capabilities were being conflated: knowing that something happened (event notification, which a wallet/webhook provider will push to you cheaply) and knowing whether it is interesting (market data, which a free public API returns at a rate limit that is fine for a low-volume radar).",
 "The stack was split: a containerised service provisioned with the webhook feed for discovery and the free market API for scoring, with the commercial feed made optional behind a flag rather than required, so the system runs in a degraded-but-useful mode when the paid key is absent.",
 "Before paying for a data provider, check whether the problem is event delivery or market intelligence — they have very different price curves, and an architecture that treats them separately can start free and grow into the paid tier instead of depending on it.",
),
"catalog-and-internal-linking": (
 "Turning a product list into navigation: eleven entries, two links each",
 "devops-vps", "2026-09-01", ["information-architecture", "frontend", "seo"],
 "A catalogue modal had four entries with long descriptions and one stale link. It became eleven entries with two consistent links each: the product, and its source.",
 "The catalogue was a place where descriptions went to die. Visitors could not see the breadth of what exists, and one link pointed at a retired address.",
 "The list mixed two different things: what a project is (which the page around it already explained) and where to go next (which only the entry itself knows). Descriptions therefore duplicated the surrounding copy while the actionable part stayed hidden.",
 "Each entry became a compact card with a name and two pill links — a live product and its repository — in a scrollable grid capped at most of the viewport height, and the one stale address was corrected to the product's current home.",
 "Lists are navigation, not prose: name plus destinations. Keeping one pattern per entry means adding the twelfth item costs no thought, and a stale link is visible because it breaks the pattern rather than hiding inside a paragraph.",
),
}


def esc(s):
    return s  # entries contain deliberate inline HTML (<code>, <em>)


def page_shell(title, description, canonical, body, extra_head=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-7552930808768657"
     crossorigin="anonymous"></script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#050810">
<meta name="color-scheme" content="dark">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="XH Agents">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{canonical}">
<meta name="twitter:card" content="summary">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
{extra_head}<style>
:root{{--bg:#050810;--surface:#0b1220;--surface-raised:#101a2e;--border:#1b2436;--border-strong:#2a3654;--text:#e7ebf3;--text-muted:#8a94a6;--text-faint:#5a6478;--accent-live:#4fd1c5;--accent-pay:#7c8cff;--radius:6px;--max-width:1080px;--mono:"JetBrains Mono",ui-monospace,Menlo,monospace}}
*{{box-sizing:border-box}}html{{color-scheme:dark;overflow-y:auto;overflow-x:hidden}}
body{{margin:0;background:var(--bg);background-image:radial-gradient(circle at 15% 0%,rgba(79,209,197,.06),transparent 45%);color:var(--text);font-family:"Inter",-apple-system,"Segoe UI",sans-serif;line-height:1.6;-webkit-font-smoothing:antialiased}}
a{{color:inherit}}.container{{max-width:var(--max-width);margin:0 auto;padding:0 24px}}
.mono{{font-family:var(--mono)}}.eyebrow{{font-family:var(--mono);font-size:.8rem;color:var(--text-faint)}}
.header{{border-bottom:1px solid var(--border);background:#050810d9;backdrop-filter:blur(6px);position:sticky;top:0;z-index:10}}
.header-row{{display:flex;align-items:center;justify-content:space-between;padding:16px 24px;flex-wrap:wrap;gap:12px}}
.brand{{text-decoration:none;font-weight:600}}.brand-sub{{color:var(--text-faint);font-weight:400;font-size:.85rem;margin-left:6px}}
.nav{{display:flex;gap:20px;font-size:.85rem;flex-wrap:wrap}}.nav a{{text-decoration:none;color:var(--text-muted)}}.nav a:hover{{color:var(--accent-live)}}
main{{padding:48px 0 72px}}.wrap{{max-width:74ch}}
h1{{font-size:clamp(1.5rem,2.4vw,2.1rem);line-height:1.25;margin:.2rem 0 1rem}}
h2{{font-size:1.05rem;margin:2rem 0 .6rem;color:var(--text)}}
p,li{{color:var(--text-muted)}}p{{margin:0 0 1rem}}
.meta{{font-family:var(--mono);font-size:.8rem;color:var(--text-faint);margin-bottom:1.6rem}}
.meta a{{color:var(--accent-live);text-decoration:none}}
.tags{{display:flex;gap:8px;flex-wrap:wrap;margin:1.6rem 0 0;padding:0;list-style:none}}
.tags li{{font-family:var(--mono);font-size:.72rem;color:var(--text-faint);border:1px solid var(--border);border-radius:999px;padding:3px 10px}}
.card{{border:1px solid var(--border);background:var(--surface);border-radius:var(--radius);padding:18px 20px;margin:0 0 14px}}
.card a.title{{color:var(--text);text-decoration:none;font-weight:600}}.card a.title:hover{{color:var(--accent-live)}}
.card p{{margin:.5rem 0 0;font-size:.92rem}}
.cat{{font-family:var(--mono);font-size:.72rem;color:var(--accent-pay);text-transform:uppercase;letter-spacing:.04em}}
.more{{margin-top:2.4rem;border-top:1px solid var(--border);padding-top:1.2rem}}
code{{font-family:var(--mono);font-size:.85em;background:var(--surface-raised);border:1px solid var(--border);border-radius:4px;padding:1px 5px}}
.footer{{border-top:1px solid var(--border);padding:32px 0 48px;font-size:.8rem;color:var(--text-faint)}}
.footer-links{{display:flex;gap:16px;flex-wrap:wrap}}.footer-links a{{color:var(--text-muted);text-decoration:none}}
</style>
</head>
<body>
<header class="header">
  <div class="container header-row">
    <a href="/" class="brand mono">XHAGENTS&gt; <span class="brand-sub">Exhibition Hall Autonomous AI</span></a>
    <nav class="nav mono">
      <a href="/#features">Capabilities</a>
      <a href="/#status">Live status</a>
      <a href="/#exhibition">Products</a>
      <a href="/kb/">Notes</a>
    </nav>
  </div>
</header>
<main><div class="container wrap">
{body}
</div></main>
<footer class="footer mono"><div class="container">
  <p>XH Agents — field notes from running a small autonomous AI company.</p>
  <nav class="footer-links">
    <a href="/">Home</a>
    <a href="/kb/">Knowledge Base</a>
    <a href="/about.html">About</a>
    <a href="/privacy.html">Privacy Policy</a>
    <a href="/terms.html">Terms of Service</a>
    <a href="/disclaimer.html">Disclaimer</a>
  </nav>
</div></footer>
</body>
</html>
"""


def main():
    KB_DIR.mkdir(exist_ok=True)
    slugs = list(NOTES)
    written = []

    # index
    groups = {}
    for slug, (title, cat, date, tags, summary, *_rest) in NOTES.items():
        groups.setdefault(cat, []).append((slug, title, date, summary))
    body = [f"""<p class="eyebrow">Knowledge Base</p>
<h1>Field notes from running a small autonomous AI company</h1>
<p>Everything below is something we got wrong first, written up after it was fixed. They are the same {len(NOTES)}
entries our paid knowledge endpoint serves programmatically — published here in readable form, free, because a note
that nobody can find is not worth writing. No theory, no listicles: a symptom, what was actually wrong, what we
changed, and the lesson we keep.</p>"""]
    for cat in CATEGORIES:
        if cat not in groups:
            continue
        body.append(f'<h2>{CATEGORIES[cat]}</h2>')
        for slug, title, date, summary in sorted(groups[cat], key=lambda x: x[2], reverse=True):
            body.append(f"""<div class="card"><span class="cat">{cat}</span>
<a class="title" href="/kb/{slug}.html">{title}</a>
<p>{summary}</p>
<p class="meta" style="margin:.6rem 0 0">{date}</p></div>""")
    index_html = page_shell(
        "Knowledge Base — XH Agents",
        f"{len(NOTES)} field notes from building and operating a small autonomous AI company: deployment, payments, x402, agent infrastructure and trading automation.",
        f"{SITE}/kb/",
        "\n".join(body),
        extra_head='<script type="application/ld+json">{"@context":"https://schema.org","@type":"CollectionPage","name":"XH Agents Knowledge Base","url":"https://xhagents.xyz/kb/"}</script>\n')
    (KB_DIR / "index.html").write_text(index_html, encoding="utf-8")
    written.append("/kb/index.html")

    # individual notes
    for i, (slug, (title, cat, date, tags, summary, symptom, cause, fix, lesson)) in enumerate(NOTES.items()):
        others = [s for s in slugs if s != slug][i % max(1, len(slugs) - 1)::max(1, len(slugs) - 1)][:3] or [s for s in slugs if s != slug][:3]
        more = "\n".join(f'<li><a href="/kb/{s}.html">{NOTES[s][0]}</a></li>' for s in others)
        body = f"""<p class="eyebrow"><a href="/kb/" style="color:var(--accent-live);text-decoration:none">Knowledge Base</a> · {CATEGORIES[cat]}</p>
<h1>{title}</h1>
<p class="meta">{date}</p>
<h2>The symptom</h2><p>{symptom}</p>
<h2>What was actually wrong</h2><p>{cause}</p>
<h2>The fix</h2><p>{fix}</p>
<h2>What we took away</h2><p>{lesson}</p>
<ul class="tags">{''.join(f'<li>{t}</li>' for t in tags)}</ul>
<div class="more"><h2 style="margin-top:0">More notes</h2><ul>{more}</ul>
<p><a href="/kb/" style="color:var(--accent-live);text-decoration:none">← All {len(NOTES)} notes</a></p></div>"""
        extra = ('<script type="application/ld+json">' + json.dumps({
            "@context": "https://schema.org", "@type": "TechArticle",
            "headline": title, "datePublished": date, "description": summary,
            "author": {"@type": "Organization", "name": "XH Agents"},
            "publisher": {"@type": "Organization", "name": "XH Agents"},
            "mainEntityOfPage": f"{SITE}/kb/{slug}.html"}) + "</script>\n")
        (KB_DIR / f"{slug}.html").write_text(
            page_shell(f"{title} — XH Agents", html.escape(summary, quote=True),
                       f"{SITE}/kb/{slug}.html", body, extra_head=extra), encoding="utf-8")
        written.append(f"/kb/{slug}.html")

    # sitemap
    sm = DOCROOT / "sitemap.xml"
    if sm.exists():
        shutil.copyfile(sm, str(sm) + f".bak.{STAMP}_kb")
        s = sm.read_text(encoding="utf-8")
        add = "".join(f"  <url><loc>{SITE}/kb/{'' if s2 == 'index.html' else ''}</loc></url>\n" for s2 in [])
        new_urls = [f"{SITE}/kb/"] + [f"{SITE}/kb/{s}.html" for s in slugs]
        for u in new_urls:
            if u not in s:
                s = s.replace("</urlset>", f"  <url><loc>{u}</loc><changefreq>monthly</changefreq><priority>0.6</priority></url>\n</urlset>")
        sm.write_text(s, encoding="utf-8")
        print(f"  ✓ sitemap.xml: {len(new_urls)} URL KB ditambahkan/dicek")
    else:
        print("  ! sitemap.xml tidak ditemukan")

    # footer link on the main pages
    for extra in ["index.html", "about.html", "privacy.html", "terms.html", "disclaimer.html", "ad-order.html"]:
        p = DOCROOT / extra
        if not p.exists():
            continue
        s = p.read_text(encoding="utf-8")
        if 'href="/kb/"' in s:
            print(f"  = {extra}: tautan KB sudah ada"); continue
        s2 = re.sub(r'(<nav class="footer-links"[^>]*>)', r'\1<a href="/kb/">Knowledge Base</a> ', s, count=1)
        if s2 == s:
            print(f"  ! {extra}: footer tidak cocok"); continue
        shutil.copyfile(p, str(p) + f".bak.{STAMP}_kb")
        p.write_text(s2, encoding="utf-8")
        print(f"  ✓ {extra}: tautan Knowledge Base di footer")

    print(f"\n{len(written)} halaman KB ditulis ke {KB_DIR}")


if __name__ == "__main__":
    main()
