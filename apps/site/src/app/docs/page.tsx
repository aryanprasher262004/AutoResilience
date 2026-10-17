import type { Metadata } from "next";

import { Container, ExternalLink, PageHeader, Panel, StatusBadge } from "@/components/primitives";
import { repoFile } from "@/lib/site";

export const metadata: Metadata = { title: "Docs" };

const docs = [
  { title: "Setup and usage guide", path: "README.md", body: "Prerequisites, local cluster, database, API, console and a first experiment." },
  { title: "Safety policy", path: "chaos/policies/safety-policy.md", body: "What the engine may and may not do to a cluster." },
  { title: "Orchestration", path: "docs/orchestration.md", body: "The reconciler, deadlines, abort and cleanup." },
  { title: "Resilience Score v3", path: "docs/scoring/resilience-score-v3.md", body: "Components, weights, thresholds and caps." },
  { title: "Prometheus queries", path: "monitoring/prometheus/queries.md", body: "Every query behind the baseline and observation." },
  { title: "Recorded experiments", path: "docs/recordings.md", body: "The recording contract, sanitization and export runbook." },
];

export default function DocsPage() {
  return (
    <>
      <PageHeader eyebrow="Docs" title="Documentation" status={<StatusBadge status="planned">Docs site planned</StatusBadge>}>
        <p>
          A searchable documentation site is planned. Until then, the documentation lives in the repository and
          is kept in step with the code.
        </p>
      </PageHeader>
      <Container className="py-16">
        <ul className="grid gap-4 md:grid-cols-2">
          {docs.map((doc) => (
            <li key={doc.path}>
              <ExternalLink href={repoFile(doc.path)} className="group block h-full">
                <Panel className="reveal h-full p-6 transition-colors group-hover:border-line-strong">
                  <h2 className="font-medium group-hover:text-accent">{doc.title} ↗</h2>
                  <p className="mt-2 text-sm leading-relaxed text-muted">{doc.body}</p>
                  <p className="mt-4 font-mono text-xs text-faint">{doc.path}</p>
                </Panel>
              </ExternalLink>
            </li>
          ))}
        </ul>
      </Container>
    </>
  );
}
