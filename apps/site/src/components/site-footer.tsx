import Link from "next/link";
import type { ReactNode } from "react";

import { GITHUB_URL } from "@/lib/site";

import { LogoMark } from "./logo";
import { Container, StatusBadge } from "./primitives";

const linkClass = "text-sm text-muted transition-colors hover:text-fg";

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-line">
      <Container className="grid gap-10 py-14 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div>
          <Link href="/" className="inline-flex items-center gap-2 font-semibold tracking-tight">
            <LogoMark className="size-6" />
            AutoResilience
          </Link>
          <p className="mt-3 max-w-xs text-sm leading-relaxed text-muted">
            Controlled, evidence-based resilience testing for Kubernetes services. Pre-release software.
          </p>
        </div>
        <FooterColumn title="Product">
          <Link className={linkClass} href="/product">Product</Link>
          <Link className={linkClass} href="/how-it-works">How It Works</Link>
          <Link className={linkClass} href="/playground">Playground</Link>
          <Link className={linkClass} href="/download">Download</Link>
        </FooterColumn>
        <FooterColumn title="Project">
          <Link className={linkClass} href="/docs">Docs</Link>
          <a className={linkClass} href={GITHUB_URL} target="_blank" rel="noreferrer">
            GitHub<span className="sr-only"> (opens in a new tab)</span>
          </a>
          <Link className={linkClass} href="/about">About</Link>
          <span className="flex flex-wrap items-center gap-2 text-sm text-faint">
            Support <StatusBadge status="planned">Not set up yet</StatusBadge>
          </span>
        </FooterColumn>
        <FooterColumn title="Social">
          <span className="flex flex-wrap items-center gap-2 text-sm text-faint">
            Social accounts <StatusBadge status="placeholder" />
          </span>
          <p className="text-xs leading-relaxed text-faint">No official social accounts exist yet.</p>
        </FooterColumn>
      </Container>
      <div className="border-t border-line">
        <Container className="flex flex-col gap-3 py-6 text-xs text-faint sm:flex-row sm:items-center sm:justify-between">
          <p>© 2026 AutoResilience contributors. Not yet released.</p>
          <nav aria-label="Legal" className="flex gap-5">
            <Link className="hover:text-fg" href="/privacy">Privacy</Link>
            <Link className="hover:text-fg" href="/terms">Terms</Link>
          </nav>
        </Container>
      </div>
    </footer>
  );
}

function FooterColumn({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h2 className="font-mono text-xs tracking-[0.14em] text-faint uppercase">{title}</h2>
      <div className="mt-4 flex flex-col items-start gap-2.5">{children}</div>
    </div>
  );
}
