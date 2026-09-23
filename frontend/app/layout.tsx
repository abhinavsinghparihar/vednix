import type { Metadata, Viewport } from "next";
import "@fontsource-variable/inter";
import "@fontsource-variable/outfit";
import "@fontsource-variable/jetbrains-mono";
import "@fontsource/noto-sans-devanagari/devanagari.css";
import { BootGate } from "@/components/brand/BootGate";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vednix AI — The Next Generation AI Workspace",
  description:
    "Private-first, multilingual AI workspace. Hindi, Hinglish, English — your language, your machine, your data.",
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
      <body className="antialiased">
        <BootGate />
        {children}
      </body>
    </html>
  );
}
