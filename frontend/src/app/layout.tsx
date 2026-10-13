import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { AppShell } from "@/components/shell/app-shell";
import { EnumProvider } from "@/providers/enum-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "BugFlow",
  description: "Bug triage with agents",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <EnumProvider>
          <AppShell>{children}</AppShell>
        </EnumProvider>
      </body>
    </html>
  );
}
