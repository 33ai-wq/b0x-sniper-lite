#!/usr/bin/env node
// register_kb.js — register KB Ask endpoint to x402bazaar.org using viem (matching working pattern)
const fs = require('fs');
const { privateKeyToAccount } = require('viem/accounts');
const { recoverMessageAddress } = require('viem');
const path = require('path');

const KEY_FILE = '/home/ubuntu/prpo_ai/x402_bazaar/.bazaar_key';
const SERVER = process.env.BAZAAR_SERVER || 'https://x402-api.onrender.com';
const KB_TREASURY = '0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0';

const SERVICES = [
  { 
    name: 'xh-agents-kb-ask', 
    url: 'https://xhagents.xyz/api/kb/ask', 
    price: 0.03,
    desc: 'XH Agents Knowledge Base - Ask questions and get technical solutions from 15 curated entries covering devops, AI infra, payments, trading bots, and content automation',
    payTo: KB_TREASURY,
  },
];

async function main() {
  const key = fs.readFileSync(KEY_FILE, 'utf8').trim();
  const account = privateKeyToAccount(key.startsWith('0x') ? key : '0x' + key);
  console.log('Wallet (signer):', account.address);
  console.log('Payments route to:', KB_TREASURY);

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

    const body = { 
      url: s.url, 
      ownerAddress: account.address, 
      timestamp: ts, 
      signature, 
      price: s.price, 
      name: s.name,
      description: s.desc
    };
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
