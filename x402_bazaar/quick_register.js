#!/usr/bin/env node
// quick_register.js — daftarkan endpoint x402 yang SUDAH VALID ke x402bazaar.org
// Menggunakan node/viem (signMessage) yang MATCH dengan recoverMessageAddress backend bazaar
// (terbukti: recover == account.address). Ini yang beneran diterima (bukan eth_account Python).
//
// Endpoint yang didaftarkan (JANGAN ubah kode upstream):
//   #1 b0x402-core-base @ x402-cf-worker.mulberry-boar.workers.dev (Base)  $0.01/call
//   #2 b0x402-data-base @ b0x402-data.mulberry-boar.workers.dev (Base)     $0.01/call
// Private key baca dari /home/ubuntu/prpo_ai/x402_bazaar/.bazaar_key (0x57ee...f357, mode 600).
//
// Usage:
//   node quick_register.js            # daftarkan #1 & #2
//   node quick_register.js --verify   # hanya cek address, no POST
const fs = require('fs');
const { privateKeyToAccount } = require('viem/accounts');
const { recoverMessageAddress } = require('viem');
const path = require('path');

const KEY_FILE = '/home/ubuntu/prpo_ai/x402_bazaar/.bazaar_key';
const SERVER = process.env.BAZAAR_SERVER || 'https://x402-api.onrender.com';

const SERVICES = [
  { name: 'b0x402-core-base', url: 'https://x402-cf-worker.mulberry-boar.workers.dev/v1/meme-hunter', price: 0.01 },
  { name: 'b0x402-data-base', url: 'https://b0x402-data.mulberry-boar.workers.dev/v1/b0x402-data', price: 0.01 },
];

async function main() {
  const key = fs.readFileSync(KEY_FILE, 'utf8').trim();
  const account = privateKeyToAccount(key.startsWith('0x') ? key : '0x' + key);
  console.log('Wallet:', account.address);

  const verifyOnly = process.argv.includes('--verify');

  for (const s of SERVICES) {
    const ts = Date.now();
    const message = `quick-register:${s.url}:${account.address}:${ts}`;
    const signature = await account.signMessage({ message });

    if (verifyOnly) {
      const rec = await recoverMessageAddress({ message, signature });
      console.log(`  [${s.name}] recover match: ${rec.toLowerCase() === account.address.toLowerCase()}`);
      continue;
    }

    const body = { url: s.url, ownerAddress: account.address, timestamp: ts, signature, price: s.price, name: s.name };
    try {
      const r = await fetch(`${SERVER}/quick-register`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      const data = await r.json();
      console.log(`\n[${s.name}] HTTP ${r.status}`);
      console.log(JSON.stringify(data, null, 2).slice(0, 900));
    } catch (e) {
      console.log(`[${s.name}] ERR`, e.message);
    }
  }
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });