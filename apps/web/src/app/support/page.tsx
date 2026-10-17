import type { Metadata } from "next";
import Link from "next/link";

import { Diagnostics } from "@/components/help/diagnostics";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { REPOSITORY_URL } from "@/lib/runtime";

export const metadata: Metadata = { title: "Support" };

export default function SupportPage() {
  const upstream = process.env.AUTORESILIENCE_API_PROXY_TARGET ?? "unknown";
  return (
    <>
      <PageHeader title="Support" description="What help exists today, and what to include when you ask for it." />
      <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
        <Card>
          <CardHeader title="Where to get help" />
          <ul className="divide-y divide-line">
            <li className="flex items-start justify-between gap-3 px-4 py-3">
              <div>
                <p className="text-sm text-fg">Help and troubleshooting</p>
                <p className="mt-0.5 text-xs text-muted">
                  Setup checks, fixes for each readiness problem, and what every state means.{" "}
                  <Link href="/help" className="text-accent hover:underline">
                    Open Help
                  </Link>
                </p>
              </div>
              <Badge tone="success" dot>
                Available
              </Badge>
            </li>
            <li className="flex items-start justify-between gap-3 px-4 py-3">
              <div>
                <p className="text-sm text-fg">Source repository</p>
                <p className="mt-0.5 text-xs text-muted">
                  Code, documentation and issues.{" "}
                  <a href={REPOSITORY_URL} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                    GitHub ↗<span className="sr-only"> (opens in a new tab)</span>
                  </a>
                </p>
              </div>
              <Badge tone="success" dot>
                Available
              </Badge>
            </li>
            <li className="flex items-start justify-between gap-3 px-4 py-3">
              <div>
                <p className="text-sm text-fg">Support channel</p>
                <p className="mt-0.5 text-xs text-muted">
                  There is no support desk, ticketing or chat for AutoResilience yet, and this console sends nothing
                  anywhere.
                </p>
              </div>
              <Badge tone="warning" dot>
                Planned
              </Badge>
            </li>
          </ul>
        </Card>
        <Card>
          <CardHeader
            title="Diagnostics"
            description="Paste this into an issue. It holds no secrets and no experiment data."
          />
          <CardBody>
            <Diagnostics upstream={upstream} />
          </CardBody>
        </Card>
      </div>
    </>
  );
}
