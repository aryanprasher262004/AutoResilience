import type { Metadata } from "next";

import { ApiStatus } from "@/components/shell/api-status";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DescriptionList } from "@/components/ui/description-list";
import { PageHeader } from "@/components/ui/page-header";
import { CONSOLE_VERSION, REPOSITORY_URL, RUNTIME_MODE, RUNTIME_MODES } from "@/lib/runtime";

export const metadata: Metadata = { title: "About" };

export default function AboutPage() {
  return (
    <>
      <PageHeader title="About" description="What this console is and what it is connected to." />
      <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
        <Card>
          <CardHeader title="AutoResilience" />
          <CardBody className="grid gap-3 text-sm leading-relaxed text-muted">
            <p>
              A self-service resilience testing platform for Kubernetes: configure a controlled failure, let the
              server validate it, observe the impact from Kubernetes, server and client evidence, and get an
              explainable Resilience Score backed by that evidence.
            </p>
            <p>
              Pre-release software. It supports one fault type, pod-delete, and runs against a cluster you own. No
              software license has been published yet.
            </p>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="This installation" />
          <CardBody>
            <DescriptionList
              items={[
                { label: "Console version", value: <span className="font-mono">{CONSOLE_VERSION}</span> },
                { label: "Runtime mode", value: `${RUNTIME_MODES[RUNTIME_MODE].label} · ${RUNTIME_MODES[RUNTIME_MODE].summary}` },
                { label: "Engine (GET /ready)", value: <ApiStatus detailed /> },
                {
                  label: "Source",
                  value: (
                    <a href={REPOSITORY_URL} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                      GitHub ↗<span className="sr-only"> (opens in a new tab)</span>
                    </a>
                  ),
                },
              ]}
            />
          </CardBody>
        </Card>
      </div>
    </>
  );
}
