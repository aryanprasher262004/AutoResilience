import type { Metadata } from "next";

import { ButtonLink, Container, ExternalLink, PageHeader, Panel, StatusBadge } from "@/components/primitives";
import { repoFile } from "@/lib/site";

export const metadata: Metadata = { title: "Playground" };

export default function PlaygroundPage() {
  return (
    <>
      <PageHeader eyebrow="Playground" title="Replay real experiments, step by step." status={<StatusBadge status="planned">Coming soon</StatusBadge>}>
        <p>
          The playground will replay recorded runs in your browser: the timeline, the deleted pod and its
          replacement, the evidence and the score. Nothing is executed and nothing connects to a cluster.
        </p>
      </PageHeader>
      <Container className="py-16">
        <Panel className="reveal flex flex-col items-center px-6 py-16 text-center">
          <div aria-hidden className="grid size-12 place-items-center rounded-full border border-line-strong">
            <span className="size-2 rounded-full bg-faint" />
          </div>
          <h2 className="mt-6 text-xl font-medium">No recordings yet</h2>
          <p className="mt-3 max-w-lg text-sm leading-relaxed text-muted">
            Recordings are exported only from real, completed experiments, then sanitized, reviewed and
            hash-verified. They will appear here after the controlled evaluation campaign. There is no sample
            or simulated data in the meantime.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <ButtonLink href="/how-it-works" variant="primary">
              How a run works
            </ButtonLink>
            <ExternalLink
              href={repoFile("docs/recordings.md")}
              className="inline-flex h-11 items-center rounded-md border border-line-strong px-5 text-sm text-fg hover:bg-surface-3"
            >
              Recording format
            </ExternalLink>
          </div>
        </Panel>
      </Container>
    </>
  );
}
