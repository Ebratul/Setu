import type { Metadata, Viewport } from "next";
import { Inter, Noto_Sans_Bengali, Noto_Sans_SC } from "next/font/google";

import { I18nProvider } from "@/i18n";
import { THEME_INIT_SCRIPT } from "@/lib/theme";

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
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: { default: "Setu সেতু — AI SME Finance Copilot", template: "%s · Setu" },
  description:
    "AI finance copilot for Bangladeshi importers buying from China: milestone escrow, risk-tiered approvals, signed audit log. Simulated sandbox with fictional data.",
  applicationName: "Setu",
  openGraph: { siteName: "Setu সেতু", type: "website" },
  twitter: { card: "summary_large_image" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#0f766e" },
    { media: "(prefers-color-scheme: dark)", color: "#0b1220" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${bengali.variable} ${chinese.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="flex min-h-full flex-col font-sans">
        <I18nProvider>{children}</I18nProvider>
      </body>
    </html>
  );
}
