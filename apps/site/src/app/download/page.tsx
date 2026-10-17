import type { Metadata } from "next";

import { Container, ExternalLink, PageHeader, Panel, StatusBadge } from "@/components/primitives";
import { GITHUB_URL, repoFile } from "@/lib/site";

export const metadata: Metadata = { title: "Download" };

const requirements = [
  ["Docker", "running; kind and PostgreSQL run on it"],
  ["kind", "local Kubernetes cluster"],
  ["kubectl, Helm", "cluster access, Prometheus and LitmusChaos charts"],
  ["uv", "Python 3.12 environment for the engine"],
  ["Node.js 24", "web console"],
];

const steps = [
  { label: "Clone", code: `git clone ${GITHUB_URL}.git\ncd AutoResilience` },
  { label: "Cluster, monitoring, chaos and sample apps", code: "./scripts/dev-cluster.sh" },
  { label: "Database", code: "./scripts/dev-db.sh" },
  {
    label: "Engine API (keep it running)",
    code: "cd apps/api && uv sync --frozen\nKUBE_CONTEXT=kind-autoresilience uv run fastapi dev app/main.py",
  },
  { label: "Console", code: "npm ci            # from the repository root\nnpm run dev --workspace web" },
];

export default function DownloadPage() {
  return (
    <>
      <PageHeader eyebrow="Download" title="Not yet released." status={<StatusBadge status="planned">No release yet</StatusBadge>}>
        <p>
          There are no installers, release artefacts, checksums or signatures yet. A packaged local stack is
          planned; when it ships, this page will list each artefact with its checksum and signature.
        </p>
      </PageHeader>
      <Container className="grid gap-8 py-16 lg:grid-cols-[1fr_1.4fr] [&>*]:min-w-0">
        <div className="space-y-8">
          <Panel className="reveal p-6">
            <h2 className="font-medium">Run it from source today</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              Everything runs on your machine against a local kind cluster with two sample applications.
              Allocate enough resources to Docker: the reference environment used 10 CPUs and about 8 GB of
              memory.
            </p>
          </Panel>
          <Panel className="reveal p-6">
            <h2 className="font-medium">Requirements</h2>
            <dl className="mt-4 divide-y divide-line text-sm">
              {requirements.map(([tool, use]) => (
                <div key={tool} className="flex justify-between gap-4 py-2.5">
                  <dt>{tool}</dt>
                  <dd className="text-right text-muted">{use}</dd>
                </div>
              ))}
            </dl>
            <ExternalLink href={repoFile("README.md")} className="mt-4 inline-block text-sm text-accent hover:underline">
              Full setup guide ↗
            </ExternalLink>
          </Panel>
        </div>
        <ol className="space-y-4">
          {steps.map((step, i) => (
            <li key={step.label}>
              <Panel className="reveal overflow-hidden">
                <p className="border-b border-line px-5 py-3 text-sm">
                  <span className="mr-2 font-mono text-xs text-accent">{String(i + 1).padStart(2, "0")}</span>
                  {step.label}
                </p>
                <pre tabIndex={0} className="overflow-x-auto px-5 py-4 font-mono text-[13px] leading-relaxed text-muted">
                  <code>{step.code}</code>
                </pre>
              </Panel>
            </li>
          ))}
        </ol>
      </Container>
    </>
  );
}
