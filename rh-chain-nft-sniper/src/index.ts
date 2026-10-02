// RH Chain NFT Mint Sniper - Entry Point
// Public SeaDrop mint sniper for Robinhood Chain (chain ID 4663)

import chalk from "chalk";
import { runWizard } from "./wizard";
import { closePrompts } from "./prompt";

const HELP = `
RH Chain NFT Mint Sniper
Mint NFT trong các đợt public SeaDrop trên Robinhood Chain (4663).
Calldata được tạo từ dữ liệu on-chain, không cần tài khoản hoặc access token OpenSea.

Sử dụng:
  npm start              Chạy trình hướng dẫn tương tác
  npm start -- --help    Hiển thị trợ giúp này
  npm run dry-run        Chạy ở chế độ dry-run (simulate only)

Chương trình sẽ lần lượt hỏi private key, chain, số lượng, liên kết NFT, RPC,
gas và thời điểm mint. Có thể đặt giá trị mặc định trong .env (xem .env.example).
`;

async function main(): Promise<void> {
  const args = process.argv.slice(2);

  if (args.includes("--help") || args.includes("-h")) {
    console.log(HELP);
    return;
  }

  try {
    await runWizard();
    closePrompts();
    process.exit(0);
  } catch (err: any) {
    closePrompts();
    console.error(chalk.red(`\n❌ ${err.message}\n`));
    process.exit(1);
  }
}

void main();