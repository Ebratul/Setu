import type { Metadata } from "next";
import { Inter, Noto_Sans_Bengali, Noto_Sans_SC } from "next/font/google";

import { I18nProvider } from "@/i18n";

import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const bengali = Noto_Sans_Bengali({
  variable: "--font-bengali",
  subsets: ["bengali"],
});

const chinese = Noto_Sans_SC({
  variable: "--font-sc",
  weight: ["400", "700"],
  preload: false,
});

export const metadata: Metadata = {
  title: "Setu — AI SME Finance Copilot",
  description:
    "AI SME finance copilot for Bangladeshi importers. Simulated sandbox.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${bengali.variable} ${chinese.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="flex min-h-full flex-col font-sans">
        <I18nProvider>{children}</I18nProvider>
      </body>
    </html>
  );
}
