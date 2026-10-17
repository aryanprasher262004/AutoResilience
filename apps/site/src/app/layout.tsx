import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { SiteFooter } from "@/components/site-footer";
import { SiteNav } from "@/components/site-nav";

import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "AutoResilience · Resilience testing for Kubernetes", template: "%s · AutoResilience" },
  description:
    "Controlled failure, validated safety, measured recovery and an explainable Resilience Score for Kubernetes services.",
};

export const viewport: Viewport = { themeColor: "#0a0e19", colorScheme: "dark" };

// The static site talks to no server: connect-src 'self' only allows its own files, so
// even injected code could not reach a local engine API. (Dev mode needs eval/HMR.)
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'none'",
].join("; ");

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`}>
      <head>
        {process.env.NODE_ENV === "production" ? <meta httpEquiv="Content-Security-Policy" content={CSP} /> : null}
      </head>
      <body>
        <a
          href="#content"
          className="sr-only rounded-md bg-accent px-3 py-2 text-sm font-medium text-white focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[60]"
        >
          Skip to content
        </a>
        <SiteNav />
        <main id="content">{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}
