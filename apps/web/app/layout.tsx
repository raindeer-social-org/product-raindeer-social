import type { Metadata } from "next";
import { Inter } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider } from "@/lib/brand-context";
import { AuthGate } from "@/components/auth-gate";
import { ToastProvider } from "@/components/ui/Toast";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Raindeer Social",
  description: "AI-native social media management",
};

// Root layout: every route in the app renders inside AuthProvider ->
// BrandProvider -> AuthGate. AuthGate is what redirects unauthenticated
// visitors to /login and renders the nav shell once signed in; BrandProvider
// is what scopes brand-aware pages to the switcher's current selection.
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="font-sans">
        <ToastProvider>
          <AuthProvider>
            <BrandProvider>
              <AuthGate>{children}</AuthGate>
            </BrandProvider>
          </AuthProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
