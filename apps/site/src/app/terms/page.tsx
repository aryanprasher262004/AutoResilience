import type { Metadata } from "next";

import { Container, PageHeader, StatusBadge } from "@/components/primitives";

export const metadata: Metadata = { title: "Terms" };

export default function TermsPage() {
  return (
    <>
      <PageHeader eyebrow="Legal" title="Terms" status={<StatusBadge status="planned">Draft</StatusBadge>}>
        <p>Last updated 17 October 2026.</p>
      </PageHeader>
      <Container className="max-w-3xl py-16">
        <div className="space-y-5 text-base leading-relaxed text-muted">
          <p>
            No software license has been published for AutoResilience yet. Until one is, the source is
            available to read on GitHub, but no other rights are granted.
          </p>
          <p>
            AutoResilience is pre-release software, provided as is and without warranty. It deletes pods by
            design: run it only against clusters you own or are explicitly authorised to test.
          </p>
          <p>These terms will be replaced when the first release and its license are published.</p>
        </div>
      </Container>
    </>
  );
}
