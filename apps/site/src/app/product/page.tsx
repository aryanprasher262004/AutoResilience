import type { Metadata } from "next";

import { Container, PageHeader, Panel, StatusBadge, type Availability } from "@/components/primitives";

export const metadata: Metadata = { title: "Product" };

const capabilities: { title: string; body: string; status: Availability }[] = [
  {
    title: "Experiment builder",
    body: "Pick a discovered Deployment or StatefulSet and a pod-delete (graceful or forced), duration and number of affected replicas. The server checks it before you can start.",
    status: "available",
  },
  {
    title: "Safety validation",
    body: "Namespace-bound policies in code: forbidden system namespaces, duration and blast-radius limits, and a minimum of healthy replicas checked against the live workload.",
    status: "available",
  },
  {
    title: "Automatic orchestration",
    body: "A background reconciler drives each run through every phase, enforces deadlines, survives API restarts and cleans up only the chaos resources it created.",
    status: "available",
  },
  {
    title: "Three-sided evidence",
    body: "Kubernetes pod timestamps and availability, server-side request errors, and client-side failures and outage duration from a built-in load generator.",
    status: "available",
  },
  {
    title: "Explicit recovery decision",
    body: "COMPLETED only when replacements are Ready, availability is stable and Litmus agrees. Otherwise UNKNOWN, with a reason code and whether the cause was platform or application.",
    status: "available",
  },
  {
    title: "Explainable Resilience Score",
    body: "A versioned 0–100 score with a per-component breakdown, computed only from stored evidence and recomputable under older methodologies.",
    status: "available",
  },
  {
    title: "History, services and reports",
    body: "Filterable experiment history, per-workload history and a printable report for every run.",
    status: "available",
  },
  {
    title: "Recorded evidence",
    body: "Completed runs export as sanitized, hash-verified recordings: the basis for the public playground.",
    status: "available",
  },
  {
    title: "Packaged local stack",
    body: "A single command to start the engine, console and database locally, with explicit permissions and a guided first experiment.",
    status: "planned",
  },
  {
    title: "Bring your own application",
    body: "Import Kubernetes manifests or a Docker Compose project into a cluster AutoResilience owns.",
    status: "planned",
  },
  {
    title: "Desktop app",
    body: "A thin desktop shell over the same local stack.",
    status: "planned",
  },
];

export default function ProductPage() {
  return (
    <>
      <PageHeader eyebrow="Product" title="Controlled failure, measured recovery.">
        <p>
          AutoResilience is a self-service resilience testing platform for Kubernetes. It runs one bounded
          fault at a time and turns what happened into evidence and a score. Today it supports one fault,
          pod-delete, and it is honest about that.
        </p>
      </PageHeader>
      <Container className="py-16">
        <ul className="grid gap-4 md:grid-cols-2">
          {capabilities.map((item) => (
            <li key={item.title}>
              <Panel className="reveal h-full p-6">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <h2 className="font-medium">{item.title}</h2>
                  <StatusBadge status={item.status} />
                </div>
                <p className="mt-3 text-sm leading-relaxed text-muted">{item.body}</p>
              </Panel>
            </li>
          ))}
        </ul>
        <Panel className="reveal mt-10 p-6">
          <h2 className="font-medium">Built on</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            LitmusChaos for failure injection, Prometheus and kube-state-metrics for observation, a FastAPI
            engine with PostgreSQL for experiment history, and a Next.js console. The reference environment is
            a local kind cluster with two sample applications.
          </p>
        </Panel>
      </Container>
    </>
  );
}
