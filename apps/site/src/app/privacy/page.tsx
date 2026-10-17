import type { Metadata } from "next";

import { Container, PageHeader, StatusBadge } from "@/components/primitives";

export const metadata: Metadata = { title: "Privacy" };

export default function PrivacyPage() {
  return (
    <>
      <PageHeader eyebrow="Legal" title="Privacy" status={<StatusBadge status="planned">Draft</StatusBadge>}>
        <p>Last updated 17 October 2026.</p>
      </PageHeader>
      <Container className="max-w-3xl py-16">
        <div className="space-y-5 text-base leading-relaxed text-muted">
          <p>
            <strong className="text-fg">This website</strong> is a set of static files. It has no backend, sets
            no cookies, runs no analytics or tracking scripts and loads nothing from third parties; its fonts
            are bundled with the site.
          </p>
          <p>
            Hosting has not been chosen yet. Whichever host serves the site may keep standard web server
            logs; this page will name the host and its policy once one is in use.
          </p>
          <p>
            <strong className="text-fg">The AutoResilience software</strong> runs on your machine. It sends no
            telemetry; experiment data stays in your local database unless you export it yourself.
            Third-party build tools it uses, such as Next.js, have their own telemetry settings.
          </p>
        </div>
      </Container>
    </>
  );
}
