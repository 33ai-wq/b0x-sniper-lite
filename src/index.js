/**
 * ebook-store — Self-hosted crypto ebook store
 * Cloudflare Worker
 *
 * Flow:
 *   GET  /             → Landing page + buy button
 *   POST /checkout     → Returns x402 invoice (10 USDC on Base, $9.99)
 *   GET  /download/:t  → Payment status + delivery
 *   GET  /claim?t=X&tx=0x... → Verify tx on-chain → deliver EPUB
 */

const CFG = {
  payoutAddress: "0x57EEC52d76A4A78D4562fc2564101A4bD2e3F357",
  usdcContract:  "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
  network:       "eip155:8453",
  price:         "10000000",  // 10 USDC (6 decimals)
  priceUSD:      "$9.99",
};

const HTML_LANDING = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>B0x70Logical — The Onchain Operator's Playbook</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:linear-gradient(135deg,#0a1f2e 0%,#1a365d 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;color:#f0f4f8}
.container{max-width:600px;padding:40px;text-align:center}
.badge{background:rgba(34,211,238,.15);border:1px solid #22d3ee;color:#22d3ee;padding:6px 16px;border-radius:20px;font-size:13px;font-weight:600;letter-spacing:.5px;display:inline-block;margin-bottom:24px}
.cover-box{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);border-radius:16px;padding:32px;margin-bottom:32px}
.cover-box h1{font-size:28px;font-weight:800;color:#fbbf24;line-height:1.2;margin-bottom:8px}
.cover-box .sub{font-size:16px;color:#22d3ee;margin-bottom:20px}
.price-tag{font-size:40px;font-weight:800;color:#fff;margin:16px 0 8px}
.price-tag span{font-size:18px;color:rgba(255,255,255,.6);font-weight:400}
.payment-options{background:rgba(255,255,255,.05);border-radius:12px;padding:20px;margin:20px 0}
.payment-row{display:flex;align-items:center;justify-content:center;gap:10px;font-size:14px;color:rgba(255,255,255,.7);margin:8px 0}
.check{color:#22c55e;font-size:18px}
.buy-btn{background:linear-gradient(135deg,#22c55e,#16a34a);color:#fff;border:none;padding:18px 48px;font-size:18px;font-weight:700;border-radius:12px;cursor:pointer;width:100%;transition:transform .2s,box-shadow .2s;box-shadow:0 4px 20px rgba(34,197,94,.3);margin-top:8px}
.buy-btn:hover{transform:translateY(-2px);box-shadow:0 8px 30px rgba(34,197,94,.4)}
.buy-btn:active{transform:translateY(0)}
.buy-btn:disabled{opacity:.6;cursor:not-allowed}
.footer{margin-top:24px;font-size:12px;color:rgba(255,255,255,.4);line-height:1.6}
.footer a{color:#22d3ee;text-decoration:none}
.note{background:rgba(251,191,36,.1);border:1px solid rgba(251,191,36,.3);border-radius:8px;padding:12px 16px;font-size:13px;color:#fbbf24;margin-top:16px;text-align:left}
.note strong{color:#22c55e}
#payBox{display:none;margin-top:20px;background:rgba(34,211,238,.08);border:1px solid #22d3ee;border-radius:12px;padding:20px;text-align:left}
#payBox h3{color:#22d3ee;margin-bottom:12px;font-size:15px}
.pay-row{font-size:13px;color:rgba(255,255,255,.8);line-height:1.8;margin-bottom:6px}
.pay-row strong{color:#fff}
.pay-code{background:rgba(255,255,255,.1);padding:8px;border-radius:8px;display:block;font-size:12px;word-break:break-all;color:#fff;font-family:monospace;margin-top:4px}
.pay-headers{background:rgba(0,0,0,.3);border-radius:8px;padding:12px;margin-top:12px}
.pay-headers-label{font-size:11px;color:rgba(255,255,255,.4);margin-bottom:4px}
.pay-headers-code{font-size:11px;color:#fbbf24;word-break:break-all;font-family:monospace}
.claim-btn{background:rgba(34,211,238,.15);border:1px solid #22d3ee;color:#22d3ee;padding:10px 24px;border-radius:8px;cursor:pointer;font-weight:600;margin-top:16px;width:100%}
.claim-btn:hover{background:rgba(34,211,238,.25)}
.success-box{background:rgba(34,197,94,.1);border:1px solid #22c55e;border-radius:12px;padding:24px;margin-top:20px}
.success-box h3{color:#22c55e;margin-bottom:12px}
.success-box a{display:inline-block;background:#22c55e;color:#fff;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:700;margin-top:12px}
</style>
</head>
<body>
<div class="container">
  <div class="badge">B0x70Logical &middot; DIGITAL EBOOK &middot; DRM-FREE</div>
  <div class="cover-box">
    <h1>B0x70Logical<br>The Onchain Operator's Playbook</h1>
    <p class="sub">Build Paid APIs. Run Crypto Infrastructure. Earn.</p>
    <div class="price-tag">10 USDC <span>($9.99)</span></div>
    <div class="payment-options">
      <div class="payment-row"><span class="check">&check;</span> EPUB + DOCX formats</div>
      <div class="payment-row"><span class="check">&check;</span> Delivered instantly after payment</div>
      <div class="payment-row"><span class="check">&check;</span> No account required</div>
      <div class="payment-row"><span class="check">&check;</span> DRM-free, yours forever</div>
    </div>
    <button class="buy-btn" id="buyBtn" onclick="startCheckout()">&#128274; Pay with USDC on Base</button>
    <div id="payBox">
      <h3>&#128203; Payment Instructions</h3>
      <div class="pay-row"><strong>Network:</strong> <code id="netName"></code></div>
      <div class="pay-row"><strong>Token:</strong> <code id="assetName"></code></div>
      <div class="pay-row"><strong>Amount:</strong> <code id="volAmt" style="color:#22c55e;font-size:16px;font-weight:bold;"></code></div>
      <div class="pay-row"><strong>Send to:</strong><code id="payTo" class="pay-code"></code></div>
      <p style="font-size:12px;color:rgba(255,255,255,.5);margin-top:12px;">
        Use any Ethereum/Base wallet (MetaMask, Rabby, Coinbase Wallet).<br>
        After sending, click <strong>"Check Payment & Download"</strong> below.
      </p>
      <div class="pay-headers">
        <div class="pay-headers-label">x402 headers to include in your transaction:</div>
        <div class="pay-headers-code" id="x402hdrs"></div>
      </div>
      <button class="claim-btn" id="claimBtn" onclick="checkStatus()">&#128270; Check Payment & Download</button>
    </div>
    <div id="successBox" class="success-box" style="display:none">
      <h3>&#9989; Payment Confirmed!</h3>
      <p style="font-size:14px;color:rgba(255,255,255,.8);">Your ebook is ready for download.</p>
      <a id="dlLink" href="#">Download The Onchain Operator's Playbook (.epub)</a>
    </div>
    <div class="note">
      <strong>How it works:</strong> Click the button above &rarr; copy the <strong>Send to</strong> address into your wallet &rarr; send exactly <span id="noteAmt">10 USDC</span> with the x402 headers &rarr; click <strong>Check Payment & Download</strong>.
    </div>
  </div>
  <div class="footer">
    Secure payment via x402 protocol &middot; Powered by Cloudflare Workers<br>
    Recipient: 0x57EE...F357 &middot; USDC on Base
  </div>
</div>
<script>
let gToken = '';
let gInvoice = {};
let gVolume = '';
let gPayTo = '';
async function startCheckout(){
  var btn=document.getElementById('buyBtn');
  if(btn.disabled)return;
  btn.textContent='\u23F3 Generating invoice...';
  btn.disabled=true;
  try{
    var res=await fetch('/checkout',{method:'POST'});
    var data=await res.json();
    if(!data.invoice){alert('Error: '+JSON.stringify(data));return;}
    gToken=data.downloadToken;
    var inv=data.invoice;
    gInvoice=inv;
    gVolume=String(Number(BigInt(inv.volume))/1e6);
    gPayTo=inv.recipient;
    var net=inv.network||'eip155:8453';
    var netName=net.includes('8453')?'Base':'Base';
    document.getElementById('netName').textContent=netName+' (eip155:8453)';
    document.getElementById('assetName').textContent=inv.asset;
    document.getElementById('volAmt').textContent=gVolume+' USDC';
    document.getElementById('payTo').textContent=inv.recipient;
    document.getElementById('noteAmt').textContent=gVolume+' USDC';
    var hdrs='x402: '+(inv.schema||'x402')+'\n'+
             'x402-asset: '+inv.asset+'\n'+
             'x402-network: '+net+'\n'+
             'x402-volume: '+inv.volume+'\n'+
             'x402-pay-to: '+inv.recipient+'\n'+
             'x402-timeout: '+inv.maxTimeout+'\n'+
             'x402-recipient: '+inv.recipient+'\n'+
             'x402-nonce: '+inv.nonce;
    document.getElementById('x402hdrs').textContent=hdrs;
    document.getElementById('buyBtn').style.display='none';
    document.getElementById('payBox').style.display='block';
  }catch(e){
    alert('Error: '+e.message);
    btn.textContent='&#128274; Pay with USDC on Base';
    btn.disabled=false;
  }
}
async function checkStatus(){
  var btn=document.getElementById('claimBtn');
  btn.textContent='\u23F3 Verifying on-chain...';
  btn.disabled=true;
  try{
    var res=await fetch('/download/'+gToken);
    var data=await res.json();
    if(data.status==='paid'||data.downloadUrl){
      document.getElementById('payBox').style.display='none';
      document.getElementById('successBox').style.display='block';
      var dlLink=document.getElementById('dlLink');
      dlLink.href='/download/'+gToken+'?claim=1';
    } else {
      alert('Payment not confirmed yet. Make sure you sent exactly '+gVolume+' USDC with x402 headers to: '+gPayTo);
      btn.textContent='\u2705 Check Payment & Download';
      btn.disabled=false;
    }
  }catch(e){
    alert('Error: '+e.message);
    btn.textContent='\u2705 Check Payment & Download';
    btn.disabled=false;
  }
}
</script>
</body>
</html>`;

// In-memory invoice store (per isolate — resets on cold start)
// For production: use KV binding
const invoiceStore = new Map();

function randomNonce() {
  const arr = new Uint8Array(16);
  crypto.getRandomValues(arr);
  return Array.from(arr, b => b.toString(16).padStart(2, '0')).join('');
}

function createInvoice(downloadToken) {
  const now = Math.floor(Date.now() / 1000);
  return {
    schema:     "x402",
    network:    CFG.network,
    asset:      CFG.usdcContract,
    volume:     CFG.price,
    maxTimeout: String(now + 900),
    recipient:  CFG.payoutAddress,
    nonce:      randomNonce(),
  };
}

function getKV(env) {
  return env.EBOOK_KV || null;
}

// GET /
async function handleRoot() {
  return new Response(HTML_LANDING, {
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "public, max-age=3600" },
  });
}

// POST /checkout
async function handleCheckout(env) {
  const kv = getKV(env);
  const downloadToken = randomNonce();
  const invoice = createInvoice(downloadToken);
  const invData = { invoice, createdAt: Date.now(), paid: false };

  invoiceStore.set(downloadToken, invData);
  if (kv) {
    await kv.put("inv:" + downloadToken, JSON.stringify(invData), { expirationTtl: 900 });
  }

  return new Response(JSON.stringify({
    invoice,
    downloadToken,
    expiresIn: 900,
    instructions: "Send exactly " + (Number(BigInt(CFG.price)) / 1e6) + " USDC to the recipient address with the x402 headers.",
    checkUrl: "/download/" + downloadToken,
  }), {
    headers: { "Content-Type": "application/json" },
  });
}

// GET /download/:token
async function handleDownload(token, env) {
  const kv = getKV(env);
  let invData = invoiceStore.get(token);
  if (!invData && kv) {
    const stored = await kv.get("inv:" + token);
    if (stored) invData = JSON.parse(stored);
  }

  if (!invData) {
    return new Response(JSON.stringify({ error: "Download token not found or expired." }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });
  }

  const { invoice, paid } = invData;
  const now = Math.floor(Date.now() / 1000);
  const expiresAt = Number(BigInt(invoice.maxTimeout));

  if (now > expiresAt + 120) {
    return new Response(JSON.stringify({ error: "Payment window expired. Please start a new checkout." }), {
      status: 410,
      headers: { "Content-Type": "application/json" },
    });
  }

  // Handle claim=1 — verify payment and deliver
  const url = new URL("http://x/");
  // Check if this is a claim request (passed via query param from JS)
  // We use ?claim=1 flag set by the download link button
  // The JS already calls /download/token which returns JSON with status
  // Then redirects to /download/token?claim=1 if paid

  return new Response(JSON.stringify({
    status: paid ? "paid" : "awaiting_payment",
    invoice,
    token,
    message: paid
      ? "Payment confirmed. Your download is ready."
      : "Payment not yet confirmed. Please ensure your wallet sent exactly " +
        (Number(BigInt(CFG.price)) / 1e6) + " USDC to the invoice address.",
    downloadUrl: paid ? "/download/" + token + "?claim=1" : null,
  }), {
    headers: { "Content-Type": "application/json" },
  });
}

// POST /claim (internal — called by claim page)
async function handleClaim(token, txHash, env) {
  const kv = getKV(env);
  let invData = invoiceStore.get(token);
  if (!invData && kv) {
    const stored = await kv.get("inv:" + token);
    if (stored) invData = JSON.parse(stored);
  }

  if (!invData) {
    return new Response(JSON.stringify({ error: "Token not found." }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });
  }

  if (invData.paid) {
    return deliverEpub(invData, env);
  }

  // Verify tx on Base via public RPC
  const rpcUrl = "https://base.gateway.tenderly.co";
  const payoutLower = CFG.payoutAddress.toLowerCase().replace("0x", "");
  const payoutPadded = "0x" + "0".repeat(24) + payoutLower;

  try {
    const body = {
      jsonrpc: "2.0",
      method: "eth_getTransactionReceipt",
      params: [txHash],
      id: 1,
    };

    const rpcRes = await fetch(rpcUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!rpcRes.ok) {
      return new Response(JSON.stringify({ error: "Could not reach Base RPC." }), {
        status: 502,
        headers: { "Content-Type": "application/json" },
      });
    }

    const rpcData = await rpcRes.json();
    const receipt = rpcData.result;

    if (!receipt) {
      return new Response(JSON.stringify({ error: "Transaction not found on Base blockchain." }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Verify tx.to === USDC contract
    const usdcLower = CFG.usdcContract.toLowerCase();
    if (!receipt.to || receipt.to.toLowerCase() !== usdcLower) {
      return new Response(JSON.stringify({ error: "Transaction was not sent to USDC contract." }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Find Transfer log: topic[0]=Transfer sig, topic[2]=to (payout address), topic[3]=value
    const TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";

    const transferLog = receipt.logs && receipt.logs.find(log => {
      if (!log.topics || log.topics.length < 4) return false;
      return log.topics[0] === TRANSFER_TOPIC && log.topics[2] === payoutPadded;
    });

    if (!transferLog) {
      return new Response(JSON.stringify({ error: "No USDC transfer to payout address found in this transaction." }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Verify amount >= price
    const logValueHex = transferLog.topics[3] || "0x0";
    const logValue = BigInt(logValueHex);
    const expectedPrice = BigInt(CFG.price);

    if (logValue < expectedPrice) {
      return new Response(JSON.stringify({
        error: "Insufficient payment. Required: " + (Number(expectedPrice) / 1e6) +
               " USDC, Received: " + (Number(logValue) / 1e6) + " USDC",
      }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Payment verified!
    invData.paid = true;
    invoiceStore.set(token, invData);
    if (kv) {
      await kv.put("inv:" + token, JSON.stringify(invData), { expirationTtl: 86400 });
    }

    return deliverEpub(invData, env);

  } catch (e) {
    return new Response(JSON.stringify({ error: "Verification failed: " + e.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
}

async function deliverEpub(invData, env) {
  // Try env var first (base64 encoded EPUB — set at deploy time)
  if (env.EPUB_BASE64) {
    try {
      const decoded = Buffer.from(env.EPUB_BASE64, "base64");
      return new Response(decoded, {
        headers: {
          "Content-Type": "application/epub+zip",
          "Content-Disposition": "attachment; filename=\"the-onchain-operators-playbook.epub\"",
          "Cache-Control": "private, no-store",
        },
      });
    } catch (_) {}
  }

  // Try KV store
  const kv = getKV(env);
  if (kv) {
    const epub = await kv.get("ebook:epub", "arrayBuffer");
    if (epub) {
      return new Response(epub, {
        headers: {
          "Content-Type": "application/epub+zip",
          "Content-Disposition": "attachment; filename=\"the-onchain-operators-playbook.epub\"",
          "Cache-Control": "private, no-store",
        },
      });
    }
  }

  return new Response(JSON.stringify({ error: "Ebook file not available. Please contact support." }), {
    status: 503,
    headers: { "Content-Type": "application/json" },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Root
    if (url.pathname === "/" && request.method === "GET") {
      return handleRoot();
    }

    // Checkout
    if (url.pathname === "/checkout" && request.method === "POST") {
      return handleCheckout(env);
    }

    // Download / claim
    if (url.pathname.startsWith("/download/")) {
      const token = url.pathname.split("/download/")[1];
      const isClaim = url.searchParams.get("claim") === "1";
      const txHash = url.searchParams.get("tx");

      if (isClaim || txHash) {
        return handleClaim(token, txHash || url.searchParams.get("tx") || "", env);
      }

      return handleDownload(token, env);
    }

    // Legacy claim URL: /claim?token=X&tx=0x...
    if (url.pathname === "/claim" && request.method === "GET") {
      const token = url.searchParams.get("token");
      const tx = url.searchParams.get("tx");
      if (!token) {
        return new Response(JSON.stringify({ error: "Missing token." }), {
          status: 400,
          headers: { "Content-Type": "application/json" },
        });
      }
      return handleClaim(token, tx || "", env);
    }

    // x402 protocol discovery
    if (url.pathname === "/.well-known/x402") {
      return new Response(JSON.stringify({
        version: "1.0",
        resources: [{
          rel:   "invoice",
          href:  "/checkout",
          method: "POST",
          schemas: ["x402"],
        }],
      }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    // Health
    if (url.pathname === "/health") {
      return new Response(JSON.stringify({
        status: "ok",
        product: "The Onchain Operator's Playbook",
        price: CFG.price,
        priceUSD: CFG.priceUSD,
        network: CFG.network,
        recipient: CFG.payoutAddress,
      }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response(JSON.stringify({ error: "Not found." }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });
  },
};