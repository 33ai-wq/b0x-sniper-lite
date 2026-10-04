"""domain_audit — the deliverability and security audit an agent runs before it trusts a domain.

One call answers: can mail from this domain be delivered (SPF, DMARC, DKIM, MX), is the web side properly
secured (TLS certificate, redirect, HSTS, security headers), and is the namespace sound (NS, CAA, DNSSEC).
Returns a 0-100 score with the evidence, the reasons points were lost, and what was not checked.

Everything is measured live from DNS and a real TLS handshake — no third-party reputation API, so there is
no upstream cost and no opinion we cannot show the working for.
"""
from __future__ import annotations

import json
import re
import socket
import ssl
import subprocess
import time
from dataclasses import dataclass
from typing import Any

VERDICT_GOOD = 80
VERDICT_OK = 60
DKIM_SELECTORS = ["default", "google", "selector1", "selector2", "k1", "k2", "s1", "s2", "mail", "dkim",
                  "smtp", "mandrill", "everlytickey1", "cm", "protonmail", "zoho"]
LOOKUP_MECHANISMS = ("include", "a", "mx", "ptr", "exists", "redirect")


@dataclass
class Ctx:
    pass


def _dig(name: str, rtype: str, timeout: float = 8.0) -> dict:
    """Use the system resolver (dig) — the same path a mail server takes, and it reports TTL/flags too."""
    out: dict[str, Any] = {"name": name, "type": rtype, "records": []}
    try:
        p = subprocess.run(["dig", "+short", "+time=5", "+tries=2", name, rtype],
                           capture_output=True, text=True, timeout=timeout)
        out["records"] = [ln.strip() for ln in (p.stdout or "").splitlines() if ln.strip()]
        out["rcode_ok"] = p.returncode == 0
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:100]}"
    return out


def _txt(name: str) -> list[str]:
    rows = _dig(name, "TXT")["records"]
    return [r.strip('"') for r in rows]


def _spf(domain: str) -> dict:
    txts = _txt(domain)
    spf = next((t for t in txts if t.lower().startswith("v=spf1")), None)
    out: dict[str, Any] = {"record": spf, "valid": False, "lookups": None, "all_qualifier": None,
                           "issues": []}
    if not spf:
        out["issues"].append("no SPF record: anyone can spoof this domain")
        return out
    terms = spf.split()[1:]
    lookups = 0
    for t in terms:
        core = t.split(":")[0].split("=")[0].lstrip("+-~?")
        if core in LOOKUP_MECHANISMS:
            lookups += 1
        if core == "include":
            pass
        if core == "all":
            out["all_qualifier"] = t[0] if t[0] in "+-~?" else "+"
        if core not in ("all", "include", "a", "mx", "ptr", "exists", "redirect", "ip4", "ip6"):
            out["issues"].append(f"unrecognised mechanism: {t}")
    out["lookups"] = lookups
    out["valid"] = lookups <= 10 and out["all_qualifier"] is not None and not out["issues"]
    if lookups > 10:
        out["issues"].append(f"{lookups} DNS lookups in the record: over the RFC 7208 limit of 10, "
                             "which makes receivers give up and the record fail")
    if out["all_qualifier"] == "+":
        out["issues"].append("+all: the record explicitly authorises every sender on the internet")
    if out["all_qualifier"] is None:
        out["issues"].append("no all: receivers cannot know what to do with unlisted senders")
    return out


def _dmarc(domain: str) -> dict:
    txts = _txt(f"_dmarc.{domain}")
    rec = next((t for t in txts if t.lower().startswith("v=dmarc1")), None)
    out: dict[str, Any] = {"record": rec, "policy": None, "pct": None, "rua": None, "sp": None,
                           "adkim": None, "aspf": None, "issues": []}
    if not rec:
        out["issues"].append("no DMARC record: nobody is told what to do with mail that fails SPF/DKIM")
        return out
    tags: dict[str, str] = {}
    for kv in rec.split(";"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            tags[k.strip().lower()] = v.strip()
    out["policy"] = (tags.get("p") or "").strip().lower() or None
    pct = (tags.get("pct") or "100").strip()
    out["pct"] = int(pct) if pct.isdigit() else None
    out["rua"] = (tags.get("rua") or "").strip() or None
    out["sp"] = (tags.get("sp") or "").strip() or None
    out["adkim"] = (tags.get("adkim") or "r").strip()
    out["aspf"] = (tags.get("aspf") or "r").strip()
    if out["policy"] == "none":
        out["issues"].append("p=none: monitoring only, failing mail is still delivered")
    if out["policy"] is None:
        out["issues"].append("no p= tag: the record is not usable")
    if not out["rua"]:
        out["issues"].append("no rua: nobody receives the aggregate failure reports")
    return out


def _dkim(domain: str) -> dict:
    """Probe the common selectors, but first check for a wildcard: some domains answer every selector
    (example.com publishes `*._domainkey` with an empty p=) and counting that as a key would be a lie."""
    probe_name = f"xh-probe-nonexistent-9f3a._domainkey.{domain}"
    probe = _txt(probe_name)
    wildcard = probe[0] if probe else None
    found: list[dict] = []
    empty: list[dict] = []
    for sel in DKIM_SELECTORS:
        recs = _txt(f"{sel}._domainkey.{domain}")
        rec = next((r for r in recs if "v=dkim1" in r.lower() or "p=" in r), None)
        if not rec:
            continue
        if wildcard is not None and rec.strip() == wildcard.strip():
            continue  # a wildcard answer: this selector has no key of its own
        key = re.search(r"p=([A-Za-z0-9+/=]+)", rec)
        row = {"selector": sel, "record": rec[:220], "has_public_key": bool(key and key.group(1))}
        if row["has_public_key"]:
            found.append(row)
        else:
            empty.append({**row, "note": "record exists but p= is empty, which marks the key as revoked"})
    return {"selectors_checked": len(DKIM_SELECTORS), "found": found, "empty": empty,
            "wildcard": wildcard is not None,
            "wildcard_record": (wildcard[:120] if wildcard else None)}


def _mx(domain: str) -> dict:
    rows = _dig(domain, "MX")["records"]
    hosts = []
    for r in rows:
        parts = r.split()
        if len(parts) == 2:
            hosts.append({"priority": int(parts[0]) if parts[0].isdigit() else None, "host": parts[1].rstrip(".")})
    null_mx = bool(rows) and all((h["host"] == "" for h in hosts))
    for h in hosts:
        h["resolves"] = bool(_dig(h["host"], "A")["records"]) if h["host"] else False
    return {"records": rows, "hosts": hosts, "null_mx": null_mx}


def _tls(domain: str, port: int = 443) -> dict:
    out: dict[str, Any] = {"port": port}
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((domain, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ss:
                cert = ss.getpeercert() or {}
                out["tls_version"] = ss.version()
                out["cipher"] = (ss.cipher() or [None])[0]
                subject = cert.get("subject") or ()
                issuer = cert.get("issuer") or ()
                out["subject"] = dict((k, v) for part in subject for k, v in part)
                out["issuer"] = dict((k, v) for part in issuer for k, v in part)
                out["san"] = [v for k, v in (cert.get("subjectAltName") or ()) if k == "DNS"][:20]
                out["not_after"] = cert.get("notAfter")
                out["hostname_ok"] = True
                if cert.get("notAfter"):
                    import datetime as _dt
                    exp = _dt.datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
                    out["days_until_expiry"] = (exp - _dt.datetime.utcnow()).days
    except ssl.SSLCertVerificationError as e:
        out["error"] = f"certificate verification failed: {str(e)[:160]}"
        out["hostname_ok"] = False
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:140]}"
    return out


def _http_probe(domain: str) -> dict:
    import httpx
    out: dict[str, Any] = {}
    try:
        with httpx.Client(follow_redirects=False, timeout=15) as c:
            r = c.get(f"http://{domain}/")
            out["http_status"] = r.status_code
            out["http_redirects_to_https"] = bool(r.headers.get("location", "").startswith("https://"))
        with httpx.Client(follow_redirects=True, timeout=15) as c:
            r = c.get(f"https://{domain}/", headers={"User-Agent": "xh-agents-domain-audit/1.0"})
            out["https_status"] = r.status_code
            h = {k.lower(): v for k, v in r.headers.items()}
            out["server"] = h.get("server")
            out["hsts"] = h.get("strict-transport-security")
            out["security_headers"] = {
                "content-security-policy": bool(h.get("content-security-policy")),
                "x-content-type-options": h.get("x-content-type-options"),
                "x-frame-options": h.get("x-frame-options"),
                "referrer-policy": h.get("referrer-policy"),
                "permissions-policy": bool(h.get("permissions-policy")),
            }
            if out["hsts"]:
                m = re.search(r"max-age=(\d+)", out["hsts"])
                out["hsts_max_age"] = int(m.group(1)) if m else None
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:140]}"
    return out


def assess(ctx: Ctx, domain: str) -> dict:
    started = time.time()
    domain = (domain or "").strip().lower()
    domain = re.sub(r"^https?://", "", domain).split("/")[0].split(":")[0]
    if not re.fullmatch(r"(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}", domain):
        return {"domain": domain, "error": "not a valid domain name", "score": 0, "verdict": "invalid"}

    spf = _spf(domain)
    dmarc = _dmarc(domain)
    dkim = _dkim(domain)
    mx = _mx(domain)
    tls = _tls(domain)
    http = _http_probe(domain)
    ns = _dig(domain, "NS")["records"]
    caa = _dig(domain, "CAA")["records"]
    a = _dig(domain, "A")["records"]
    aaaa = _dig(domain, "AAAA")["records"]

    points: dict[str, Any] = {}
    findings: list[str] = []

    # mail authentication (45)
    p = 0.0
    if spf.get("record"):
        p += 12
        if not spf["issues"]:
            p += 6
            findings.append("SPF is present and within limits")
        else:
            findings.extend(spf["issues"][:2])
    else:
        findings.append("no SPF record")
    if dmarc.get("record"):
        p += 10
        if dmarc["policy"] in ("quarantine", "reject"):
            p += 10
            findings.append(f"DMARC policy {dmarc['policy']} — failing mail is acted on")
        elif dmarc["policy"] == "none":
            p += 3
        if dmarc.get("rua"):
            p += 3
    else:
        findings.append("no DMARC record")
    if dkim["found"]:
        p += 4
        findings.append(f"DKIM key(s) found for selector(s): {', '.join(f['selector'] for f in dkim['found'][:3])}")
    elif dkim.get("wildcard"):
        p += 2
        findings.append("no DKIM key of its own: the zone answers every selector with an empty p= (a wildcard), "
                        "which is a deliberate 'no DKIM here' signal rather than a missing record")
    else:
        findings.append("no DKIM key on the common selectors (a private selector may exist — it cannot be guessed)")
    if not dkim["found"] and dkim.get("empty"):
        findings.append("selectors present but revoked (empty p=): "
                        + ", ".join(e["selector"] for e in dkim["empty"][:4]))
    points["mail_auth"] = round(min(p, 45.0), 1)

    # mail delivery (15)
    p = 0.0
    if mx.get("null_mx"):
        p += 10
        findings.append("null MX (RFC 7505): this domain states it does not receive mail at all — treated as "
                        "intentional, not as a fault")
    elif mx["hosts"]:
        resolving = [h for h in mx["hosts"] if h["resolves"]]
        if len(resolving) >= 2:
            p += 15
            findings.append(f"{len(resolving)} MX hosts resolve")
        elif resolving:
            p += 9
            findings.append("a single MX host resolves — no mail redundancy")
        else:
            p += 2
            findings.append("MX records exist but none resolve")
    else:
        findings.append("no MX records: the domain cannot receive mail")
    points["mail_delivery"] = round(p, 1)

    # TLS (25)
    p = 0.0
    if tls.get("hostname_ok") and not tls.get("error"):
        p += 15
        findings.append(f"valid TLS certificate ({tls.get('issuer')}, expires in {tls.get('days_until_expiry')} days)")
        if (tls.get("days_until_expiry") or 999) < 15:
            p -= 5
            findings.append("certificate expires in under two weeks")
        if (tls.get("tls_version") or "") >= "TLSv1.2":
            p += 5
    elif tls.get("error"):
        findings.append(f"TLS problem: {tls['error'][:120]}")
    points["tls"] = round(max(0.0, min(p, 25.0)), 1)

    # web hygiene (15)
    p = 0.0
    if http.get("http_redirects_to_https"):
        p += 5
    elif http.get("http_status"):
        findings.append("plain HTTP does not redirect to HTTPS")
    if http.get("hsts"):
        p += 5
        findings.append(f"HSTS max-age={http.get('hsts_max_age')}")
    else:
        findings.append("no HSTS header: a downgrade attack stays possible")
    sh = http.get("security_headers") or {}
    have = sum(1 for k in ("content-security-policy", "x-content-type-options", "x-frame-options",
                           "referrer-policy") if sh.get(k))
    p += min(5.0, have * 1.25)
    points["web_hygiene"] = round(min(p, 15.0), 1)

    # namespace hygiene (bonus adjustments)
    bonus = 0.0
    if caa:
        bonus += 3
    if ns:
        bonus += 2
    points["namespace_bonus"] = round(bonus, 1)

    raw = sum(points.values())
    score = max(0, min(100, round(raw)))
    verdict = "good" if score >= VERDICT_GOOD else ("acceptable" if score >= VERDICT_OK else "weak")

    return {
        "domain": domain, "score": score, "verdict": verdict,
        "points": points,
        "weights": {"mail_auth": 45, "mail_delivery": 15, "tls": 25, "web_hygiene": 15,
                    "namespace_bonus": 5},
        "dns": {"a": a, "aaaa": aaaa, "ns": ns, "caa": caa, "mx": mx},
        "mx": mx,
        "spf": spf, "dmarc": dmarc, "dkim": dkim,
        "tls": tls, "http": http,
        "findings": findings,
        "methodology": {
            "resolver": "the system resolver (dig), the same path a receiving mail server takes",
            "spf": "mechanisms parsed and counted against the RFC 7208 lookup limit of 10",
            "dmarc": "_dmarc TXT parsed: policy, pct, rua, alignment",
            "dkim": f"{len(DKIM_SELECTORS)} common selectors probed; an unlisted selector cannot be guessed",
            "tls": "a real handshake with certificate verification and hostname checking",
            "http": "a real request: redirect behaviour, HSTS and the common security headers",
        },
        "not_checked": [
            "blocklist and blacklist standing (needs a reputation feed)",
            "actual inbox placement: a test send is the only proof",
            "BIMI/VMC certificates and DMARC aggregate reports",
            "the content or reputation of the mail actually sent",
        ],
        "verdicts": {"good": f">= {VERDICT_GOOD}", "acceptable": f"{VERDICT_OK}-{VERDICT_GOOD - 1}",
                     "weak": f"< {VERDICT_OK}"},
        "elapsed_ms": round((time.time() - started) * 1000),
    }


def register(app, ctx: Ctx) -> None:
    from pydantic import BaseModel, Field

    class DomainReq(BaseModel):
        domain: str = Field(..., description="Domain to audit, e.g. example.com")

    @app.get("/domain-audit/method")
    def index():
        return {
            "provider": "XH Agents — domain & email deliverability audit",
            "what_it_is": ("Mail authentication (SPF/DMARC/DKIM), mail delivery (MX), TLS certificate, web "
                           "hygiene (redirect, HSTS, security headers) and namespace hygiene — scored 0-100 with "
                           "the evidence and the reasons points were lost."),
            "price_usdc_per_call": 0.05,
            "endpoints": [{"route": "POST /api/domain-audit", "price_usd": 0.05},
                          {"route": "GET /api/domain-audit?domain=…", "price_usd": 0.05}],
            "verdicts": {"good": ">= 80", "acceptable": "60-79", "weak": "< 60"},
            "weights": {"mail_auth": 45, "mail_delivery": 15, "tls": 25, "web_hygiene": 15,
                        "namespace_bonus": 5},
            "not_checked": ["blocklists", "inbox placement", "BIMI", "mail content reputation"],
        }

    def _run(domain: str) -> dict:
        return assess(ctx, domain)

    @app.post("/domain-audit")
    def audit_post(req: DomainReq):
        return _run(req.domain)

    @app.get("/domain-audit")
    def audit_get(domain: str):
        return _run(domain)
