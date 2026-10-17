import type { Metadata } from "next";

import { Container, ExternalLink, PageHeader, Panel } from "@/components/primitives";
import { GITHUB_URL } from "@/lib/site";

export const metadata: Metadata = { title: "About" };

const principles = [
  {
    title: "Evidence over claims",
    body: "Every decision is backed by stored evidence. Missing data is shown as missing, never filled in.",
  },
  {
    title: "Safety before injection",
    body: "Limits are enforced by the server against the live cluster. A check that cannot run does not pass.",
  },
  {
    title: "Honest uncertainty",
    body: "When the platform, not the application, is the problem, the run is UNKNOWN and not scored.",
  },
  {
    title: "Local first",
    body: "The engine runs on your machine against a cluster you own. Nothing is sent anywhere.",
  },
];

export default function AboutPage() {
  return (
    <>
      <PageHeader eyebrow="About" title="Why AutoResilience exists.">
        <p>
          Teams often say their services are resilient because Kubernetes restarts failed pods. AutoResilience
          makes that a measurable statement: one controlled failure, checked for safety, observed from every
          side, with a recovery decision and a score anyone can inspect.
        </p>
      </PageHeader>
      <Container className="py-16">
        <ul className="grid gap-4 md:grid-cols-2">
          {principles.map((item) => (
            <li key={item.title}>
              <Panel className="reveal h-full p-6">
                <h2 className="font-medium">{item.title}</h2>
                <p className="mt-2 text-sm leading-relaxed text-muted">{item.body}</p>
              </Panel>
            </li>
          ))}
        </ul>
        <Panel className="reveal mt-10 p-6">
          <h2 className="font-medium">Project status</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            AutoResilience is pre-release and developed in the open. It supports a single fault type,
            pod-delete, on a local kind cluster.{" "}
            <ExternalLink href={GITHUB_URL} className="text-accent hover:underline">
              Source on GitHub
            </ExternalLink>
            .
          </p>
        </Panel>
      </Container>
    </>
  );
}
