import type { Metadata } from "next";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "LitCount — Save & Win DeFi Pool",
  description: "Just stake it dan get reward. Pool staking on LitVM Testnet.",
  icons: { icon: "/favicon.ico" },
  openGraph: {
    title: "LitCount",
    description: "Just stake it dan get reward.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-black text-white antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
