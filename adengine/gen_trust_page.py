#!/usr/bin/env python3
"""gen_trust_page.py — halaman publik /trust/ dari hasil sapuan (magnet trafik gratis + etalase endpoint).

Membaca data/trust_sweep.json, menulis /var/www/xhagents-www/trust/index.html plus salinan sumber repo.
"""
from __future__ import annotations

import html
import json
import os
import shutil
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # /home/ubuntu/prpo_ai
DATA = os.environ.get("XH_TRUST_SWEEP_JSON", os.path.join(ROOT, "xh_api", "data", "trust_sweep.json"))
TARGETS = ["/var/www/xhagents-www/trust/index.html",
           "/home/ubuntu/xhagents-web/public/trust/index.html"]


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def row_css(score) -> str:
    if not isinstance(score, (int, float)):
        return "s-none"
    if score >= 80:
        return "s-good"
    if score >= 60:
        return "s-ok"
    return "s-bad"


def table(rows: list[dict], limit: int | None = None) -> str:
    out = ['<table><thead><tr><th>#</th><th>origin</th><th>score</th><th>verdict</th><th>endpoints</th>'
           '<th>payTo</th><th>main finding</th></tr></thead><tbody>']
    for i, r in enumerate(rows[:limit] if limit else rows, 1):
        findings = r.get("findings") or []
        main = ""
        for f in findings:
            if not f.lower().startswith(("good", "spf is present", "dmarc policy")):
                main = f
                break
        main = main or (findings[0] if findings else "")
        out.append(
            f'<tr><td>{i}</td><td><code>{esc(r.get("origin"))}</code></td>'
            f'<td class="{row_css(r.get("score"))}">{esc(r.get("score"))}</td>'
            f'<td>{esc(r.get("verdict") or ("unreachable" if not r.get("reachable") else "?"))}</td>'
            f'<td>{esc(r.get("count"))}</td>'
            f'<td><code>{(esc(r.get("payto")) or "")[:12]}…</code></td>'
            f'<td class="f">{esc(main)[:150]}</td></tr>')
    out.append("</tbody></table>")
    return "\n".join(out)


def main() -> None:
    data = json.load(open(DATA))
    origins = data.get("origins", [])
    scored = [r for r in origins if isinstance(r.get("score"), (int, float))]
    stats = data.get("score_stats") or {}
    counts = data.get("counts") or {}
    verdicts = (counts.get("verdicts") or {})
    penalties = data.get("common_penalties") or {}
    gen = data.get("generated_at") or ""

    # ── provenance (2026-10-08): angka kami sendiri, tiga tolok ukur independen ──
    # Dihasilkan oleh ~/x402_rank/gen_provenance.py; halaman tidak pernah menulis angka tangan.
    prov = {}
    prov_path = os.path.join(ROOT, "adengine", "data", "provenance.json")
    if os.path.exists(prov_path):
        try:
            prov = json.load(open(prov_path))
        except Exception:  # noqa: BLE001
            prov = {}
    gl = prov.get("gate_log") or {}
    oc = prov.get("onchain_24h") or {}
    tb = prov.get("__removed_amount_field__") or {}
    th = prov.get("board_thresholds") or {}
    prov_block = ""
    if prov:
        prov_block = f"""
<h2>Our own numbers (call provenance)</h2>
<div class="kpi">
  <div><b>{esc(gl.get('settled_total'))}</b><span>settled calls since {esc((gl.get('since') or '')[:10])}</span></div>
  <div><b>{esc(gl.get('from_external'))}</b><span>from outside callers</span></div>
  <div><b>${esc(oc.get('usdc'))}</b><span>USDC in, last 24h</span></div>
  <div><b>${esc(tb.get('usdc'))}</b><span>treasury balance</span></div>
  <div><b>{esc(prov.get('generated_at', '')[:16].replace('T', ' '))}</b><span>counted (CST)</span></div>
</div>
<div class="note">{esc(prov.get('disclosure'))}</div>
<div class="note">Counting rules, and the board thresholds we measured ({esc(th.get('measured'))}):
place 10 on x402scan's 24-hour server board needs about {esc(th.get('rank10_24h_calls'))} settled calls a day,
its 100th place about {esc(th.get('rank100_24h_calls'))}, and a place on the board at all about
{esc(th.get('on_board_min_24h_calls'))}. We publish where we are instead of buying a position.
This section is rebuilt from <code>adengine/data/provenance.json</code>: the call count is our own request
table filtered by method+path, the transfers are read from Base, the balance is a plain USDC
<code>balanceOf</code> call.</div>
"""

    top = [r for r in scored][:25]
    worst = [r for r in scored][-15:][::-1]
    unreachable = [r for r in origins if not r.get("reachable")]

    pen_rows = "".join(f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in list(penalties.items())[:12])
    verd_rows = "".join(f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in sorted(verd_counts(verdicts)))

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>x402 seller trust leaderboard — XH Agents</title>
<meta name="description" content="Every x402 seller origin we can find, probed from the outside and scored 0-100:
402 behaviour, challenge conformance, discovery documents, on-chain payTo reputation and price sanity.
{len(scored)} origins scored, median {stats.get('median')}. Refreshed {esc(gen[:10])}.">
<link rel="canonical" href="https://xhagents.xyz/trust/">
<style>
:root{{--bg:#0a0a0f;--fg:#e8e8f0;--dim:#9a9ab0;--line:#23233a;--good:#3ddc97;--ok:#e8c547;--bad:#ff6b6b}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial}}
.wrap{{max-width:1100px;margin:0 auto;padding:40px 20px 80px}}
h1{{font-size:30px;margin:0 0 6px}} h2{{font-size:20px;margin:36px 0 10px}}
p.lead{{color:var(--dim);margin:0 0 18px;max-width:70ch}}
.kpi{{display:flex;gap:26px;flex-wrap:wrap;margin:22px 0 6px}}
.kpi div{{background:#12121c;border:1px solid var(--line);border-radius:10px;padding:12px 16px;min-width:120px}}
.kpi b{{display:block;font-size:22px}} .kpi span{{color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.06em}}
table{{width:100%;border-collapse:collapse;margin-top:8px;font-size:13px}}
th,td{{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--dim);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.05em}}
code{{color:#b9c6ff;font-size:12px}} td.f{{color:var(--dim);max-width:340px}}
.s-good{{color:var(--good)}} .s-ok{{color:var(--ok)}} .s-bad{{color:var(--bad)}} .s-none{{color:var(--dim)}}
.note{{border-left:3px solid var(--line);padding:8px 14px;color:var(--dim);margin:18px 0}}
a{{color:#8fb8ff}} .cta{{background:#12121c;border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-top:14px}}
</style>
</head>
<body><div class="wrap">
<h1>x402 seller trust leaderboard</h1>
<p class="lead">An autonomous agent about to pay an endpoint it has never used has almost nothing to go on.
So we sweep the public x402 catalogue — one representative endpoint per origin — and score each origin from the
outside using the same trust layer we sell: unpaid 402 behaviour, challenge conformance, discovery documents,
on-chain <code>payTo</code> reputation and price sanity.</p>
<div class="kpi">
  <div><b>{len(scored)}</b><span>origins scored</span></div>
  <div><b>{esc(stats.get('median'))}</b><span>median score</span></div>
  <div><b>{esc(stats.get('mean'))}</b><span>mean</span></div>
  <div><b>{esc(stats.get('unreachable'))}</b><span>unreachable</span></div>
  <div><b>{esc(gen[:16].replace('T', ' '))}</b><span>checked (UTC)</span></div>
</div>
<div class="note">A score is a point-in-time judgement from the outside — not an audit, not an endorsement, and
not a statement about whether a seller delivers. One endpoint per origin is probed; an origin may run others.
Each row was checked at the time above; scores move as sellers change.</div>
{prov_block}
<h2>Most trusted (top 25)</h2>
{table(top)}

<h2>Lowest scoring</h2>
{table(worst)}

<h2>Verdict spread</h2>
<table><thead><tr><th>verdict</th><th>origins</th></tr></thead><tbody>{verd_rows}</tbody></table>

<h2>Why scores were lost</h2>
<table><thead><tr><th>penalty</th><th>occurrences</th></tr></thead><tbody>{pen_rows}</tbody></table>

<h2>Reproduce any row</h2>
<div class="cta">
<p>One endpoint, live, for $0.05 USDC — <code>POST https://xhagents.xyz/api/x402-trust</code>
with <code>{{"url": "…"}}</code> gives you the same 0-100 report with the evidence and the penalties.</p>
<p>The full ranking as JSON, filterable by verdict and score, is $0.05 —
<code>GET https://xhagents.xyz/api/trust-leaderboard?limit=100&amp;order=worst</code>.
Free method page and top-ten preview: <a href="/api/trust-leaderboard/method">/api/trust-leaderboard/method</a>.</p>
<p>Every endpoint is listed with its price in <a href="/openapi.json">openapi.json</a> and
<a href="/.well-known/x402">/.well-known/x402</a>.</p>
</div>

<h2>Method</h2>
<p class="lead">{esc(data.get('method'))}</p>
<p class="lead">Not checked: {esc(", ".join(data.get('not_checked') or []))}.</p>
<p class="lead">Unreachable at sweep time: {len(unreachable)} origins
{esc(", ".join(r.get('origin', '') for r in unreachable[:8]))}</p>
</div></body></html>
"""
    for t in TARGETS:
        os.makedirs(os.path.dirname(t), exist_ok=True)
        with open(t, "w") as f:
            f.write(page)
        print("ditulis:", t, f"({len(page)} byte)")

    # tambahkan /trust/ ke sitemap kalau belum ada
    for sm in ("/var/www/xhagents-www/sitemap.xml", "/home/ubuntu/xhagents-web/public/sitemap.xml"):
        if not os.path.exists(sm):
            continue
        s = open(sm).read()
        if "https://xhagents.xyz/trust/" in s:
            print("sitemap sudah memuat /trust/:", sm)
            continue
        s = s.replace("</urlset>",
                      f"  <url><loc>https://xhagents.xyz/trust/</loc>"
                      f"<lastmod>{time.strftime('%Y-%m-%d')}</lastmod>"
                      f"<changefreq>daily</changefreq><priority>0.8</priority></url>\n</urlset>")
        shutil.copy(sm, f"{sm}.bak.{int(time.time())}")
        open(sm, "w").write(s)
        print("sitemap diperbarui:", sm)


def verd_counts(verdicts: dict) -> list[tuple[str, int]]:
    return sorted(verdicts.items(), key=lambda kv: -kv[1])


if __name__ == "__main__":
    main()
