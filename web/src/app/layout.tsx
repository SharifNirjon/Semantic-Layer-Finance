import type { Metadata } from "next";
import type { ReactNode } from "react";
import AppShell from "@/components/AppShell";
import { AuthProvider } from "@/lib/auth";
// Fonts are bundled (no runtime call to a font CDN, so locked-down bank networks render the same).
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "./globals.css";

export const metadata: Metadata = {
  title: "Governed Banking Analytics",
  description: "One governed definition for every number: copilot, dashboard and audit trail.",
};

// Sets the theme before first paint so there is no light/dark flash.
const THEME_SCRIPT = `try{var t=localStorage.getItem('gba.theme');if(!t){t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-screen">
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
