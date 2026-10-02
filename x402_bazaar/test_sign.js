// Test the exact message format and signature
const { privateKeyToAccount } = require('viem/accounts');
const { recoverMessageAddress } = require('viem');
const fs = require('fs');

const KEY_FILE = '/home/ubuntu/prpo_ai/x402_bazaar/.bazaar_key';

const key = fs.readFileSync(KEY_FILE, 'utf8').trim();
const account = privateKeyToAccount(key.startsWith('0x') ? key : '0x' + key);

const url = 'https://xhagents.xyz/api/kb/ask';
const ts = Date.now();
const message = `quick-register:${url}:${account.address}:${ts}`;

console.log('Account:', account.address);
console.log('Message:', message);

async function test() {
  const signature = await account.signMessage({ message });
  console.log('Signature:', signature);

  const rec = await recoverMessageAddress({ message, signature });
  console.log('Recovered:', rec);
  console.log('Match:', rec.toLowerCase() === account.address.toLowerCase());

  // Test with lowercase owner
  const message2 = `quick-register:${url}:${account.address.toLowerCase()}:${ts}`;
  console.log('\nMessage2:', message2);
  const signature2 = await account.signMessage({ message2 });
  const rec2 = await recoverMessageAddress({ message2, signature2 });
  console.log('Recovered2:', rec2);
  console.log('Match2:', rec2.toLowerCase() === account.address.toLowerCase());
}

test().catch(console.error);
