import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { OpenGuideButton } from "@/components/help/open-guide-button";
import { SetupChecklist } from "@/components/help/setup-checklist";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { STATE_META } from "@/lib/experiment-state";
import { docsUrl } from "@/lib/runtime";

export const metadata: Metadata = { title: "Help" };

const TROUBLESHOOTING: { id: string; title: string; body: ReactNode }[] = [
  {
    id: "api-unreachable",
    title: "API unreachable",
    body: (
      <>
        The console cannot reach the engine. Local stack: <code>python3 tools/ar/ar.py status</code> shows which
        container is down and <code>python3 tools/ar/ar.py start</code> starts it. Development: start it from{" "}
        <code>apps/api</code> with <code>KUBE_CONTEXT=kind-autoresilience uv run fastapi dev app/main.py</code>. The
        console proxies to the address fixed at build time (Settings → API connection).
      </>
    ),
  },
  {
    id: "database_unreachable",
    title: "Database unavailable",
    body: (
      <>
        PostgreSQL is not reachable. Local stack: <code>python3 tools/ar/ar.py start</code>. Development:{" "}
        <code>./scripts/dev-db.sh</code> starts it and applies the migrations.
      </>
    ),
  },
  {
    id: "schema_missing",
    title: "Database not migrated",
    body: (
      <>
        The database exists but has no schema. Run <code>uv run alembic upgrade head</code> in <code>apps/api</code>.
      </>
    ),
  },
  {
    id: "schema_outdated",
    title: "Database schema outdated",
    body: (
      <>
        The engine is newer than the database. Run <code>uv run alembic upgrade head</code> in <code>apps/api</code>.
      </>
    ),
  },
  {
    id: "no-workloads",
    title: "No workloads discovered",
    body: (
      <>
        The engine lists Deployments and StatefulSets through <code>KUBE_CONTEXT</code>; system namespaces are never
        listed. <code>python3 tools/ar/ar.py install</code> (or <code>./scripts/dev-cluster.sh</code> for development)
        creates the local cluster with two sample applications. Settings → Local environment shows whether the engine
        reaches the cluster at all.
      </>
    ),
  },
  {
    id: "baseline",
    title: "Baseline fails right after a restart",
    body: (
      <>
        Prometheus keeps its data in memory. After it restarts, baselines lack samples for about a minute; the run
        ends Undetermined (platform) rather than guessing. Wait and start a new run.
      </>
    ),
  },
  {
    id: "validation",
    title: "An experiment was blocked by safety validation",
    body: (
      <>
        The safety step lists every check with the server&apos;s message and, for failed checks, why it exists. Adjust
        the target or blast radius; limits cannot be changed from the console.
      </>
    ),
  },
];

const DOCS: [string, string][] = [
  ["Setup and usage guide", "README.md"],
  ["Local stack: install, upgrade, backup", "docs/local-stack.md"],
  ["Safety policy", "chaos/policies/safety-policy.md"],
  ["Orchestration", "docs/orchestration.md"],
  ["Resilience Score v3", "docs/scoring/resilience-score-v3.md"],
  ["Prometheus queries", "monitoring/prometheus/queries.md"],
  ["Recorded experiments", "docs/recordings.md"],
];

export default function HelpPage() {
  return (
    <>
      <PageHeader
        title="Help"
        description="Get set up, fix common problems and look up what each state means."
        actions={<OpenGuideButton />}
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start">
        <div className="grid min-w-0 gap-4">
          <Card>
            <CardHeader title="Getting started" description="Checked live against the API" />
            <SetupChecklist />
          </Card>

          <Card>
            <CardHeader title="Troubleshooting" />
            <div className="divide-y divide-line">
              {TROUBLESHOOTING.map((item) => (
                <section key={item.id} id={item.id} aria-labelledby={`${item.id}-title`} className="scroll-mt-20 px-4 py-3">
                  <h3 id={`${item.id}-title`} className="text-sm font-medium text-fg">
                    {item.title}
                  </h3>
                  <p className="mt-1 text-xs leading-relaxed text-muted [&_code]:font-mono [&_code]:text-fg">{item.body}</p>
                </section>
              ))}
            </div>
          </Card>

          <Card>
            <CardHeader title="Experiment states" description="As the console presents them" />
            <dl className="divide-y divide-line">
              {Object.entries(STATE_META).map(([state, meta]) => (
                <div key={state} className="grid gap-1 px-4 py-2.5 sm:grid-cols-[11rem_1fr]">
                  <dt className="text-sm text-fg">
                    {meta.label} <span className="block font-mono text-2xs text-faint">{state}</span>
                  </dt>
                  <dd className="text-xs text-muted">{meta.description}</dd>
                </div>
              ))}
            </dl>
          </Card>
        </div>

        <aside className="grid gap-4 lg:sticky lg:top-20">
          <Card>
            <CardHeader title="Learn more" />
            <CardBody className="grid gap-2 text-sm">
              <Link href="/how-it-works" className="text-accent hover:underline">
                How it works
              </Link>
              <Link href="/support" className="text-accent hover:underline">
                Support and diagnostics
              </Link>
              <p className="mt-2 text-2xs font-medium tracking-wide text-faint uppercase">Documentation (GitHub)</p>
              {DOCS.map(([label, path]) => (
                <a key={path} href={docsUrl(path)} target="_blank" rel="noreferrer" className="text-muted hover:text-fg">
                  {label} ↗<span className="sr-only"> (opens in a new tab)</span>
                </a>
              ))}
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Keyboard" />
            <CardBody className="text-xs leading-relaxed text-muted">
              Every control is reachable with Tab; “Skip to content” is the first stop on each page. In the guide and
              dialogs, Escape closes and focus returns to where you were.
            </CardBody>
          </Card>
        </aside>
      </div>
    </>
  );
}
