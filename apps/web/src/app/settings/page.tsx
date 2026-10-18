import type { Metadata } from "next";
import type { ReactNode } from "react";

import { ClusterAccess } from "@/components/settings/cluster-access";
import { DataAndBackups } from "@/components/settings/data-backups";
import { LocalEnvironment, StackCommands } from "@/components/settings/local-environment";
import { PreferencesForm } from "@/components/settings/preferences-form";
import { StackControls } from "@/components/settings/stack-controls";
import { TourControls } from "@/components/settings/tour-controls";
import { ApiStatus } from "@/components/shell/api-status";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DescriptionList } from "@/components/ui/description-list";
import { PageHeader } from "@/components/ui/page-header";
import { PlannedState } from "@/components/ui/states";
import { API_BASE_PATH } from "@/lib/api/client";
import { TOUR_TARGET } from "@/lib/help-content";
import { RUNTIME_MODE, RUNTIME_MODES, type RuntimeMode } from "@/lib/runtime";

export const metadata: Metadata = { title: "Settings" };

const SECTIONS = [
  { id: "environment", title: "Environment health", description: "How this console reaches the engine, and how the engine reaches its database, cluster and Prometheus." },
  { id: "kubernetes", title: "Kubernetes access", description: "The clusters the engine may read and the one where experiments may run." },
  { id: "data", title: "Data and backups", description: "Where experiment history lives, and backing it up or restoring it." },
  { id: "stack", title: "Stack operations", description: "The operations allowed from the browser, and the terminal commands for everything else." },
  { id: "console", title: "Console", description: "Preferences and tours stored in this browser only." },
] as const;
type SectionId = (typeof SECTIONS)[number]["id"];

function Section({ id, children }: { id: SectionId; children: ReactNode }) {
  const meta = SECTIONS.find((s) => s.id === id)!;
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="grid scroll-mt-20 gap-3">
      <div>
        <h2 id={`${id}-title`} className="text-base font-semibold text-fg">
          {meta.title}
        </h2>
        <p className="mt-0.5 text-xs text-muted">{meta.description}</p>
      </div>
      {children}
    </section>
  );
}

export default function SettingsPage() {
  // The rewrite target baked in at build time (next.config.ts), i.e. where requests really go.
  const upstream = process.env.AUTORESILIENCE_API_PROXY_TARGET ?? "unknown";
  return (
    <>
      <PageHeader title="Settings" description="What the engine can reach, where data lives, and what this console may do." />
      <nav aria-label="Settings sections" data-tour={TOUR_TARGET.settingsSections} className="mb-6 flex flex-wrap gap-1.5">
        {SECTIONS.map((s) => (
          <a
            key={s.id}
            href={`#${s.id}`}
            className="rounded-md border border-line px-2.5 py-1 text-xs text-muted hover:border-line-strong hover:text-fg"
          >
            {s.title}
          </a>
        ))}
      </nav>
      <div className="grid gap-8">
        <Section id="environment">
          <LocalEnvironment />
          <Card>
            <CardHeader level={3} title="API connection" description="Fixed when the console is built." />
            <CardBody>
              <DescriptionList
                items={[
                  { label: "Browser endpoint", value: <code className="font-mono">{API_BASE_PATH}</code> },
                  {
                    label: "Proxied to (AUTORESILIENCE_API_URL at build time)",
                    value: <code className="font-mono">{upstream}</code>,
                  },
                  { label: "Status (GET /ready)", value: <ApiStatus detailed /> },
                ]}
              />
            </CardBody>
          </Card>
          <Card>
            <CardHeader level={3} title="Runtime mode" description="Where the engine and this console run." />
            <ul className="divide-y divide-line">
              {(Object.keys(RUNTIME_MODES) as RuntimeMode[]).map((mode) => {
                const meta = RUNTIME_MODES[mode];
                return (
                  <li key={mode} className="flex flex-wrap items-start justify-between gap-3 px-4 py-3">
                    <div className="min-w-0">
                      <p className="text-sm text-fg">
                        {meta.label}
                        {mode === RUNTIME_MODE ? <span className="ml-2 text-xs text-accent">this console</span> : null}
                      </p>
                      <p className="mt-0.5 text-xs text-muted">{meta.summary}</p>
                    </div>
                    <Badge tone={meta.status === "available" ? "success" : "warning"} dot>
                      {meta.status === "available" ? "Available" : "Planned"}
                    </Badge>
                  </li>
                );
              })}
            </ul>
          </Card>
        </Section>

        <Section id="kubernetes">
          <ClusterAccess />
        </Section>

        <Section id="data">
          <DataAndBackups />
        </Section>

        <Section id="stack">
          <StackControls />
          <StackCommands />
          <PlannedState milestone="Not in the browser" title="What stays out of the console">
            <p>
              Installing, upgrading, restoring and uninstalling the stack, and granting the engine access to further
              clusters (<code className="font-mono">ar cluster import</code>), provision or delete resources and run only
              from a terminal. The engine&apos;s clusters are fixed when it starts (
              <code className="font-mono">KUBE_CONTEXT</code>, <code className="font-mono">DISCOVERY_CLUSTERS</code>).
            </p>
            <p>
              Safety policies, timeouts and limits are configured in the engine (code and environment variables) and
              are deliberately not editable from the browser.
            </p>
          </PlannedState>
        </Section>

        <Section id="console">
          <PreferencesForm />
          <TourControls />
        </Section>
      </div>
    </>
  );
}
