import type { Metadata } from "next";
import { Plus_Jakarta_Sans, Instrument_Serif, JetBrains_Mono } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider } from "@/lib/brand-context";
import { AuthGate } from "@/components/auth-gate";
import { ToastProvider } from "@/components/ui/Toast";

// Matches "Raindeer Social Startup Onboarding/Raindeer Social.dc.html"'s
// <helmet> font-face declaration exactly.
const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-jakarta",
});
const instrumentSerif = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
  variable: "--font-instrument-serif",
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-jetbrains-mono",
});

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
    <html
      lang="en"
      className={`${jakarta.variable} ${instrumentSerif.variable} ${jetbrainsMono.variable}`}
    >
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
