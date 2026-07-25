import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Noto_Sans_Devanagari, Outfit } from "next/font/google";
import { BootGate } from "@/components/brand/BootGate";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const outfit = Outfit({ subsets: ["latin"], variable: "--font-outfit", display: "swap" });
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
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        {/* theme bootstrap — before first paint, zero flash (FOUC-safe).
            Defaults to Obsidian; honors localStorage, then OS preference. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem("vednix.theme");if(t==="light"||t==="dark"){document.documentElement.dataset.theme=t}else if(window.matchMedia("(prefers-color-scheme: light)").matches){document.documentElement.dataset.theme="light"}}catch(e){}`,
          }}
        />
      </head>
      <body
        className={`${inter.variable} ${outfit.variable} ${jbMono.variable} ${notoDev.variable} antialiased`}
      >
        <BootGate />
        {children}
      </body>
    </html>
  );
}
