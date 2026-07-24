import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Noto_Sans_Devanagari } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const jbMono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jbmono", display: "swap" });
const notoDev = Noto_Sans_Devanagari({
  subsets: ["devanagari"],
  variable: "--font-noto-dev",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Vednix AI — The Next Generation AI Workspace",
  description:
    "Offline-first, multilingual AI workspace. Hindi, Hinglish, English — your language, your machine, your data.",
  applicationName: "Vednix AI",
};

export const viewport: Viewport = {
  themeColor: "#050505",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} ${jbMono.variable} ${notoDev.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}
