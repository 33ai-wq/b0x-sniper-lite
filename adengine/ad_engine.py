#!/usr/bin/env python3
"""
XH Agents — Advertising Engine (self-hosted, x402-native)
- POST /api/ad-order   : advertiser submits order -> returns USDC invoice
- POST /api/ads/activate : internal activate after payment confirmed
- GET  /api/ads        : list active banners (ads.json)
- GET  /api/check-payments : scan Treasury Solana+Base for unpaid orders, activate matches
Stdlib only (no flask). Run: python3 ad_engine.py
"""
import json, sqlite3, os, uuid, time, datetime, hashlib, threading, smtplib, sys, re
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import requests

ROOT = "/var/www/nomad7"
DB = os.path.join(os.path.dirname(__file__), "ads.db")
ADS_JSON = os.path.join(os.path.dirname(__file__), "ads.json")
PORT = 8000
GMAIL_USER = "yusliarifn78@gmail.com"
GMAIL_PASS_FILE = os.path.join(os.path.dirname(__file__), ".gmail_pass")
MARKETING = "marketing@xhagents.xyz"
PARTNER = "partner@xhagents.xyz"

# ---------- shared payment verification + idempotency ----------
sys.path.insert(0, "/home/ubuntu/prpo_ai")
from xh_verify import find_incoming_usdc, verify_tx_usdc, processed  # noqa: E402

SHARED_ENV = "/home/ubuntu/prpo_ai/.env"


def _shared_env(key: str, default: str = "") -> str:
    """Read one key from the shared prpo_ai/.env (the engines are started by systemd
    without an EnvironmentFile, so os.environ alone is not enough)."""
    try:
        for line in open(SHARED_ENV):
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return os.environ.get(key, default)


# Admin token guards the activate endpoint: without it ANYONE could publish an ad.
ADMIN_TOKEN = _shared_env("XH_ADMIN_TOKEN")
# Tests / dry runs must not send real mail.
NO_EMAIL = os.environ.get("XH_AD_NO_EMAIL") == "1" or _shared_env("XH_AD_NO_EMAIL") == "1"
LOOKBACK_BLOCKS = int(_shared_env("XH_LOOKBACK_BLOCKS", "7200"))
AD_MONTH_SECONDS = 30 * 86400
ORDER_RATE_LIMIT_PER_HOUR = int(_shared_env("XH_AD_ORDERS_PER_HOUR", "5"))
_RATE: dict = {}
_RATE_LOCK = threading.Lock()

# ---------- Coinbase CDP Onramp (optional) ----------
# Creates a single-use Onramp session so an advertiser without USDC can
# buy USDC with a card and have it delivered straight to the treasury.
# Requires the CDP project to have an Onramp app attached (this currently
# 404s with "failed to find app with cloud project id" until enabled in
# the CDP Portal). Credentials read from the CDP env file (mode 600).
CDP_ENV_FILE = "/home/ubuntu/prpo_ai/cdp/.env.cdp"
CDP_ONRAMP_API = "https://api.cdp.coinbase.com/platform/v2/onramp/sessions"


def _cdp_env() -> dict:
    env = {}
    try:
        for line in open(CDP_ENV_FILE):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    except OSError as e:
        print("cdp env read error:", e)
    return env


def create_onramp_session(dest_address: str, amount_usdc, redirect_url=""):
    """Return {session_url} by POSTing to CDP Platform v2 Onramp API."""
    env = _cdp_env()
    kid = env.get("CDP_API_KEY_ID", "")
    secret = env.get("CDP_API_KEY_PRIVATE_KEY", "").replace("\\n", "\n")
    if not kid or not secret:
        return {"error": "cdp creds not configured"}
    try:
        from cdp.auth import get_auth_headers
        from cdp.auth.utils.http import GetAuthHeadersOptions
        body = {
            "purchaseCurrency": "USDC",
            "destinationNetwork": "base",
            "destinationAddress": dest_address,
            "purchaseAmount": str(amount_usdc),
            "paymentCurrency": "USD",
        }
        if redirect_url:
            body["redirectUrl"] = redirect_url
        headers = get_auth_headers(GetAuthHeadersOptions(
            api_key_id=kid, api_key_secret=secret,
            request_method="POST",
            request_host="api.cdp.coinbase.com",
            request_path="/platform/v2/onramp/sessions",
            request_body=body,
        ))
        headers["Content-Type"] = "application/json"
        r = requests.post(CDP_ONRAMP_API, headers=headers,
                          json=body, timeout=30)
        if r.status_code == 201:
            data = r.json()
            return {"session_url": data.get("session", {}).get("url")}
        try:
            msg = r.json().get("message") or r.json().get("error", {})
        except Exception:
            msg = r.text[:300]
        return {"error": f"onramp {r.status_code}: {msg}"}
    except Exception as e:
        return {"error": f"onramp exception: {type(e).__name__}: {str(e)[:200]}"}

# Treasury addresses (single source of truth):
#  - XH Agents Base treasury = Coinbase Smart Wallet (MPC, no local private key).
#    Overridable via XH_TREASURY_BASE env so it's not hardcoded in code.
#  - Solana stays the existing x402 treasury (unchanged).
TREASURY = {
    "solana": "GhFbGgNxERN6pQ7boSFLFJuPwXJuvJ8Tx7EgoJ9LV2Aw",
    "base":   os.environ.get(
        "XH_TREASURY_BASE",
        "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0",
    ),
}
# Flat monthly rates (USD == USDC 1:1 for pricing)
RATES = {"728x90": 40, "480x320": 60, "300x250": 35}
SIZES = {"728x90": (728, 90), "480x320": (480, 320), "300x250": (300, 250)}

SOL_RPC = "https://api.mainnet-beta.solana.com"
BASE_RPC = "https://mainnet.base.org"

def db():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS orders(
        id TEXT PRIMARY KEY, size TEXT, network TEXT, amount REAL, email TEXT,
        advertiser_wallet TEXT, title TEXT, text TEXT, image_url TEXT,
        landing_url TEXT, status TEXT, created INTEGER, paid INTEGER, tx_hash TEXT)""")
    have = [r[1] for r in c.execute("PRAGMA table_info(orders)")]
    if "tx_hash" not in have:            # migrate older databases in place
        c.execute("ALTER TABLE orders ADD COLUMN tx_hash TEXT")
    c.commit(); return c

def gen_id():
    return "XH" + hashlib.sha1(uuid.uuid4().bytes).hexdigest()[:10].upper()

def load_ads():
    """Active ads only. Expired placements (30 days) are dropped and the file
    self-heals, so a 'flat monthly rate' really means one month."""
    if not os.path.exists(ADS_JSON): return []
    try:
        ads = json.load(open(ADS_JSON))
    except Exception:
        return []
    now = int(time.time())
    live = [a for a in ads if int(a.get("expire") or 0) > now]
    if len(live) != len(ads):
        try:
            save_ads(live)
        except Exception as e:  # noqa: BLE001
            print("prune err", e)
    return live

def save_ads(ads):
    tmp = ADS_JSON + ".tmp"
    json.dump(ads, open(tmp, "w"), indent=2)
    os.replace(tmp, ADS_JSON)

# ---------- payment detection ----------
def check_solana(order):
    """Scan recent tx to treasury for memo == order id."""
    try:
        r = requests.post(SOL_RPC, json={"jsonrpc":"2.0","id":1,
            "method":"getSignaturesForAddress",
            "params":[TREASURY["solana"], {"limit":15}]}, timeout=8)
        sigs = (r.json().get("result") or [])[:15]
        for s in sigs:
            sig = s.get("signature")
            if not sig: continue
            try:
                tx = requests.post(SOL_RPC, json={"jsonrpc":"2.0","id":1,
                    "method":"getTransaction","params":[sig, {"encoding":"jsonParsed"}]},
                    timeout=8).json().get("result")
                if not tx: continue
                ixs = tx.get("transaction",{}).get("message",{}).get("instructions",[])
                for ix in ixs:
                    memo = ix.get("parsed",{}).get("info",{}).get("memo","") if ix.get("program")=="spl-memo" else ""
                    if order["id"] in memo:
                        return True
            except Exception:
                continue
    except Exception as e:
        print("sol err", e)
    return False

def check_base(order):
    """Return the matching on-chain USDC transfer for this order, or None.

    Fixed 2026-09-23: the old version filtered eth_getLogs by `address = treasury`,
    but ERC-20 Transfer logs are emitted by the USDC **contract**, so it could never
    match and no Base order was ever detected. It also matched on amount alone.
    Now: token contract + topic0 Transfer + topic2 = treasury (+ topic1 = the
    advertiser wallet when they gave one), and each tx hash can be claimed once.
    """
    try:
        payer = (order.get("advertiser_wallet") or "").strip()
        min_atomic = int(round(float(order["amount"]) * 1_000_000 * 0.99))
        hits = find_incoming_usdc(
            TREASURY["base"],
            from_address=payer if payer.startswith("0x") else None,
            min_atomic=min_atomic,
            lookback_blocks=LOOKBACK_BLOCKS,
        )
        for h in hits:
            if not processed.seen(h["tx_hash"]):
                return h
        # If the order has no wallet, fall back to amount matching but ONLY on a
        # payment nobody has claimed yet, so one transfer can't activate two ads.
        if not payer:
            for h in hits:
                if not processed.seen(h["tx_hash"]):
                    return h
        return None
    except Exception as e:  # noqa: BLE001
        print("base err", e)
        return None

def detect_payments():
    c = db()
    rows = c.execute("SELECT * FROM orders WHERE status='pending' ORDER BY created ASC").fetchall()
    cols = [r[1] for r in c.execute("PRAGMA table_info(orders)")]
    activated = []
    for row in rows:
        o = dict(zip(cols, row))
        if o["network"] == "solana":
            paid = check_solana(o)          # returns True/False (memo based)
            tx_hash = None
        else:
            hit = check_base(o)             # returns the matched payment or None
            paid = bool(hit)
            tx_hash = hit["tx_hash"] if hit else None
            if paid and not processed.claim(tx_hash, "ad-order", o["id"], hit["value_atomic"]):
                paid = False                # already credited elsewhere
                print("skip: tx already used", tx_hash)
        if paid:
            c.execute("UPDATE orders SET status='paid', paid=1, tx_hash=? WHERE id=?",
                      (tx_hash, o["id"]))
            try:
                activate(o)
            except Exception as e:  # noqa: BLE001
                print("activate err", e)
            activated.append(o["id"])
    # One payment activates exactly one ad. If the same wallet still has other
    # pending orders of the same size, they stay pending and need their own
    # payment (no double activation, no silent over-crediting).
    for oid in activated:
        pass
    c.commit(); c.close()
    return activated

def send_email(to_addr, subject, body):
    try:
        if NO_EMAIL:
            print("no-email mode, would send:", subject, "->", to_addr)
            return True
        if not os.path.exists(GMAIL_PASS_FILE):
            print("no gmail pass, skip email")
            return False
        pw = open(GMAIL_PASS_FILE).read().strip()
        msg = EmailMessage()
        msg["From"] = GMAIL_USER
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as s:
            s.login(GMAIL_USER, pw)
            s.send_message(msg)
        return True
    except Exception as e:
        print("email err", e)
        return False

URL_RE = re.compile(r"^https?://[^\s<>\"']{4,300}$", re.I)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def _clean_text(v, limit=300):
    """Ad copy is plain text: strip tags and control chars, cap the length."""
    v = re.sub(r"<[^>]*>", "", str(v or ""))
    v = "".join(ch for ch in v if ch >= " " or ch in "\n\t")
    return v.strip()[:limit]


def _clean_url(v):
    v = str(v or "").strip()
    return v if URL_RE.match(v) else ""


def validate_ad_payload(d):
    """Shared validation for new orders and for the activate endpoint."""
    errs = []
    size = str(d.get("size") or "")
    net = str(d.get("network") or "")
    if size not in RATES:
        errs.append("bad size")
    if net not in TREASURY:
        errs.append("bad network")
    email = str(d.get("email") or "").strip()
    if email and not EMAIL_RE.match(email):
        errs.append("bad email")
    wallet = str(d.get("advertiser_wallet") or "").strip()
    if wallet and not (wallet.startswith("0x") and len(wallet) == 42 or len(wallet) >= 32):
        errs.append("bad wallet")
    title = _clean_text(d.get("title"), 120)
    text = _clean_text(d.get("text"), 300)
    image_url = _clean_url(d.get("image_url"))
    landing_url = _clean_url(d.get("landing_url"))
    if not title:
        errs.append("title required")
    if d.get("image_url") and not image_url:
        errs.append("image_url must be an http(s) url")
    if d.get("landing_url") and not landing_url:
        errs.append("landing_url must be an http(s) url")
    if not landing_url:
        errs.append("landing_url required")
    return errs, {
        "size": size, "network": net, "email": email, "advertiser_wallet": wallet,
        "title": title, "text": text, "image_url": image_url, "landing_url": landing_url,
    }


def _rate_ok(ip, bucket="order"):
    now = time.time()
    with _RATE_LOCK:
        key = f"{bucket}:{ip}"
        hits = [t for t in _RATE.get(key, []) if now - t < 3600]
        if len(hits) >= ORDER_RATE_LIMIT_PER_HOUR:
            _RATE[key] = hits
            return False
        hits.append(now)
        _RATE[key] = hits
        return True


def activate(o):
    errs, clean = validate_ad_payload(o)
    if errs:
        raise ValueError("refusing to publish: " + ", ".join(errs))
    ads = load_ads()
    ads = [a for a in ads if a.get("order_id")!=o["id"]]
    ads.append({
        "order_id": o["id"], "size": clean["size"],
        "title": clean["title"], "text": clean["text"],
        "image_url": clean["image_url"], "landing_url": clean["landing_url"],
        "advertiser": clean["email"], "expire": int(time.time())+AD_MONTH_SECONDS,
    })
    save_ads(ads)
    # notify advertiser + marketing that ad is live
    send_email(o["email"], "Your XH Agents ad is LIVE",
        f"Hi,\n\nYour ad '{o['title']}' ({o['size']}) is now live on xhagents.xyz.\nOrder: {o['id']}\n\nThanks for advertising with XH Agents.")
    send_email(MARKETING, f"[XH Ad LIVE] {o['title']} ({o['size']})",
        f"Ad activated: {o['id']}\nAdvertiser: {o['email']}\nSize: {o['size']}\nLanding: {o['landing_url']}")

# ---------- HTTP ----------
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def _j(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type","application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Connection","close")
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        p = urlparse(self.path)
        if p.path == "/api/ads":
            self._j(load_ads())
        elif p.path == "/api/check-payments":
            activated = detect_payments()
            self._j({"activated": activated})
        elif p.path == "/ads.json":
            try:
                self.send_response(200); self.send_header("Content-Type","application/json")
                self.send_header("Access-Control-Allow-Origin","*"); self.end_headers()
                self.wfile.write(open(ADS_JSON).read().encode())
            except: self._j({"error":"no ads"},404)
        else: self._j({"error":"not found"},404)

    def do_POST(self):
        p = urlparse(self.path)
        L = int(self.headers.get("Content-Length",0)); body = self.rfile.read(L)
        try: data = json.loads(body or b"{}")
        except: return self._j({"error":"bad json"},400)
        if p.path == "/api/ad-order":
            return self._order(data)
        elif p.path == "/api/onramp":
            # Build a single-use Coinbase Onramp session to fund an order.
            order_id = data.get("order_id")
            addr = data.get("destination_address") or TREASURY.get("base", "")
            amt = data.get("amount") or RATES.get(data.get("size", ""), 0)
            redirect = "https://xhagents.xyz/ad-order.html" + (f"?order={order_id}" if order_id else "")
            res = create_onramp_session(addr, amt, redirect)
            return self._j(res, 201 if "session_url" in res else 502)
        elif p.path == "/api/ads/activate":
            # Was fully open: anyone could publish an ad on xhagents.xyz.
            ip = self.client_address[0] if self.client_address else ""
            token = self.headers.get("X-Admin-Token", "")
            if not (ip in ("127.0.0.1", "::1") and not ADMIN_TOKEN) and token != ADMIN_TOKEN:
                return self._j({"error": "unauthorized",
                                "message": "X-Admin-Token required (localhost is allowed when no token is configured)"}, 403)
            try:
                activate(data)
            except ValueError as e:
                return self._j({"error": "invalid", "message": str(e)}, 400)
            return self._j({"ok": True})
        elif p.path == "/api/check-payments":
            activated = detect_payments()
            return self._j({"activated": activated})
        return self._j({"error":"not found"},404)

    def _order(self, d):
        ip = self.client_address[0] if self.client_address else "?"
        if not _rate_ok(ip):
            return self._j({"error": "rate_limited", "message": "too many orders from this address — try again later"}, 429)
        errs, clean = validate_ad_payload(d)
        if errs:
            return self._j({"error": "invalid", "details": errs}, 400)
        d = {**d, **clean}
        size = clean["size"]; net = clean["network"]
        oid = gen_id(); amt = RATES[size]
        c = db()
        c.execute("INSERT INTO orders(id,size,network,amount,email,advertiser_wallet,title,"
                  "text,image_url,landing_url,status,created,paid) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (oid, size, net, amt, d.get("email",""), d.get("advertiser_wallet",""),
             d.get("title",""), d.get("text",""), d.get("image_url",""),
             d.get("landing_url",""), "pending", int(time.time()), 0))
        c.commit(); c.close()
        # email invoice to advertiser + notify marketing
        net_name = "Solana" if net=="solana" else "Base"
        send_email(d.get("email",""), "Your XH Agents Ad Invoice",
            f"Hi,\n\nOrder created: {oid}\nSize: {size}\nAmount: {amt} USDC ({net_name})\n\nPay exactly {amt} USDC to:\n{TREASURY[net]}\nwith memo/note: {oid}\n\nYour ad goes live automatically after payment is detected.\nOrder page: https://xhagents.xyz/ad-order.html?order={oid}")
        send_email(MARKETING, f"[XH Ad REQUEST] {d.get('title','')} ({size})",
            f"New order {oid}\nAdvertiser: {d.get('email','')}\nSize: {size}\nAmount: {amt} USDC ({net_name})\nLanding: {d.get('landing_url','')}")
        self._j({
            "order_id": oid, "size": size, "amount_usdc": amt,
            "network": net, "treasury": TREASURY[net],
            "memo": oid,
            "pay_url": f"https://xhagents.xyz/ad-order.html?order={oid}",
            "note": "Send exactly %s USDC to treasury with memo %s" % (amt, oid),
        })

    def log_message(self, *a): pass

if __name__ == "__main__":
    db()
    print("Ad engine on", PORT)
    HTTPServer(("0.0.0.0", PORT), H).serve_forever()
