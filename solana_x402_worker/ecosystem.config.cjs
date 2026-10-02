module.exports = {
  apps: [{
    name: 'solana-x402',
    script: 'src/server.js',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '512M',
    env: {
      NODE_ENV: 'production',
      PORT: 3000,
      SOLANA_TREASURY_PUBLIC_KEY: 'GhFbGgNxERN6pQ7boSFLFJuPwXJuvJ8Tx7EgoJ9LV2Aw',
      SOLANA_RPC_URL: 'https://api.mainnet-beta.solana.com',
      BASE_URL: 'https://pronomad.duckdns.org'
    }
  }]
};
